from __future__ import annotations

import json
import os
import uuid
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
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
        return json.loads(raw.decode("utf-8"))


def _extract_kb_ids(payload: Any) -> set[str]:
    ids: set[str] = set()
    if payload is None:
        return ids

    if isinstance(payload, dict):
        candidates = []
        for key in ("data", "items", "knowledge_bases", "knowledgeBases", "result"):
            if key in payload:
                candidates.append(payload[key])
        if not candidates:
            candidates.append(payload)

        for c in candidates:
            if isinstance(c, list):
                for item in c:
                    if isinstance(item, dict):
                        for k in ("id", "kb_id", "kbId"):
                            v = item.get(k)
                            if isinstance(v, str) and v:
                                ids.add(v)
    elif isinstance(payload, list):
        for item in payload:
            if isinstance(item, dict):
                v = item.get("id")
                if isinstance(v, str) and v:
                    ids.add(v)

    return ids


def main() -> None:
    _load_env_file(Path(__file__).resolve().parents[1] / ".env")

    base_url = os.environ.get("WEKNORA_BASE_URL")
    api_key = os.environ.get("WEKNORA_API_KEY")
    timeout_ms = os.environ.get("WEKNORA_REQUEST_TIMEOUT_MS")

    missing = [k for k, v in {"WEKNORA_BASE_URL": base_url, "WEKNORA_API_KEY": api_key, "WEKNORA_REQUEST_TIMEOUT_MS": timeout_ms}.items() if not v]
    if missing:
        raise RuntimeError(f"Missing required env vars: {', '.join(missing)}")

    try:
        timeout_seconds = max(int(timeout_ms or "0"), 1) / 1000
    except Exception as e:
        raise RuntimeError("Invalid WEKNORA_REQUEST_TIMEOUT_MS (expected integer milliseconds)") from e

    request_id = str(uuid.uuid4())
    headers = {
        "Accept": "application/json",
        "X-API-Key": api_key or "",
        "X-Request-ID": request_id,
    }

    api_base = base_url.rstrip("/")
    if not api_base.endswith("/api/v1"):
        api_base = api_base + "/api/v1"

    list_paths = ["/knowledge-bases"]
    create_paths = ["/knowledge-bases"]

    last_error: Exception | None = None

    for list_path in list_paths:
        list_url = api_base + list_path
        try:
            listed = _request_json("GET", list_url, headers=headers, timeout_seconds=timeout_seconds)
            before_ids = _extract_kb_ids(listed)

            name = f"sbo-smoke-{request_id[:8]}"
            created_ok = False

            for create_path in create_paths:
                create_url = api_base + create_path
                for body in (
                    {"name": name, "description": "", "type": "document"},
                    {"name": name, "description": ""},
                ):
                    try:
                        _request_json("POST", create_url, headers=headers, timeout_seconds=timeout_seconds, body=body)
                        created_ok = True
                        break
                    except HTTPError as e:
                        last_error = e
                        if e.code in (400, 404, 405, 409, 422):
                            continue
                        if e.code in (401, 403):
                            raise RuntimeError("WeKnora auth failed. Verify WEKNORA_API_KEY and WEKNORA_BASE_URL.") from e
                        raise
                    except Exception as e:
                        last_error = e
                if created_ok:
                    break

            if not created_ok:
                raise RuntimeError(
                    f"WeKnora KnowledgeBase create failed. Tried POST to: {', '.join(base_url.rstrip('/') + p for p in create_paths)}"
                ) from last_error

            listed2 = _request_json("GET", list_url, headers=headers, timeout_seconds=timeout_seconds)
            after_ids = _extract_kb_ids(listed2)
            if after_ids and before_ids and after_ids == before_ids:
                raise RuntimeError("WeKnora KnowledgeBase list did not change after create (unexpected)")

            return
        except HTTPError as e:
            last_error = e
            if e.code in (401, 403):
                raise RuntimeError("WeKnora auth failed. Verify WEKNORA_API_KEY and WEKNORA_BASE_URL.") from e
        except Exception as e:
            last_error = e

    raise RuntimeError(
        f"WeKnora KnowledgeBase list/create failed. Tried list paths: {', '.join(list_paths)}"
    ) from last_error


if __name__ == "__main__":
    main()
