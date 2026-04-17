FROM python:3.11-slim

WORKDIR /app

ENV PYTHONPATH=/app

COPY shared/pyproject.toml /app/shared/pyproject.toml
RUN pip install --no-cache-dir --upgrade pip setuptools wheel sqlalchemy[asyncio] asyncpg psycopg2-binary python-dotenv

COPY shared /app/shared

RUN pip install --no-cache-dir loguru httpx

COPY services/llm /app/services/llm

CMD ["python", "-m", "services.llm.main"]
