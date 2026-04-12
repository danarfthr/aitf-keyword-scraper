FROM python:3.11-slim

WORKDIR /app

ENV PYTHONPATH=/app

# Install shared package dependencies first
COPY shared/pyproject.toml /app/shared/pyproject.toml
RUN pip install --no-cache-dir --upgrade pip setuptools wheel sqlalchemy[asyncio] asyncpg psycopg2-binary python-dotenv

COPY shared /app/shared

RUN pip install --no-cache-dir loguru fastapi "uvicorn[standard]" pydantic httpx beautifulsoup4 crawl4ai lxml pandas html5lib

COPY services/scraper /app/services/scraper
COPY services/api /app/services/api

EXPOSE 8000

CMD ["uvicorn", "services.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
