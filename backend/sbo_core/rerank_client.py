from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

import httpx

from sbo_core.errors import AppError, ErrorCode


@dataclass(frozen=True)
class RerankResult:
    evidence_id: str
    score: float


class RerankClient:
    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        timeout_ms: int,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._api_base = base_url.rstrip("/")
        self._api_key = api_key
        self._timeout = httpx.Timeout(timeout=max(timeout_ms, 1) / 1000)
        self._transport = transport

    async def rerank(
        self,
        *,
        query: str,
        candidates: list[dict[str, Any]],
        model: str | None = None,
        request_id: str | None = None,
    ) -> list[RerankResult]:
        rid = request_id or str(uuid.uuid4())

        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self._api_key}",
            "X-Request-ID": rid,
        }

        payload: dict[str, Any] = {
            "query": query,
            "candidates": candidates,
        }
        if model:
            payload["model"] = model

        url = self._api_base + "/rerank"

        async with httpx.AsyncClient(timeout=self._timeout, transport=self._transport) as client:
            try:
                resp = await client.post(url, headers=headers, json=payload)
            except httpx.TimeoutException as e:
                raise AppError(
                    code=ErrorCode.RERANK_FAILED,
                    message="Rerank provider timeout",
                    status_code=503,
                    details={"request_id": rid},
                ) from e
            except httpx.RequestError as e:
                raise AppError(
                    code=ErrorCode.RERANK_FAILED,
                    message="Rerank provider unavailable",
                    status_code=503,
                    details={"request_id": rid, "error": str(e)},
                ) from e

        if resp.status_code in (401, 403):
            raise AppError(
                code=ErrorCode.RERANK_FAILED,
                message="Rerank provider auth failed",
                status_code=503,
                details={"request_id": rid, "status_code": resp.status_code},
            )

        if resp.status_code >= 500:
            raise AppError(
                code=ErrorCode.RERANK_FAILED,
                message="Rerank provider returned server error",
                status_code=503,
                details={"request_id": rid, "status_code": resp.status_code},
            )

        try:
            data = resp.json()
        except Exception as e:
            raise AppError(
                code=ErrorCode.RERANK_FAILED,
                message="Rerank provider invalid JSON response",
                status_code=503,
                details={"request_id": rid, "status_code": resp.status_code},
            ) from e

        if not isinstance(data, dict) or data.get("success") is not True:
            raise AppError(
                code=ErrorCode.RERANK_FAILED,
                message="Rerank provider response unexpected (expected success=true)",
                status_code=503,
                details={"request_id": rid, "status_code": resp.status_code, "payload": data},
            )

        raw_items = data.get("data")
        if raw_items is None:
            return []
        if not isinstance(raw_items, list):
            raise AppError(
                code=ErrorCode.RERANK_FAILED,
                message="Rerank provider response unexpected (expected data as list)",
                status_code=503,
                details={"request_id": rid, "status_code": resp.status_code, "payload": data},
            )

        results: list[RerankResult] = []
        for item in raw_items:
            if not isinstance(item, dict):
                continue
            evidence_id = item.get("evidence_id")
            score = item.get("score")
            if not isinstance(evidence_id, str) or not isinstance(score, (int, float)):
                continue
            results.append(RerankResult(evidence_id=evidence_id, score=float(score)))

        return results
