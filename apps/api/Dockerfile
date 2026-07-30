FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install dependencies first for better layer caching.
COPY pyproject.toml ./
RUN pip install --upgrade pip && pip install .

# Application source + migrations.
COPY . .
RUN pip install . --no-deps

# Non-root runtime user.
RUN useradd --create-home --uid 10001 sokola

# Document uploads land in SOKOLA_DOCUMENTS_STORAGE_DIR (default var/documents,
# i.e. /app/var/documents). /app itself is root-owned, so the directory has to
# exist and be owned by the runtime user or every upload fails with EACCES.
# Creating it here also fixes ownership for the named volume compose.prod.yml
# mounts over it: Docker seeds a fresh volume from the image path, ownership
# included.
RUN mkdir -p /app/var/documents && chown -R sokola:sokola /app/var

USER sokola

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
