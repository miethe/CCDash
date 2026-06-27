# ── Stage 1: dependency builder ─────────────────────────────────────────────
FROM python:3.12-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PATH=/opt/venv/bin:$PATH

WORKDIR /app

COPY backend/requirements.txt ./backend/requirements.txt
RUN python -m venv /opt/venv && \
    python -m pip install --upgrade pip && \
    python -m pip install -r backend/requirements.txt

# ── Stage 2: shared runtime base ────────────────────────────────────────────
# Non-root user (uid/gid configurable for bind-mount UID alignment).
# Includes all application code + contracts package.
FROM python:3.12-slim AS runtime

ARG BUILD_UID=1000
ARG BUILD_GID=1000

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app:/app/packages/ccdash_contracts/src \
    PATH=/opt/venv/bin:$PATH

WORKDIR /app

RUN groupadd --gid "${BUILD_GID}" ccdash && \
    useradd \
      --uid "${BUILD_UID}" \
      --gid "${BUILD_GID}" \
      --create-home \
      --home-dir /home/ccdash \
      --shell /usr/sbin/nologin \
      ccdash

COPY --from=builder /opt/venv /opt/venv
COPY --chown=ccdash:ccdash backend ./backend
COPY --chown=ccdash:ccdash packages/ccdash_contracts ./packages/ccdash_contracts
COPY --chown=ccdash:ccdash deploy/runtime/entrypoint.sh ./deploy/runtime/entrypoint.sh

# WORKDIR /app is created root-owned by the WORKDIR directive; ensure the
# non-root runtime user can seed runtime artifacts (e.g. projects.json) at the
# project root. Without this, rootless Podman + UID 1000 fails with
# PermissionError: [Errno 13] Permission denied: '/app/projects.json'.
RUN chown ccdash:ccdash /app

USER ccdash:ccdash

EXPOSE 8000 9465

# Default healthcheck: routes based on CCDASH_RUNTIME_PROFILE.
# The api and worker named targets below override this with explicit paths.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import os, urllib.request; profile=os.getenv('CCDASH_RUNTIME_PROFILE', '').strip(); url='http://127.0.0.1:9465/readyz' if profile == 'worker' else 'http://127.0.0.1:8000/readyz' if profile in {'local', 'api'} else None; assert url, f'unsupported CCDASH_RUNTIME_PROFILE={profile!r}'; urllib.request.urlopen(url, timeout=3)"

ENTRYPOINT ["/app/deploy/runtime/entrypoint.sh"]

# ── Stage 3a: api target ─────────────────────────────────────────────────────
# Runs uvicorn in the `api` runtime profile. /readyz on :8000 is the health gate.
# Build: docker build --target api -t ccdash-api .
# Run:   docker run -e CCDASH_RUNTIME_PROFILE=api -p 8000:8000 ccdash-api
FROM runtime AS api

ENV CCDASH_RUNTIME_PROFILE=api

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=5 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/readyz', timeout=4)"

CMD ["python", "-m", "uvicorn", "backend.runtime.bootstrap_api:app", \
     "--host", "0.0.0.0", "--port", "8000"]

# ── Stage 3b: worker target ──────────────────────────────────────────────────
# Runs the background worker (no HTTP API server). /readyz on :9465 is the probe.
# Build: docker build --target worker -t ccdash-worker .
# Run:   docker run -e CCDASH_RUNTIME_PROFILE=worker -p 9465:9465 ccdash-worker
FROM runtime AS worker

ENV CCDASH_RUNTIME_PROFILE=worker

EXPOSE 9465

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:9465/readyz', timeout=4)"

CMD ["python", "-m", "backend.worker"]
