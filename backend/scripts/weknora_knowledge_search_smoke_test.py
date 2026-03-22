from __future__ import annotations

import json
import os
import uuid
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import ProxyHandler, Request, build_opener


def _load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        if "=" not in s:
            continue
        k, v = s.split("=", 1)
        k = k.strip()
        v = v.strip().strip('"').strip("'")
        if k and k not in os.environ:
            os.environ[k] = v


def _request_json(
    *,
    method: str,
    url: str,
    headers: dict[str, str],
    timeout_seconds: float,
    body: dict[str, Any] | None = None,
) -> Any:
    data: bytes | None = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")

    req = Request(url=url, method=method, data=data)
    for k, v in headers.items():
        req.add_header(k, v)

    opener = build_opener(ProxyHandler({}))
    with opener.open(req, timeout=timeout_seconds) as resp:
        raw = resp.read()
        if not raw:
            return None
        try:
            return json.loads(raw.decode("utf-8"))
        except Exception:
            return raw.decode("utf-8", errors="replace")


def main() -> None:
    _load_env_file(Path(__file__).resolve().parents[1] / ".env")

    base_url = os.environ.get("WEKNORA_BASE_URL")
    api_key = os.environ.get("WEKNORA_API_KEY")
    timeout_ms = os.environ.get("WEKNORA_REQUEST_TIMEOUT_MS")
    kb_id = os.environ.get("WEKNORA_KNOWLEDGE_BASE_ID")
    kb_ids_raw = os.environ.get("WEKNORA_KNOWLEDGE_BASE_IDS")

    missing = [
        k
        for k, v in {
            "WEKNORA_BASE_URL": base_url,
            "WEKNORA_API_KEY": api_key,
            "WEKNORA_REQUEST_TIMEOUT_MS": timeout_ms,
        }.items()
        if not v
    ]
    if missing:
        raise RuntimeError(f"Missing required env vars: {', '.join(missing)}")

    try:
        timeout_seconds = max(int(timeout_ms or "0"), 1) / 1000
    except Exception as e:
        raise RuntimeError("Invalid WEKNORA_REQUEST_TIMEOUT_MS (expected integer milliseconds)") from e

    request_id = str(uuid.uuid4())
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "X-API-Key": api_key or "",
        "X-Request-ID": request_id,
    }

    api_base = (base_url or "").rstrip("/")
    if not api_base.endswith("/api/v1"):
        api_base = api_base + "/api/v1"

    url = api_base + "/knowledge-search"
    body: dict[str, Any] = {"query": "SecondBrainOS smoke test"}
    if kb_id:
        body["knowledge_base_id"] = kb_id
    elif kb_ids_raw:
        s = kb_ids_raw.strip()
        if s.startswith("["):
            try:
                parsed = json.loads(s)
                if isinstance(parsed, list) and all(isinstance(x, str) and x for x in parsed):
                    body["knowledge_base_ids"] = parsed
            except Exception:
                pass
        else:
            parts = [p.strip() for p in s.split(",") if p.strip()]
            if parts:
                body["knowledge_base_ids"] = parts

    try:
        payload = _request_json(method="POST", url=url, headers=headers, timeout_seconds=timeout_seconds, body=body)
    except HTTPError as e:
        try:
            raw = e.read()
            text = raw.decode("utf-8", errors="replace") if raw else ""
        except Exception:
            text = ""
        if e.code in (401, 403):
            raise RuntimeError("WeKnora auth failed. Verify WEKNORA_API_KEY and WEKNORA_BASE_URL.") from e
        raise RuntimeError(
            f"WeKnora connection failed. POST {url} returned HTTP {e.code}. Response body: {text}"
        ) from e
    except URLError as e:
        raise RuntimeError(f"WeKnora connection failed. URLError when calling {url}.") from e
    except Exception as e:
        raise RuntimeError(f"WeKnora connection failed. Unexpected error when calling {url}.") from e

    if not isinstance(payload, dict) or payload.get("success") is not True:
        raise RuntimeError("WeKnora response unexpected (expected JSON with success=true)")

    data = payload.get("data")
    if data is not None and not isinstance(data, list):
        raise RuntimeError("WeKnora response unexpected (expected data as list)")


if __name__ == "__main__":
    main()
