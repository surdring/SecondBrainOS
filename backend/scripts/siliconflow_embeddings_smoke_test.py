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
    force_override = {
        "SILICONFLOW_BASE_URL",
        "SILICONFLOW_API_KEY",
        "SILICONFLOW_EMBEDDING_MODEL",
    }
    for line in path.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        if "=" not in s:
            continue
        k, v = s.split("=", 1)
        k = k.strip()
        v = v.strip().strip('"').strip("'")
        if not k:
            continue
        if k in force_override or k not in os.environ:
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
        try:
            return json.loads(raw.decode("utf-8"))
        except Exception:
            return raw.decode("utf-8", errors="replace")


def main() -> None:
    _load_env_file(Path(__file__).resolve().parents[1] / ".env")

    base_url = os.environ.get("SILICONFLOW_BASE_URL")
    api_key = os.environ.get("SILICONFLOW_API_KEY")
    model = os.environ.get("SILICONFLOW_EMBEDDING_MODEL")

    missing = [
        k
        for k, v in {
            "SILICONFLOW_BASE_URL": base_url,
            "SILICONFLOW_API_KEY": api_key,
            "SILICONFLOW_EMBEDDING_MODEL": model,
        }.items()
        if not v
    ]
    if missing:
        raise RuntimeError(f"Missing required env vars: {', '.join(missing)}")

    request_id = str(uuid.uuid4())
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
        "X-Request-ID": request_id,
    }

    api_base = base_url.rstrip("/")

    models_url = api_base + "/models"
    try:
        payload = _request_json("GET", models_url, headers=headers, timeout_seconds=10)
    except HTTPError as e:
        if e.code in (401, 403):
            raise RuntimeError("SiliconFlow auth failed. Verify SILICONFLOW_API_KEY.") from e
        raise RuntimeError(f"SiliconFlow connection failed. GET {models_url} returned HTTP {e.code}.") from e
    except URLError as e:
        raise RuntimeError(f"SiliconFlow connection failed. URLError when calling {models_url}.") from e
    except Exception as e:
        raise RuntimeError(f"SiliconFlow connection failed. Unexpected error when calling {models_url}.") from e

    if payload is None:
        raise RuntimeError("SiliconFlow response empty (expected JSON)")

    embeddings_url = api_base + "/embeddings"
    try:
        payload2 = _request_json(
            "POST",
            embeddings_url,
            headers=headers,
            timeout_seconds=20,
            body={"model": model, "input": ["smoke test"]},
        )
    except HTTPError as e:
        if e.code in (401, 403):
            raise RuntimeError("SiliconFlow auth failed. Verify SILICONFLOW_API_KEY.") from e
        raise RuntimeError(f"SiliconFlow embeddings request failed. POST {embeddings_url} returned HTTP {e.code}.") from e
    except URLError as e:
        raise RuntimeError(f"SiliconFlow embeddings request failed. URLError when calling {embeddings_url}.") from e
    except Exception as e:
        raise RuntimeError(f"SiliconFlow embeddings request failed. Unexpected error when calling {embeddings_url}.") from e

    if not isinstance(payload2, dict):
        raise RuntimeError("SiliconFlow embeddings response unexpected (expected JSON object)")


if __name__ == "__main__":
    main()
