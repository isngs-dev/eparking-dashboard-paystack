FROM python:3.12-slim

WORKDIR /srv

# System deps for asyncpg/psycopg-style builds are not needed (asyncpg ships
# wheels), keep the image minimal.
COPY services/common /srv/services/common
COPY services/api/requirements.txt /srv/services/api/requirements.txt

RUN pip install --no-cache-dir -r /srv/services/api/requirements.txt \
    && pip install --no-cache-dir -e /srv/services/common

COPY services/api /srv/services/api

WORKDIR /srv/services/api

ENV PYTHONUNBUFFERED=1 \
    PYTHONPATH=/srv/services/api

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
