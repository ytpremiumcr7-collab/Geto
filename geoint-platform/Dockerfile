FROM python:3.12.14-slim-bookworm AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    GDAL_CONFIG=/usr/bin/gdal-config \
    CPLUS_INCLUDE_PATH=/usr/include/gdal \
    C_INCLUDE_PATH=/usr/include/gdal

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       gcc \
       g++ \
       libpq-dev \
       libgdal-dev \
       gdal-bin \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

COPY pyproject.toml README.md requirements.lock.txt ./
COPY app ./app

RUN python -m venv /opt/venv \
    && /opt/venv/bin/python -m pip install --no-cache-dir --upgrade pip setuptools wheel \
    && /opt/venv/bin/python -m pip install --no-cache-dir --require-hashes -r requirements.lock.txt \
    && /opt/venv/bin/python -m pip install --no-cache-dir "gdal==$(gdal-config --version)" \
    && /opt/venv/bin/python -m pip install --no-cache-dir --no-deps . \
    && /opt/venv/bin/python -m pip uninstall -y \
       pytest pytest-asyncio pytest-cov respx ruff mypy bandit pip-audit coverage \
    && /opt/venv/bin/python -c "from osgeo import gdal; print('GDAL', gdal.__version__)" \
    && /opt/venv/bin/python -c "import rasterio; print('rasterio', rasterio.__version__)"

FROM python:3.12.14-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH=/opt/venv/bin:$PATH

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       ca-certificates \
       libpq5 \
       libgdal32 \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system --gid 10001 geoint \
    && useradd --system --uid 10001 --gid geoint --home-dir /nonexistent --shell /usr/sbin/nologin geoint

WORKDIR /app

COPY --from=builder /opt/venv /opt/venv
COPY --chown=geoint:geoint migrations ./migrations
COPY --chown=geoint:geoint alembic.ini ./
COPY --chown=geoint:geoint scripts ./scripts
COPY --chown=geoint:geoint samples ./samples

USER geoint

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
