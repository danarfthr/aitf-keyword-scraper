FROM python:3.11-slim

WORKDIR /app

ENV PYTHONPATH=/app

COPY shared/pyproject.toml /app/shared/pyproject.toml
RUN pip install --no-cache-dir --upgrade pip setuptools wheel sqlalchemy[asyncio] asyncpg psycopg2-binary python-dotenv

COPY shared /app/shared

RUN pip install --no-cache-dir loguru httpx beautifulsoup4 crawl4ai lxml pandas html5lib && \
    playwright install chromium --with-deps

COPY services/scraper /app/services/scraper

CMD ["python", "-m", "services.scraper.main"]
