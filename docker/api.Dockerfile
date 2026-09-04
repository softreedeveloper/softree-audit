# syntax=docker/dockerfile:1
FROM python:3.12-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

# Dependencias nativas:
#   libpq5                → cliente PostgreSQL
#   libpango/cairo/gdk    → WeasyPrint, necesario a partir del Slice 10 (ADR-007)
RUN apt-get update && apt-get install -y --no-install-recommends \
        libpq5 \
        libpango-1.0-0 \
        libpangoft2-1.0-0 \
        libcairo2 \
        libgdk-pixbuf-2.0-0 \
        shared-mime-info \
        fonts-dejavu-core \
        curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Capa de dependencias: solo el manifiesto, para aprovechar la cache de Docker.
COPY apps/api/pyproject.toml apps/api/README.md ./
RUN mkdir -p softree_audit && touch softree_audit/__init__.py \
    && pip install --upgrade pip && pip install -e ".[dev]"

COPY apps/api/ ./
# Las pruebas viven en la raíz del repositorio (docs/spec/architecture.md §6).
COPY tests/ ./tests/

RUN useradd --create-home --uid 10001 softree \
    && mkdir -p /data/reports \
    && chown -R softree:softree /app /data/reports
USER softree

EXPOSE 8000

CMD ["uvicorn", "softree_audit.main:app", "--host", "0.0.0.0", "--port", "8000"]
