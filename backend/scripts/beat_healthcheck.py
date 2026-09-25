"""Docker healthcheck for the Celery beat container.

Celery beat has no ping. It touches a heartbeat file (core.celery_app,
``BEAT_HEARTBEAT_FILE``) whenever the broker accepted one of its tasks; the
notification outbox task is due every 10 seconds, so a heartbeat older than
``MAX_AGE_SECONDS`` means beat hangs or cannot reach the broker.

    python scripts/beat_healthcheck.py [/tmp/celerybeat-heartbeat]   # exit 1 = unhealthy
"""

import os
import sys
import time

DEFAULT_HEARTBEAT_FILE = "/tmp/celerybeat-heartbeat"
MAX_AGE_SECONDS = 120


def main(argv: list[str]) -> int:
    heartbeat = argv[1] if len(argv) > 1 else DEFAULT_HEARTBEAT_FILE
    try:
        age = time.time() - os.path.getmtime(heartbeat)
    except OSError:
        print(f"unhealthy: no heartbeat file {heartbeat} (beat has not sent a task yet)")
        return 1
    if age > MAX_AGE_SECONDS:
        print(f"unhealthy: beat has not sent a task for {age:.0f} s")
        return 1
    print(f"healthy: beat sent a task {age:.0f} s ago")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
