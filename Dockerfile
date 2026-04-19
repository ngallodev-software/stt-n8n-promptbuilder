FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends bash ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY promptforge_services ./promptforge_services
COPY promptforge_watcher ./promptforge_watcher
COPY scripts ./scripts

RUN pip install --no-cache-dir .
RUN chmod +x /app/scripts/*.sh

EXPOSE 8090

CMD ["python", "-m", "promptforge_services"]
