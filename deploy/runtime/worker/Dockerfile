FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app:/app/packages/ccdash_contracts/src

WORKDIR /app

COPY backend/requirements.txt ./backend/requirements.txt
RUN python -m pip install --upgrade pip && \
    python -m pip install -r backend/requirements.txt

COPY backend ./backend
COPY packages/ccdash_contracts ./packages/ccdash_contracts

EXPOSE 9465

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:9465/readyz', timeout=3)"

CMD ["python", "-m", "backend.worker"]
