"""Trivial smoke-test task confirming the worker/beat wiring works.

Not part of the dashboard pipeline -- delete once Sprint 3 adds real tasks
if it's no longer useful, or keep as a lightweight liveness probe task.
"""

from __future__ import annotations

from app.celery_app import celery_app


@celery_app.task(name="eparking.ping")
def ping() -> str:
    return "pong"
