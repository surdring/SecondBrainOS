from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

import httpx

from sbo_core.errors import (
    WeKnoraError,
    weknora_auth_error,
    weknora_timeout_error,
    weknora_unavailable_error,
)


@dataclass(frozen=True)
class WeKnoraSearchResult:
    id: str
    content: str
    score: float
    knowledge_id: str | None = None
    knowledge_title: str | None = None
    chunk_index: int | None = None
    metadata: dict[str, Any] | None = None


class WeKnoraClient:
    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        timeout_ms: int,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        api_base = base_url.rstrip("/")
        if not api_base.endswith("/api/v1"):
            api_base = api_base + "/api/v1"

        self._api_base = api_base
        self._api_key = api_key
        self._timeout = httpx.Timeout(timeout=max(timeout_ms, 1) / 1000)
        self._transport = transport

    async def knowledge_search(
        self,
        *,
        query: str,
        knowledge_base_id: str | None = None,
        knowledge_base_ids: list[str] | None = None,
        knowledge_ids: list[str] | None = None,
        request_id: str | None = None,
        top_k: int | None = None,
    ) -> list[WeKnoraSearchResult]:
        rid = request_id or str(uuid.uuid4())

        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "X-API-Key": self._api_key,
            "X-Request-ID": rid,
        }

        payload: dict[str, Any] = {"query": query}
        if knowledge_base_id:
            payload["knowledge_base_id"] = knowledge_base_id
        elif knowledge_base_ids:
            payload["knowledge_base_ids"] = knowledge_base_ids
        if knowledge_ids:
            payload["knowledge_ids"] = knowledge_ids

        url = self._api_base + "/knowledge-search"

        async with httpx.AsyncClient(timeout=self._timeout, transport=self._transport) as client:
            try:
                resp = await client.post(url, headers=headers, json=payload)
            except httpx.TimeoutException as e:
                raise weknora_timeout_error({"request_id": rid}) from e
            except httpx.RequestError as e:
                raise weknora_unavailable_error({"request_id": rid, "error": str(e)}) from e

        if resp.status_code in (401, 403):
            raise weknora_auth_error({"request_id": rid, "status_code": resp.status_code})

        if resp.status_code >= 500:
            raise weknora_unavailable_error({"request_id": rid, "status_code": resp.status_code})

        try:
            data = resp.json()
        except Exception as e:
            raise WeKnoraError(
                error_type="invalid_response",
                message="WeKnora response is not valid JSON",
                details={"request_id": rid, "status_code": resp.status_code},
            ) from e

        if not isinstance(data, dict) or data.get("success") is not True:
            raise WeKnoraError(
                error_type="invalid_response",
                message="WeKnora response unexpected (expected success=true)",
                details={"request_id": rid, "status_code": resp.status_code, "payload": data},
            )

        raw_items = data.get("data")
        if raw_items is None:
            return []
        if not isinstance(raw_items, list):
            raise WeKnoraError(
                error_type="invalid_response",
                message="WeKnora response unexpected (expected data as list)",
                details={"request_id": rid, "status_code": resp.status_code, "payload": data},
            )

        results: list[WeKnoraSearchResult] = []
        for item in raw_items:
            if not isinstance(item, dict):
                continue

            item_id = item.get("id")
            content = item.get("content")
            score = item.get("score")
            if not isinstance(item_id, str) or not isinstance(content, str) or not isinstance(score, (int, float)):
                continue

            results.append(
                WeKnoraSearchResult(
                    id=item_id,
                    content=content,
                    score=float(score),
                    knowledge_id=item.get("knowledge_id") if isinstance(item.get("knowledge_id"), str) else None,
                    knowledge_title=item.get("knowledge_title")
                    if isinstance(item.get("knowledge_title"), str)
                    else None,
                    chunk_index=item.get("chunk_index") if isinstance(item.get("chunk_index"), int) else None,
                    metadata=item.get("metadata") if isinstance(item.get("metadata"), dict) else None,
                )
            )

        if top_k is not None and top_k > 0:
            results = results[:top_k]

        return results

    async def list_knowledge_bases(
        self,
        *,
        request_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """获取 KnowledgeBase 列表"""
        rid = request_id or str(uuid.uuid4())

        headers = {
            "Accept": "application/json",
            "X-API-Key": self._api_key,
            "X-Request-ID": rid,
        }

        url = self._api_base + "/knowledge-bases"

        async with httpx.AsyncClient(timeout=self._timeout, transport=self._transport) as client:
            try:
                resp = await client.get(url, headers=headers)
            except httpx.TimeoutException as e:
                raise weknora_timeout_error({"request_id": rid}) from e
            except httpx.RequestError as e:
                raise weknora_unavailable_error({"request_id": rid, "error": str(e)}) from e

        if resp.status_code in (401, 403):
            raise weknora_auth_error({"request_id": rid, "status_code": resp.status_code})

        if resp.status_code >= 500:
            raise weknora_unavailable_error({"request_id": rid, "status_code": resp.status_code})

        try:
            data = resp.json()
        except Exception as e:
            raise WeKnoraError(
                error_type="invalid_response",
                message="WeKnora response is not valid JSON",
                details={"request_id": rid, "status_code": resp.status_code},
            ) from e

        if not isinstance(data, dict) or data.get("success") is not True:
            raise WeKnoraError(
                error_type="invalid_response",
                message="WeKnora response unexpected (expected success=true)",
                details={"request_id": rid, "status_code": resp.status_code, "payload": data},
            )

        kb_list = data.get("data")
        if not isinstance(kb_list, list):
            return []
        return kb_list

    async def create_knowledge_base(
        self,
        *,
        name: str,
        description: str | None = None,
        request_id: str | None = None,
    ) -> dict[str, Any]:
        """创建 KnowledgeBase"""
        rid = request_id or str(uuid.uuid4())

        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "X-API-Key": self._api_key,
            "X-Request-ID": rid,
        }

        payload: dict[str, Any] = {"name": name}
        if description:
            payload["description"] = description

        url = self._api_base + "/knowledge-bases"

        async with httpx.AsyncClient(timeout=self._timeout, transport=self._transport) as client:
            try:
                resp = await client.post(url, headers=headers, json=payload)
            except httpx.TimeoutException as e:
                raise weknora_timeout_error({"request_id": rid}) from e
            except httpx.RequestError as e:
                raise weknora_unavailable_error({"request_id": rid, "error": str(e)}) from e

        if resp.status_code in (401, 403):
            raise weknora_auth_error({"request_id": rid, "status_code": resp.status_code})

        if resp.status_code >= 500:
            raise weknora_unavailable_error({"request_id": rid, "status_code": resp.status_code})

        try:
            data = resp.json()
        except Exception as e:
            raise WeKnoraError(
                error_type="invalid_response",
                message="WeKnora response is not valid JSON",
                details={"request_id": rid, "status_code": resp.status_code},
            ) from e

        if not isinstance(data, dict) or data.get("success") is not True:
            raise WeKnoraError(
                error_type="invalid_response",
                message="WeKnora response unexpected (expected success=true)",
                details={"request_id": rid, "status_code": resp.status_code, "payload": data},
            )

        return data.get("data", {})

    async def create_ingestion(
        self,
        *,
        kb_id: str,
        source_type: str,
        source_payload: dict[str, Any],
        request_id: str | None = None,
    ) -> dict[str, Any]:
        """创建导入任务（ingestion job）"""
        rid = request_id or str(uuid.uuid4())

        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "X-API-Key": self._api_key,
            "X-Request-ID": rid,
        }

        payload: dict[str, Any] = {
            "kb_id": kb_id,
            "source_type": source_type,
            "source_payload": source_payload,
        }

        url = self._api_base + "/ingestions"

        async with httpx.AsyncClient(timeout=self._timeout, transport=self._transport) as client:
            try:
                resp = await client.post(url, headers=headers, json=payload)
            except httpx.TimeoutException as e:
                raise weknora_timeout_error({"request_id": rid}) from e
            except httpx.RequestError as e:
                raise weknora_unavailable_error({"request_id": rid, "error": str(e)}) from e

        if resp.status_code in (401, 403):
            raise weknora_auth_error({"request_id": rid, "status_code": resp.status_code})

        if resp.status_code >= 500:
            raise weknora_unavailable_error({"request_id": rid, "status_code": resp.status_code})

        try:
            data = resp.json()
        except Exception as e:
            raise WeKnoraError(
                error_type="invalid_response",
                message="WeKnora response is not valid JSON",
                details={"request_id": rid, "status_code": resp.status_code},
            ) from e

        if not isinstance(data, dict) or data.get("success") is not True:
            raise WeKnoraError(
                error_type="invalid_response",
                message="WeKnora response unexpected (expected success=true)",
                details={"request_id": rid, "status_code": resp.status_code, "payload": data},
            )

        return data.get("data", {})

    async def get_ingestion(
        self,
        *,
        ingestion_job_id: str,
        request_id: str | None = None,
    ) -> dict[str, Any]:
        """获取导入任务状态"""
        rid = request_id or str(uuid.uuid4())

        headers = {
            "Accept": "application/json",
            "X-API-Key": self._api_key,
            "X-Request-ID": rid,
        }

        url = f"{self._api_base}/ingestions/{ingestion_job_id}"

        async with httpx.AsyncClient(timeout=self._timeout, transport=self._transport) as client:
            try:
                resp = await client.get(url, headers=headers)
            except httpx.TimeoutException as e:
                raise weknora_timeout_error({"request_id": rid}) from e
            except httpx.RequestError as e:
                raise weknora_unavailable_error({"request_id": rid, "error": str(e)}) from e

        if resp.status_code == 404:
            raise WeKnoraError(
                error_type="not_found",
                message="Ingestion job not found",
                details={"request_id": rid, "ingestion_job_id": ingestion_job_id},
            )

        if resp.status_code in (401, 403):
            raise weknora_auth_error({"request_id": rid, "status_code": resp.status_code})

        if resp.status_code >= 500:
            raise weknora_unavailable_error({"request_id": rid, "status_code": resp.status_code})

        try:
            data = resp.json()
        except Exception as e:
            raise WeKnoraError(
                error_type="invalid_response",
                message="WeKnora response is not valid JSON",
                details={"request_id": rid, "status_code": resp.status_code},
            ) from e

        if not isinstance(data, dict) or data.get("success") is not True:
            raise WeKnoraError(
                error_type="invalid_response",
                message="WeKnora response unexpected (expected success=true)",
                details={"request_id": rid, "status_code": resp.status_code, "payload": data},
            )

        return data.get("data", {})
