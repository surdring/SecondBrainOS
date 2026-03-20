from __future__ import annotations

import os
from pathlib import Path
from redis import Redis
from rq import Queue
from sbo_core.jobs import return_one


def _load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        if "=" not in s:
            continue
        k, v = s.split("=", 1)
        k = k.strip()
        v = v.strip().strip('"').strip("'")
        if k and k not in os.environ:
            os.environ[k] = v


def main() -> None:
    _load_env_file(Path(__file__).resolve().parents[1] / ".env")
    redis_url = os.environ.get("REDIS_URL")
    if not redis_url:
        raise RuntimeError("Missing required env var: REDIS_URL")

    queue_name = os.environ.get("RQ_QUEUE_NAME", "sbo_default")

    r = Redis.from_url(redis_url)
    try:
        ok = r.ping()
    except Exception as e:
        raise RuntimeError(
            "Redis connection failed. Verify REDIS_URL in backend/.env. If Redis requires auth, use format: redis://:password@host:port/0"
        ) from e

    if not ok:
        raise RuntimeError("Redis ping failed")

    q = Queue(queue_name, connection=r)
    try:
        job = q.enqueue(return_one)
    except Exception as e:
        raise RuntimeError("RQ enqueue failed. Verify Redis permissions and that RQ can write to the selected DB.") from e
    if not job.id:
        raise RuntimeError("RQ enqueue failed")


if __name__ == "__main__":
    main()
