FROM python:3.12-slim

WORKDIR /srv

COPY services/common /srv/services/common
COPY services/ingestion/requirements.txt /srv/services/ingestion/requirements.txt

RUN pip install --no-cache-dir -r /srv/services/ingestion/requirements.txt \
    && pip install --no-cache-dir -e /srv/services/common

COPY services/ingestion /srv/services/ingestion

WORKDIR /srv/services/ingestion

ENV PYTHONUNBUFFERED=1 \
    PYTHONPATH=/srv/services/ingestion

# Default command is overridden per-service in docker-compose.yml
# (worker / beat / migrate all share this image).
CMD ["celery", "-A", "app.celery_app", "worker", "--loglevel=INFO"]
