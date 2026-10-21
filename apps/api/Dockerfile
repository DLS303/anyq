# Production image. The existing CI job builds this file with:
#   docker build -t anyq-api:ci apps/api

FROM python:3.11-slim-bookworm AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /build
COPY requirements.txt .
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
RUN pip install --upgrade pip \
    && pip install -r requirements.txt "gunicorn==23.0.0" \
    && python -c "import cv2; from pathlib import Path; root = Path(cv2.data.haarcascades); assert (root / 'haarcascade_frontalface_default.xml').is_file(); assert (root / 'haarcascade_russian_plate_number.xml').is_file()"

FROM python:3.11-slim-bookworm AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    PORT=8010 \
    PYTHONPATH=/srv/anyq/apps/api \
    WEB_CONCURRENCY=2 \
    GUNICORN_TIMEOUT=120 \
    GUNICORN_GRACEFUL_TIMEOUT=30 \
    OMP_NUM_THREADS=1 \
    OPENBLAS_NUM_THREADS=1

# gosu is used by the entrypoint to drop root after the data volume is ready.
# libglib and libgomp are runtime libraries for opencv.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libglib2.0-0 libgomp1 gosu \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 10001 anyq \
    && useradd --uid 10001 --gid anyq --create-home --shell /usr/sbin/nologin anyq \
    && mkdir -p /data /app \
    && chown anyq:anyq /data

COPY --from=builder /opt/venv /opt/venv

# The application resolves the repository root as parents[3] of app/paths.py
# (repo/apps/api/app/paths.py). Keep that depth so the import succeeds.
WORKDIR /srv/anyq/apps/api
COPY app ./app
COPY alembic.ini ./alembic.ini
COPY alembic ./alembic
COPY scripts ./scripts
COPY docker-entrypoint.sh /usr/local/bin/anyq-api-entrypoint
RUN chmod 755 /usr/local/bin/anyq-api-entrypoint

EXPOSE 8010

HEALTHCHECK --interval=15s --timeout=5s --start-period=60s --retries=5 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8010/ready', timeout=3).read()"

ENTRYPOINT ["anyq-api-entrypoint"]
CMD ["gunicorn"]
