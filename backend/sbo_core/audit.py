from __future__ import annotations

import logging
from typing import Any


_logger = logging.getLogger("sbo_core")


def audit_log(
    *,
    event: str,
    outcome: str,
    request_id: str | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    payload: dict[str, Any] = {
        "audit_event": event,
        "audit_outcome": outcome,
    }
    if request_id:
        payload["request_id"] = request_id
    if details:
        payload["audit_details"] = details

    _logger.info("audit", extra=payload)
