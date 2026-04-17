FROM python:3.11-slim

WORKDIR /app

ENV PYTHONPATH=/app

# Install shared package dependencies first
COPY shared/pyproject.toml /app/shared/pyproject.toml
RUN pip install --no-cache-dir --upgrade pip setuptools wheel sqlalchemy[asyncio] asyncpg psycopg2-binary python-dotenv

COPY shared /app/shared

RUN pip install --no-cache-dir loguru fastapi "uvicorn[standard]" pydantic httpx alembic

COPY alembic /app/alembic
COPY alembic.ini /app/alembic.ini
COPY shared /app/shared

ENV DATABASE_URL_SYNC=postgresql+psycopg2://${POSTGRES_USER:-aitf}:${POSTGRES_PASSWORD:-change_me_in_production}@postgres:5432/${POSTGRES_DB:-aitf_keywords}

COPY services/api /app/services/api

EXPOSE 8000

CMD ["uvicorn", "services.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
