# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**AITF Keyword Manager v2** — Microservice pipeline that scrapes trending keywords from Google Trends and Trends24 Indonesia, samples relevant news articles via crawler, uses OpenRouter LLM to determine government relevance, and enriches relevant keywords with expanded search terms. Output consumed by Team 4 via REST API.

## Architecture

```
[API + FastAPI] → [Sampler] → [LLM Service] → [Expiry Job]
       ↓              ↓              ↓              ↓
   PostgreSQL    PostgreSQL     PostgreSQL     PostgreSQL
```

- **Stateless services**: All state lives in PostgreSQL only
- **Keyword lifecycle**: Driven by `status` column (raw → news_sampled → llm_justified → enriched → expired/failed)
- **Concurrency**: All polling queries use `SELECT FOR UPDATE SKIP LOCKED` to prevent race conditions
- **No standalone scraper container**: Scraper is a library imported by API as FastAPI BackgroundTask

## Key Commands

```bash
# Virtual environment
source .venv/bin/activate

# Database migrations (first time: alembic init alembic, then edit alembic/env.py first)
alembic revision --autogenerate -m "description"
alembic upgrade head

# Run single service
uvicorn services.api.main:app --host 127.0.0.1 --port 8000
python services/sampler/main.py
python services/llm/main.py
python services/expiry/main.py

# Run tests (all or single)
pytest tests/ -v
pytest tests/test_scraper.py::test_trends24_returns_list -v

# Docker
docker compose build
docker compose up -d
docker compose logs <service>
```

## Critical Patterns

### Import Path
The shared package uses a **nested structure**: `shared/shared/`
```python
from shared.shared.db import get_session
from shared.shared.models import Keyword, Article
from shared.shared.constants import KeywordStatus
```

### Database Setup
- Uses `asyncpg` for async SQLAlchemy 2.x
- `DATABASE_URL` for application code (asyncpg)
- `DATABASE_URL_SYNC` for Alembic only (psycopg2)

### Polling Pattern (mandatory)
```python
result = await session.execute(
    select(Keyword)
    .where(Keyword.status == KeywordStatus.RAW)
    .limit(batch_size)
    .with_for_update(skip_locked=True)  # REQUIRED
)
```

### Environment Variables
All read from `.env` via `python-dotenv`. Never hardcode. Key vars:
- `DATABASE_URL`, `DATABASE_URL_SYNC`
- `OPENROUTER_API_KEY`, `LLM_MODEL`
- `API_SECRET_KEY` (for X-API-Key header auth)

### Alembic Setup
`alembic/env.py` must:
- Read `DATABASE_URL_SYNC` (psycopg2) from environment
- Import `Base` from `shared.shared.models`
- Set `target_metadata = Base.metadata`
- Use synchronous psycopg2, not asyncpg

## Directory Structure

```
├── shared/
│   └── shared/           # Pip-installable package (import: shared.shared.*)
│       ├── constants.py  # KeywordStatus, sources, thresholds
│       ├── db.py         # async_engine, get_session
│       └── models.py     # SQLAlchemy ORM models
│
├── services/
│   ├── scraper/          # Library only (NO Dockerfile, NO container)
│   │   ├── trends24.py
│   │   ├── google_trends.py
│   │   └── delta.py
│   ├── sampler/          # Crawls detik/kompas/tribun news sites
│   ├── llm/             # OpenRouter justifier + enricher
│   ├── expiry/          # APScheduler cleanup job
│   ├── api/             # FastAPI REST API
│   └── demo/            # Streamlit read-only dashboard (radio-button nav via dashboard_pages/)
│
├── alembic/              # Database migrations
│   └── versions/
└── tests/               # pytest + pytest-asyncio
```

## Service Responsibilities

| Service | Polls For | Produces |
|---------|-----------|----------|
| API | — | Runs scraper as BackgroundTask |
| Sampler | `status=raw` | Articles, sets `status=news_sampled` |
| LLM (Justifier) | `status=news_sampled` | KeywordJustification, sets `status=llm_justified` |
| LLM (Enricher) | `status=llm_justified` + `is_relevant=true` | KeywordEnrichment, sets `status=enriched` |
| Expiry | 3-pass cron | Sets `status=expired` or `status=raw` (retry) |

## API Endpoints

- `GET /pipeline/health` — Pipeline status (public)
- `POST /pipeline/trigger` — Trigger scrape cycle (requires X-API-Key)
- `GET /keywords/enriched` — Enriched keywords for Team 4 (public)
- `GET /keywords/{id}` — Full keyword detail (public)

## Alembic Migrations

Alembic manages all schema changes. Never run raw SQL for migrations.

```bash
# Initial setup (one-time)
alembic init alembic
# Edit alembic/env.py: import Base from shared.shared.models, set target_metadata
alembic revision --autogenerate -m "initial schema"
alembic upgrade head

# Future changes
alembic revision --autogenerate -m "description"
alembic upgrade head
```

## Git Workflow

- Branch: `streamlit-revamp` for current work (see `git branch` for active branch)
- Commit convention: `<scope>: <description>` (scopes: schema, shared, scraper, sampler, llm, expiry, api, demo, infra, tests)
- All commits go to feature branches, then PR to `master`
