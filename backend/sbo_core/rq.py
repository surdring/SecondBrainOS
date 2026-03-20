from __future__ import annotations

from redis import Redis
from rq import Queue

from sbo_core.config import Settings


def get_redis(settings: Settings) -> Redis:
    return Redis.from_url(settings.redis_url)


def get_queue(settings: Settings, name: str | None = None) -> Queue:
    queue_name = name or settings.rq_queue_name
    return Queue(queue_name, connection=get_redis(settings))
