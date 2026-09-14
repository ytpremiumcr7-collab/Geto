FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       gcc g++ \
       libpq-dev \
       gdal-bin \
       libgdal-dev \
       python3-gdal \
    && rm -rf /var/lib/apt/lists/*

# Ensure GDAL headers visible for pip gdal / rasterio wheels
ENV GDAL_CONFIG=/usr/bin/gdal-config
ENV CPLUS_INCLUDE_PATH=/usr/include/gdal
ENV C_INCLUDE_PATH=/usr/include/gdal

WORKDIR /app

COPY pyproject.toml README.md requirements.lock.txt ./
COPY app ./app
COPY migrations ./migrations
COPY alembic.ini ./
COPY scripts ./scripts
COPY samples ./samples

RUN python -m pip install --no-cache-dir -U pip setuptools wheel \
    && python -m pip install --no-cache-dir -r requirements.lock.txt \
    && python -m pip install --no-cache-dir -e ".[dev]" \
    && (pip install --no-cache-dir gdal==$(gdal-config --version) || pip install --no-cache-dir gdal || true) \
    && python -c "from osgeo import gdal; print('GDAL', gdal.__version__)" \
    && python -c "import rasterio; print('rasterio OK')"

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
