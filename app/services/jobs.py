from redis import Redis
from rq import Queue
from rq.job import Job
from rq.exceptions import NoSuchJobError

from app.core.config import settings

redis_conn = Redis.from_url(settings.redis_url)
queue = Queue(
    "ocr",
    connection=redis_conn,
    default_timeout=settings.job_timeout_seconds,
)


def enqueue(func_path: str, payload: dict, job_id: str | None = None) -> str:
    job = queue.enqueue(
        func_path,
        payload,
        job_id=job_id,
        result_ttl=settings.job_ttl_seconds,
        failure_ttl=settings.job_ttl_seconds,
    )
    return job.id


def fetch(job_id: str) -> dict | None:
    try:
        job = Job.fetch(job_id, connection=redis_conn)
    except NoSuchJobError:
        return None
    return {
        "job_id": job.id,
        "status": job.get_status(),
        "result": job.result if job.is_finished else None,
        "error": (job.exc_info or "").strip().splitlines()[-1] if job.is_failed else None,
    }
