# Gunicorn config that embeds Celery worker in the same process
# This saves ~120MB by sharing Django's imported modules
# Only used in deploy (docker-compose.deploy.yml)

import threading
import os

EMBED_CELERY = os.environ.get("EMBED_CELERY", "0") == "1"
_celery_started = False


def post_fork(server, worker):
    """Start Celery worker thread after gunicorn forks a worker process."""
    global _celery_started
    if not EMBED_CELERY or _celery_started:
        return

    _celery_started = True

    def run_celery():
        from plane.celery import app

        # Run worker in solo pool (single-threaded, no fork)
        argv = [
            "worker",
            "--pool=solo",
            "--concurrency=1",
            "--max-memory-per-child=150000",
            "--loglevel=info",
            "--without-heartbeat",
            "--without-mingle",
            "--without-gossip",
        ]
        app.worker_main(argv)

    t = threading.Thread(target=run_celery, name="celery-worker", daemon=True)
    t.start()
    server.log.info("Embedded Celery worker started in background thread")
