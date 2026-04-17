FROM python:3.11-slim

WORKDIR /app

ENV PYTHONPATH=/app
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

# Install system deps required by Chromium + undetected-chromedriver
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget gnupg ca-certificates curl \
    libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 \
    libcups2 libdrm2 libxkbcommon0 libxcomposite1 \
    libxdamage1 libxfixes3 libxrandr2 libgbm1 libpango-1.0-0 \
    libcairo2 libasound2 libatspi2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Install Playwright browsers (Chromium only)
RUN pip install --no-cache-dir playwright \
    && playwright install --with-deps chromium

# Install Crawl4AI
RUN pip install --no-cache-dir crawl4ai

COPY shared/pyproject.toml /app/shared/pyproject.toml
RUN pip install --no-cache-dir --upgrade pip setuptools wheel \
    sqlalchemy[asyncio] asyncpg psycopg2-binary python-dotenv loguru

COPY shared /app/shared

COPY services/sampler /app/services/sampler

CMD ["python", "-m", "services.sampler.main"]
