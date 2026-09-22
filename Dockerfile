# F1Grid API — inference-only service (reads pre-built artifacts committed to
# the repo or mounted as a volume; does not run FastF1 ingestion itself).
FROM python:3.11-slim

WORKDIR /srv

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY f1grid/ f1grid/
COPY api/ api/
COPY tests/synthetic.py tests/__init__.py tests/
COPY artifacts/ artifacts/

EXPOSE 8000
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
