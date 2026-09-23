"""Optional: poll the Drive input folder on an interval.

With this enabled the service is fully self-contained: nothing has to call it.
Drop a CV in the input folder, the JSON appears in the output folder.
"""
import logging
import time

from app.core.config import settings
from app.core.logging import setup_logging
from app.tasks import scan_folder

log = logging.getLogger(__name__)


def main() -> None:
    setup_logging()
    if not settings.poll_enabled:
        log.info("poller disabled (POLL_ENABLED=false); idling")
        while True:
            time.sleep(3600)
    log.info("poller started, interval=%ss", settings.poll_interval_seconds)
    while True:
        try:
            result = scan_folder({})
            if result["queued"]:
                log.info("scan queued %s file(s)", result["queued"])
        except Exception as e:  # noqa: BLE001
            log.exception("scan failed: %s", e)
        time.sleep(settings.poll_interval_seconds)


if __name__ == "__main__":
    main()
