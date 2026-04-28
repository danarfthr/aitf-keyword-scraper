# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository. For full technical specification, see SPEC.md.

## Project Overview

**AITF Keyword Manager v2** — Microservice pipeline that scrapes trending keywords from Google Trends and Trends24 Indonesia, samples relevant news articles via crawler, uses OpenRouter LLM to determine government relevance, and enriches relevant keywords with expanded search terms. Output consumed by Team 4 via REST API.

## Architecture

```
┌─────────────┐      ┌─────────────┐
│   Scraper   │      │   Sampler   │      ┌───────────┐
│  (service)  │      │  (service)  │      │    LLM    │
│             │      │             │      │ (service) │
└──────┬──────┘      └──────┬──────┘      └──────┬────┘
       │                    │                    │
       ▼                    ▼                    ▼
┌─────────────────────────────────────────────────┐
│                  PostgreSQL                     │
└─────────────────────────────────────────────────┘
       ▲                    ▲                    ▲
       │                    │                    │
┌──────┴──────┐      ┌──────┴──────┐      ┌──────┴──────┐
│     API     │      │   Expiry    │      │    Demo     │
│  (FastAPI)  │      │  (cronjob)  │      │ (Streamlit) │
└─────────────┘      └─────────────┘      └─────────────┘
```

- **Stateless services**: All state lives in PostgreSQL only
- **Keyword lifecycle**: Driven by `status` column (raw → news_sampled → enriched | expired | failed)
- **Concurrency**: All polling queries use `SELECT FOR UPDATE SKIP LOCKED` to prevent race conditions
- **Scraper trigger**: `POST /pipeline/trigger` writes a ScrapeRun row; Scraper service polls and executes

## Key Commands

```bash
# Virtual environment
source .venv/bin/activate

# Database migrations (first time: alembic init alembic, then edit alembic/env.py first)
alembic revision --autogenerate -m "description"
alembic upgrade head

# Run single service
python services/scraper/main.py
uvicorn services.api.main:app --host 127.0.0.1 --port 8000
python services/sampler/main.py
python services/llm/main.py
python services/expiry/main.py

# Run tests (all or single)
pytest tests/ -v
pytest tests/test_scraper.py::test_trends24_returns_list -v

# Smoke tests
pytest tests/smoke/ -v

# Docker
docker compose build
docker compose up -d
docker compose logs <service>
docker compose logs -f <service>   # Follow logs in real-time
docker compose ps                   # List running containers and status
docker compose restart <service>    # Restart specific service without losing state
```

## Docker & Service Notes

- **Docker compose:** `docker compose up -d` runs all services; each service has its own `Dockerfile` in its directory (e.g., `services/scraper/Dockerfile`)
- **Adding new services:** Create Dockerfile in service directory, then add service entry to `docker-compose.yml` with proper depends_on and environment links
- **Scraper service:** Polls `ScrapeRun` table for jobs; if pipeline shows degraded, check scraper container logs and PostgreSQL connectivity
- **Pipeline health:** Streamlit sidebar shows colored dot (green=healthy, yellow=degraded); health check endpoint is `GET /pipeline/health`
- **Pipeline trigger:** `POST /pipeline/trigger` creates a ScrapeRun row; scraper picks it up asynchronously
- **Pipeline health logic:** `GET /pipeline/health` aggregates status from all service poll results (scraper, sampler, llm, expiry)

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
│   ├── scraper/          # Polling service — scrapes trends + delta detection
│   │   ├── trends24.py
│   │   ├── google_trends.py
│   │   ├── delta.py
│   │   └── main.py       # Entry point (polls ScrapeRun table)
│   ├── sampler/          # Crawls detik/kompas/tribun news sites
│   ├── llm/             # OpenRouter processor (combined justification + enrichment)
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
| Scraper | `ScrapeRun` rows with `status=running` | Keywords with `status=raw` in PostgreSQL |
| API | — | REST API. Creates ScrapeRun rows; `POST /pipeline/trigger` enqueues scrape jobs. |
| Sampler | `status=raw` | Articles, sets `status=news_sampled` |
| LLM (processor) | `status=news_sampled` | KeywordJustification + KeywordEnrichment; sets `status=enriched` (relevant) or `status=expired` (not relevant) |
| Expiry | 3-pass cron (30 min) | Sets `status=expired` or `status=raw` (retry) |

## API Endpoints

- `GET /pipeline/health` — Pipeline status (public)
- `POST /pipeline/trigger` — Enqueue scrape job for Scraper service (requires X-API-Key). Returns immediately.
- `POST /pipeline/expire` — Expiry service runs on 30-min cron (informational only)
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

## Sampler / Crawl4AI Notes

- **`wait_until`**: Always use `"load"` — `"networkidle"` never fires on Indonesian news sites (infinite ad/tracker requests)
- **Stealth flags**: Avoid `magic=True` and `enable_stealth=True` — they trigger *more* Cloudflare blocking on tribun/kompas; use `simulate_user=True` + `override_navigator=True` instead
- **`user_agent_generator_config`**: Not supported by the installed Crawl4AI version (`ValidUAGenerator.generate()` rejects kwargs); use `user_agent_mode="random"` alone
- **Tribun/Kompas**: Cloudflare-protected — intermittently blocks Docker egress IPs; optional proxy wired via `CRAWLER_PROXY_URL` / `CRAWLER_PROXY_USER` / `CRAWLER_PROXY_PASS` env vars
- **0 articles on K-pop keywords**: Expected — hashtags like `#DearMySUNWOODay` don't appear in Indonesian news; not a crawler bug

## LLM / OpenRouter Notes

- **Rate limit**: OpenRouter free tier ~10 RPM; default semaphore is 10 — don't raise it
- **Retry backoff**: Use `15s × attempt + jitter(0-5s)` — anything faster causes cascading 429s

## Git Workflow

- Use `git branch -a` to see all local and remote branches (remote-only branches shown separately)
- After merging a feature branch: `git push -d origin <branch-name>` to delete the remote branch
- Commit convention: `<scope>: <description>` (scopes: schema, shared, scraper, sampler, llm, expiry, api, demo, infra, tests)
- All commits go to feature branches, then PR to `master`
- Current active branch: `master`
