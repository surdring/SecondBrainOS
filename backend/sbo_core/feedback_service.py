from __future__ import annotations

import uuid
from typing import Any

from sbo_core.database import EvidenceFeedback, get_database
from sbo_core.errors import AppError, ErrorCode
from sbo_core.models import FeedbackRequest, FeedbackResponse


class FeedbackService:
    def __init__(self) -> None:
        self.db = None

    def _get_db(self):
        if self.db is None:
            self.db = get_database()
        return self.db

    async def create_feedback(self, *, user_id: str | None, request: FeedbackRequest) -> FeedbackResponse:
        db = self._get_db()
        session = db.get_session()

        try:
            row = EvidenceFeedback(
                id=uuid.uuid4(),
                user_id=user_id,
                evidence_id=request.evidence_id,
                feedback_type=request.feedback_type,
                user_correction=request.user_correction,
                session_id=str(request.session_id) if request.session_id is not None else None,
                query=request.query,
                payload={
                    "evidence_id": request.evidence_id,
                    "feedback_type": request.feedback_type,
                    "user_correction": request.user_correction,
                    "session_id": str(request.session_id) if request.session_id is not None else None,
                    "query": request.query,
                },
            )
            session.add(row)
            session.commit()
            session.refresh(row)

            return FeedbackResponse(feedback_id=row.id, status="received")
        except Exception as e:
            session.rollback()
            if isinstance(e, AppError):
                raise
            raise AppError(code=ErrorCode.FEEDBACK_FAILED, message=f"Failed to create feedback: {str(e)}", status_code=503)
        finally:
            session.close()


feedback_service = FeedbackService()
