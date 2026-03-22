from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Request

from sbo_core.audit import audit_log
from sbo_core.config import load_settings
from sbo_core.database import get_database
from sbo_core.errors import AppError, ErrorCode, get_request_id
from sbo_core.feedback_service import feedback_service
from sbo_core.manage_service import forget_service
from sbo_core.models import (
    EraseJobResponse,
    ForgetRequest,
    ForgetResponse,
    ProfileUpdateRequest,
    UserProfile,
    FeedbackRequest,
    FeedbackResponse,
)
from sbo_core.neo4j_graph import get_driver
from sbo_core.rq import get_queue, get_redis
from sbo_core.services import user_profile_service


_logger = logging.getLogger("sbo_core")
router = APIRouter(prefix="/api/v1", tags=["manage"])


_DEFAULT_USER_ID = "00000000-0000-0000-0000-000000000000"


def _parse_dt(value: object) -> datetime:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value
    if isinstance(value, str) and value:
        try:
            dt = datetime.fromisoformat(value)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except Exception:
            return datetime.now(timezone.utc)
    return datetime.now(timezone.utc)


@router.post("/forget", response_model=ForgetResponse)
async def forget(request: ForgetRequest, http_request: Request) -> ForgetResponse:
    try:
        user_id = _DEFAULT_USER_ID
        resp = await forget_service.create_forget_job(user_id=user_id, request=request)
        audit_log(
            event="forget.create",
            outcome="success",
            request_id=get_request_id(http_request),
            details={
                "user_id": user_id,
                "erase_job_id": str(resp.erase_job_id),
                "tags": request.tags,
                "event_ids_count": len(request.event_ids),
                "has_time_range": bool(request.time_range),
            },
        )
        return resp
    except AppError as e:
        audit_log(
            event="forget.create",
            outcome="fail",
            request_id=get_request_id(http_request),
            details={
                "code": e.code.value,
                "status_code": e.status_code,
            },
        )
        raise
    except Exception as e:
        _logger.exception(f"Unexpected error in forget: {e}")
        audit_log(
            event="forget.create",
            outcome="error",
            request_id=get_request_id(http_request),
        )
        raise AppError(code=ErrorCode.FORGET_FAILED, message="Unexpected error during forget", status_code=503)


@router.get("/forget/{erase_job_id}", response_model=EraseJobResponse)
async def get_forget_status(erase_job_id: UUID, http_request: Request) -> EraseJobResponse:
    try:
        resp = await forget_service.get_forget_job(erase_job_id=erase_job_id)
        audit_log(
            event="forget.status",
            outcome="success",
            request_id=get_request_id(http_request),
            details={
                "erase_job_id": str(erase_job_id),
                "status": resp.status.value,
            },
        )
        return resp
    except AppError as e:
        audit_log(
            event="forget.status",
            outcome="fail",
            request_id=get_request_id(http_request),
            details={
                "erase_job_id": str(erase_job_id),
                "code": e.code.value,
                "status_code": e.status_code,
            },
        )
        raise
    except Exception as e:
        _logger.exception(f"Unexpected error in get_forget_status: {e}")
        audit_log(
            event="forget.status",
            outcome="error",
            request_id=get_request_id(http_request),
            details={
                "erase_job_id": str(erase_job_id),
            },
        )
        raise AppError(code=ErrorCode.ERASE_JOB_FAILED, message="Unexpected error during get forget status", status_code=503)


@router.get("/profile", response_model=UserProfile)
async def get_profile(http_request: Request) -> UserProfile:
    try:
        user_id = _DEFAULT_USER_ID
        payload = await user_profile_service.get_profile(user_id)
        resp = UserProfile(
            user_id=UUID(payload["user_id"]) if isinstance(payload.get("user_id"), str) else payload["user_id"],
            facts=payload.get("facts") or {},
            preferences=payload.get("preferences") or {},
            constraints=payload.get("constraints") or {},
            version=int(payload.get("version") or 1),
            updated_at=_parse_dt(payload.get("updated_at")),
        )
        audit_log(
            event="profile.get",
            outcome="success",
            request_id=get_request_id(http_request),
            details={
                "user_id": user_id,
                "version": resp.version,
            },
        )
        return resp
    except AppError as e:
        audit_log(
            event="profile.get",
            outcome="fail",
            request_id=get_request_id(http_request),
            details={
                "code": e.code.value,
                "status_code": e.status_code,
            },
        )
        raise
    except Exception as e:
        _logger.exception(f"Unexpected error in get_profile: {e}")
        audit_log(
            event="profile.get",
            outcome="error",
            request_id=get_request_id(http_request),
        )
        raise AppError(code=ErrorCode.PROFILE_NOT_FOUND, message="Unexpected error during get profile", status_code=503)


@router.put("/profile", response_model=UserProfile)
async def update_profile(request: ProfileUpdateRequest, http_request: Request) -> UserProfile:
    try:
        user_id = _DEFAULT_USER_ID
        payload = await user_profile_service.update_profile(
            user_id,
            facts=request.facts,
            preferences=request.preferences,
            constraints=request.constraints,
        )
        resp = UserProfile(
            user_id=UUID(payload["user_id"]) if isinstance(payload.get("user_id"), str) else payload["user_id"],
            facts=payload.get("facts") or {},
            preferences=payload.get("preferences") or {},
            constraints=payload.get("constraints") or {},
            version=int(payload.get("version") or 1),
            updated_at=_parse_dt(payload.get("updated_at")),
        )
        audit_log(
            event="profile.update",
            outcome="success",
            request_id=get_request_id(http_request),
            details={
                "user_id": user_id,
                "version": resp.version,
                "facts_keys": sorted(list(request.facts.keys())),
                "preferences_keys": sorted(list(request.preferences.keys())),
                "constraints_keys": sorted(list(request.constraints.keys())),
            },
        )
        return resp
    except AppError as e:
        audit_log(
            event="profile.update",
            outcome="fail",
            request_id=get_request_id(http_request),
            details={
                "code": e.code.value,
                "status_code": e.status_code,
            },
        )
        raise
    except Exception as e:
        _logger.exception(f"Unexpected error in update_profile: {e}")
        audit_log(
            event="profile.update",
            outcome="error",
            request_id=get_request_id(http_request),
        )
        raise AppError(code=ErrorCode.PROFILE_UPDATE_FAILED, message="Unexpected error during update profile", status_code=503)


@router.get("/health")
async def health(http_request: Request) -> dict[str, object]:
    settings = load_settings()

    postgres_ok = False
    postgres_details: dict[str, object] = {}
    try:
        db = get_database()
        dialect = getattr(db.engine, "dialect", None)
        dialect_name = getattr(dialect, "name", None)
        postgres_details["dialect"] = dialect_name
        with db.engine.connect() as conn:
            conn.exec_driver_sql("SELECT 1")
        postgres_ok = True
    except Exception as e:
        postgres_details["error"] = str(e)

    redis_ok = False
    redis_details: dict[str, object] = {}
    queue_details: dict[str, object] = {"name": settings.rq_queue_name}
    try:
        redis = get_redis(settings)
        redis.ping()
        redis_ok = True
        q = get_queue(settings)
        queue_details["size"] = q.count
    except Exception as e:
        redis_details["error"] = str(e)
        queue_details["size"] = None

    neo4j_details: dict[str, object] = {"enabled": bool(settings.neo4j_enable)}
    neo4j_ok: bool | None
    if not settings.neo4j_enable:
        neo4j_ok = None
    else:
        neo4j_ok = False
        try:
            driver = get_driver(settings)
            try:
                driver.verify_connectivity()
            finally:
                driver.close()
            neo4j_ok = True
        except Exception as e:
            neo4j_details["error"] = str(e)

    deps_ok = postgres_ok and redis_ok and (neo4j_ok in (True, None))
    status = "ok" if deps_ok else "degraded"

    resp: dict[str, object] = {
        "status": status,
        "dependencies": {
            "postgres": {"ok": postgres_ok, **postgres_details},
            "redis": {"ok": redis_ok, **redis_details},
            "neo4j": {"ok": neo4j_ok, **neo4j_details},
        },
        "queue": queue_details,
    }

    audit_log(
        event="health.check",
        outcome="success" if deps_ok else "degraded",
        request_id=get_request_id(http_request),
        details={
            "postgres_ok": postgres_ok,
            "redis_ok": redis_ok,
            "neo4j_ok": neo4j_ok,
            "queue_size": queue_details.get("size"),
        },
    )

    return resp


@router.post("/feedback", response_model=FeedbackResponse)
async def create_feedback(request: FeedbackRequest, http_request: Request) -> FeedbackResponse:
    """
    反馈纠错接口

    该接口用于用户对检索证据进行反馈纠错，支持类型：
    - incorrect: 证据不正确
    - outdated: 证据已过时
    - incomplete: 证据不完整

    反馈会被记录并用于后续检索优化（incorrect/outdated 证据会被过滤）。
    """
    try:
        user_id = _DEFAULT_USER_ID
        resp = await feedback_service.create_feedback(user_id=user_id, request=request)
        audit_log(
            event="feedback.create",
            outcome="success",
            request_id=get_request_id(http_request),
            details={
                "user_id": user_id,
                "feedback_id": str(resp.feedback_id),
                "evidence_id": request.evidence_id,
                "feedback_type": request.feedback_type,
            },
        )
        return resp
    except AppError as e:
        audit_log(
            event="feedback.create",
            outcome="fail",
            request_id=get_request_id(http_request),
            details={
                "code": e.code.value,
                "status_code": e.status_code,
            },
        )
        raise
    except Exception as e:
        _logger.exception(f"Unexpected error in create_feedback: {e}")
        audit_log(
            event="feedback.create",
            outcome="error",
            request_id=get_request_id(http_request),
        )
        raise AppError(code=ErrorCode.FEEDBACK_FAILED, message="Unexpected error during feedback creation", status_code=503)
