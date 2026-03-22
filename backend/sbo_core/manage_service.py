from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sbo_core.database import EraseJob, get_database
from sbo_core.errors import AppError, ErrorCode
from sbo_core.models import EraseJobResponse, EraseJobStatus, ForgetRequest, ForgetResponse


class ForgetService:
    def __init__(self) -> None:
        self.db = None

    def _get_db(self):
        if self.db is None:
            self.db = get_database()
        return self.db

    async def create_forget_job(self, *, user_id: str, request: ForgetRequest) -> ForgetResponse:
        db = self._get_db()
        session = db.get_session()

        try:
            time_range_start = None
            time_range_end = None
            if request.time_range:
                time_range_start = request.time_range.get("start")
                time_range_end = request.time_range.get("end")

            job = EraseJob(
                user_id=user_id,
                status=EraseJobStatus.QUEUED.value,
                time_range_start=time_range_start,
                time_range_end=time_range_end,
                tags=request.tags,
                event_ids=[str(eid) for eid in request.event_ids],
                affected_events=0,
                error_message=None,
                created_at=datetime.now(timezone.utc),
            )
            session.add(job)
            session.commit()
            session.refresh(job)

            return ForgetResponse(erase_job_id=job.id)
        except Exception as e:
            session.rollback()
            if isinstance(e, AppError):
                raise
            raise AppError(
                code=ErrorCode.FORGET_FAILED,
                message=f"Failed to create forget job: {str(e)}",
                status_code=503,
            )
        finally:
            session.close()

    async def get_forget_job(self, *, erase_job_id: UUID) -> EraseJobResponse:
        db = self._get_db()
        session = db.get_session()

        try:
            job = session.query(EraseJob).filter(EraseJob.id == erase_job_id).first()
            if not job:
                raise AppError(
                    code=ErrorCode.ERASE_JOB_NOT_FOUND,
                    message="Erase job not found",
                    status_code=404,
                )

            return EraseJobResponse(
                erase_job_id=job.id,
                status=EraseJobStatus(job.status),
                created_at=job.created_at,
                started_at=job.started_at,
                completed_at=job.completed_at,
                affected_events=job.affected_events or 0,
                error_message=job.error_message,
            )
        except Exception as e:
            if isinstance(e, AppError):
                raise
            raise AppError(
                code=ErrorCode.ERASE_JOB_FAILED,
                message=f"Failed to get forget job status: {str(e)}",
                status_code=503,
            )
        finally:
            session.close()


forget_service = ForgetService()
