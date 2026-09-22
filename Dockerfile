# F1Grid API - inference-only service (reads pre-built artifacts committed to
# the repo; does not run FastF1 ingestion itself).
FROM python:3.12-slim

# Deployment mode ON by default in the image: publish/score are refused, since a
# container's storage is ephemeral and publicly reachable. Read-only endpoints
# work normally. Override with -e F1GRID_DEPLOYED=0 only for local experiments.
ENV F1GRID_DEPLOYED=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000

WORKDIR /srv

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY f1grid/ f1grid/
COPY api/ api/
COPY tests/synthetic.py tests/__init__.py tests/
COPY artifacts/ artifacts/

# Run as a non-root user.
RUN useradd --create-home --uid 10001 appuser \
    && chown -R appuser:appuser /srv
USER appuser

# Deploy platforms (Railway/Render) inject $PORT; default to 8000 locally. Shell
# form so ${PORT} is expanded at runtime.
EXPOSE 8000
CMD ["sh", "-c", "uvicorn api.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
