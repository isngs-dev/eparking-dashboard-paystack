"""Celery application instance.

Sprint 3 populates the beat schedule with the Paystack ingestion tasks --
see .claude/sprints/03_INGESTION.md and .claude/skills/paystack-ingestion/.

Schedule (verified against the skill's schedule table):
    sync_recent      every 15 min, window = last 48h
    sync_reconcile   nightly,      window = last 35 days
    backfill / backfill_csv -- manual/parameterized only, deliberately NOT
        on the beat schedule.

No settlement-related task exists anywhere in this schedule -- settlement is
fully out of scope project-wide (see CLAUDE.md).
"""

from __future__ import annotations

from celery import Celery
from celery.schedules import crontab

from eparking_common.config import get_settings

settings = get_settings()

celery_app = Celery(
    "eparking_ingestion",
    broker=settings.resolved_celery_broker_url,
    backend=settings.resolved_celery_result_backend,
    # Explicit module list rather than autodiscover_tasks: autodiscover_tasks
    # is designed around Django-style installed-app names and appends
    # ".tasks" to each entry, so pointing it at "app.tasks" itself resolves
    # to the wrong module path. Explicit `include=` is the documented
    # approach for non-Django layouts.
    include=["app.tasks.ping", "app.tasks.ingest"],
    # Explicit task routing note: "eparking.ingest.reclassify" is defined in
    # app.tasks.ingest above and is enqueued both from this service's own
    # `.delay()`/beat schedule usage and, in Sprint 7, from services/api via
    # `send_task()` against this same broker -- no cross-package import
    # needed since Celery dispatches by task *name*, not by importing the
    # task function.
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    beat_schedule={
        "sync-recent-every-15-min": {
            "task": "eparking.ingest.sync_recent",
            "schedule": 15 * 60,
        },
        "sync-reconcile-nightly": {
            "task": "eparking.ingest.sync_reconcile",
            # 02:00 UTC -- off-peak, well clear of sync_recent's cadence.
            "schedule": crontab(hour=2, minute=0),
        },
        # backfill / backfill_csv are intentionally NOT scheduled here --
        # manual/parameterized only, per the sprint spec.
    },
)
