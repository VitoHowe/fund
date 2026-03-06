FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Runtime dependencies only; no MCP runtime client required.
COPY pyproject.toml README.md /app/
COPY services /app/services
COPY scripts /app/scripts
COPY docs /app/docs
COPY apps /app/apps
COPY config /app/config
COPY infra /app/infra

RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir .

EXPOSE 8010

# Default command validates runtime independence and data hub connectivity baseline.
CMD ["sh", "-c", "python scripts/check_runtime_independence.py && python scripts/check_p1_data_hub.py"]
