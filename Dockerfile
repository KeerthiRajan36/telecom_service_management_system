FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Unprivileged user: the API never needs root.
RUN useradd --create-home --uid 10001 appuser

# Dependencies first so this layer is cached until requirements.txt changes.
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY alembic.ini ./
COPY alembic ./alembic
COPY app ./app
COPY scripts ./scripts
COPY docker-entrypoint.sh ./
RUN chmod +x docker-entrypoint.sh && chown -R appuser:appuser /app

USER appuser
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4).status == 200 else 1)"

ENTRYPOINT ["./docker-entrypoint.sh"]
# Set WEB_CONCURRENCY to run multiple uvicorn worker processes (the entrypoint wires it in).
# NOTE: the built-in rate limiter's counters are per-process, so with >1 worker each process
# enforces the limit independently - fine for one host, not for multiple replicas behind a LB.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
