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
        "PROVIDER_BASE_URL",
        "PROVIDER_API_KEY",
        "PROVIDER_MODEL_ID",
        "LLM_LLAMA_BASE_URL",
        "LLM_LLAMA_API_KEY",
        "LLM_LLAMA_MODEL_ID",
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

    base_url = os.environ.get("PROVIDER_BASE_URL") or os.environ.get("LLM_LLAMA_BASE_URL")
    api_key = os.environ.get("PROVIDER_API_KEY") or os.environ.get("LLM_LLAMA_API_KEY")
    model = os.environ.get("PROVIDER_MODEL_ID") or os.environ.get("LLM_LLAMA_MODEL_ID")

    missing = [
        k for k, v in {"PROVIDER_BASE_URL": base_url, "PROVIDER_API_KEY": api_key, "PROVIDER_MODEL_ID": model}.items() if not v
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

    # Assume OpenAI-compatible provider API
    models_url = api_base + "/models"
    try:
        _request_json("GET", models_url, headers=headers, timeout_seconds=20)
    except HTTPError as e:
        if e.code in (401, 403):
            raise RuntimeError("Provider auth failed. Verify PROVIDER_API_KEY.") from e
        raise RuntimeError(f"Provider connection failed. GET {models_url} returned HTTP {e.code}.") from e
    except URLError as e:
        raise RuntimeError(f"Provider connection failed. URLError when calling {models_url}.") from e

    chat_url = api_base + "/chat/completions"
    try:
        payload = _request_json(
            "POST",
            chat_url,
            headers=headers,
            timeout_seconds=60,
            body={
                "model": model,
                "messages": [{"role": "user", "content": "smoke test"}],
                "max_tokens": 1,
                "stream": False,
            },
        )
    except HTTPError as e:
        if e.code in (401, 403):
            raise RuntimeError("Provider auth failed. Verify PROVIDER_API_KEY.") from e
        raise RuntimeError(f"Provider chat completion failed. POST {chat_url} returned HTTP {e.code}.") from e
    except URLError as e:
        raise RuntimeError(f"Provider chat completion failed. URLError when calling {chat_url}.") from e
    except Exception as e:
        raise RuntimeError(f"Provider chat completion failed. Unexpected error when calling {chat_url}.") from e

    if not isinstance(payload, dict):
        raise RuntimeError("Provider response unexpected (expected JSON object)")


if __name__ == "__main__":
    main()
