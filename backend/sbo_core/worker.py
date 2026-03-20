from __future__ import annotations

import os

from redis import Redis
from rq import Connection, Worker


def run_worker() -> None:
    redis_url = os.environ.get("REDIS_URL")
    if not redis_url:
        raise RuntimeError("Missing required env var: REDIS_URL")

    queue_name = os.environ.get("RQ_QUEUE_NAME", "sbo_default")

    conn = Redis.from_url(redis_url)
    with Connection(conn):
        worker = Worker([queue_name])
        worker.work(with_scheduler=False)


if __name__ == "__main__":
    run_worker()
