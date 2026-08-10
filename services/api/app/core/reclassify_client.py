"""API-side client for triggering `reclassify_transactions`, which lives in
`services/ingestion/app/transform.py`.

Per the sprint doc's boundary question ("you'll need to either expose it via
a shared mechanism the API can call ... or decide the cleanest way to invoke
it from an API endpoint"): `services/api` and `services/ingestion` are
separate Docker images with no shared application code (only the tiny
`services/common` package -- see both Dockerfiles), so importing
`services.ingestion.app.transform` directly from the API process is not an
option without a cross-package coupling the project's architecture doesn't
otherwise have.

Chosen approach: enqueue the existing `eparking.ingest.reclassify` Celery
task (defined in `services/ingestion/app/tasks/ingest.py`, wrapping
`reclassify_transactions` + `rebuild_daily_revenue` + cache invalidation) via
`celery_app.send_task(name, args=...)` against the *same broker* (shared
Redis, already the project's shared infrastructure). `send_task` dispatches
by task name string alone -- it does not need to import the task's Python
module -- so this stays a pure "same broker, different process" hookup, the
same pattern already used for the API and ingestion sharing one Postgres.

This module deliberately does not create/manage a full Celery `Celery(...)`
app with beat schedules or worker config -- just enough of a client to call
`send_task` and (optionally) poll a result via the shared result backend.
"""

from __future__ import annotations

from celery import Celery

from eparking_common.config import get_settings

_RECLASSIFY_TASK_NAME = "eparking.ingest.reclassify"

_client: Celery | None = None


def get_celery_client() -> Celery:
    """Lazily-constructed minimal Celery client bound to the shared broker.

    Not part of the FastAPI lifespan (unlike the DB pool/Redis client)
    because a Celery client object is cheap and stateless beyond its broker
    URL -- no connection pool to leak, no explicit close needed at shutdown.
    """
    global _client
    if _client is None:
        settings = get_settings()
        _client = Celery(
            "eparking_api_reclassify_client",
            broker=settings.resolved_celery_broker_url,
            backend=settings.resolved_celery_result_backend,
        )
        _client.conf.update(task_serializer="json", accept_content=["json"], result_serializer="json")
    return _client


def enqueue_reclassify(*, from_date_iso: str, to_date_iso: str, reason: str) -> str:
    """Enqueue the ingestion service's reclassify task. Returns the Celery
    task id (not the same as the `run_logs.id` -- the run_logs row is
    created inside the task once it actually starts executing, so it isn't
    known at enqueue time; callers that need to correlate should poll
    `run_logs` for the most recent row in the target date window, or use the
    Celery task id with a result-backend lookup)."""
    client = get_celery_client()
    async_result = client.send_task(
        _RECLASSIFY_TASK_NAME,
        args=[from_date_iso, to_date_iso, reason],
    )
    return async_result.id
