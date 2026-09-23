"""RQ worker entrypoint. Warms the OCR model before taking any job."""
from rq import Worker

from app.core.config import settings
from app.core.logging import setup_logging
from app.services import engine
from app.services.jobs import queue, redis_conn


def main() -> None:
    setup_logging()
    engine.warmup(settings.ocr_lang)
    Worker([queue], connection=redis_conn).work(with_scheduler=False)


if __name__ == "__main__":
    main()
