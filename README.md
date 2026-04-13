# AITF Keyword Manager v2

Microservice pipeline that scrapes trending keywords from Google Trends and Trends24 Indonesia, samples relevant news articles via crawler, uses OpenRouter LLM to determine government relevance, and enriches relevant keywords with expanded search terms. Output is consumed by Team 4 via REST API.

**Architecture:** 5-service Docker Compose deployment (API, Sampler, LLM, Expiry, Demo) + PostgreSQL.

---

## Keyword Lifecycle

```
raw → news_sampled → llm_justified → enriched → expired
                         ↓
                      (failed → raw, auto-retry)
```

1. **API + Scraper** — Triggered by Team 4, scrapes Trends24/Google Trends, inserts delta keywords as `raw`
2. **Sampler** — Polls `status=raw`, crawls detik/kompas/tribun news, sets `news_sampled`
3. **LLM Justifier** — Polls `status=news_sampled`, calls OpenRouter to classify relevance, sets `llm_justified`
4. **LLM Enricher** — Polls `status=llm_justified` + `is_relevant=true`, generates expanded keywords, sets `enriched`
5. **Expiry Job** — Cron job: expires stale enriched, expires irrelevant justified, retries failed keywords

---

## Quick Start

```bash
# Copy environment
cp .env.example .env
# Edit .env with your values (API keys, database credentials)

# Start all services
docker compose up -d

# Verify health
curl http://localhost:8000/pipeline/health

# Trigger a scrape (requires X-API-Key)
curl -X POST http://localhost:8000/pipeline/trigger \
  -H "X-API-Key: your-secret-key" \
  -H "Content-Type: application/json" \
  -d '{"source": "all"}'

# Check enriched keywords
curl http://localhost:8000/keywords/enriched
```

---

## Services

| Service | Port | Responsibility |
|---------|------|----------------|
| `api` | 8000 | FastAPI REST API + scraper as BackgroundTask |
| `sampler` | — | Article crawling loop (polling `status=raw`) |
| `llm` | — | Justifier + enricher loop (polling `status=news_sampled`, `status=llm_justified`) |
| `expiry` | — | APScheduler 3-pass cleanup cron |
| `demo` | 8501 | Streamlit read-only dashboard (calls API only, no direct DB) |

---

## Local Development

```bash
# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -e shared/
pip install alembic psycopg2-binary asyncpg sqlalchemy loguru fastapi uvicorn pydantic httpx beautifulsoup4 crawl4ai streamlit pytest pytest-asyncio

# Set up Alembic (one-time)
alembic init alembic
# Edit alembic/env.py to import Base from shared.shared.models
alembic revision --autogenerate -m "initial schema"
alembic upgrade head

# Run individual services
uvicorn services.api.main:app --host 127.0.0.1 --port 8000
python services/sampler/main.py
python services/llm/main.py
python services/expiry/main.py
streamlit run services/demo/app.py

# Run tests
export DATABASE_URL="postgresql+asyncpg://aitf:change_me_in_production@localhost:5432/aitf_test"
pytest tests/ -v
pytest tests/test_scraper.py::test_trends24_returns_list -v  # single test
```

---

## API Endpoints

**Public (no auth):**
- `GET /pipeline/health` — Pipeline status and keyword counts by status
- `GET /keywords/enriched?limit=50&offset=0` — Enriched keywords for Team 4
- `GET /keywords/{id}` — Full keyword detail with articles, justification, enrichment
- `GET /keywords/status/{status}` — Keywords filtered by status (raw, news_sampled, llm_justified, enriched, expired, failed)

**Protected (requires X-API-Key header):**
- `POST /pipeline/trigger` — Trigger scrape cycle (idempotent: returns 409 if already running)
- `POST /pipeline/expire` — Manually run expiry passes
- `POST /pipeline/retry-failed` — Reset all failed keywords to raw

---

## Environment Variables

```env
# PostgreSQL
DATABASE_URL=postgresql+asyncpg://aitf:change_me_in_production@localhost:5432/aitf_keywords
DATABASE_URL_SYNC=postgresql+psycopg2://aitf:change_me_in_production@localhost:5432/aitf_keywords

# OpenRouter
OPENROUTER_API_KEY=sk-or-replace-me
LLM_MODEL=anthropic/claude-3-haiku
LLM_MAX_CALLS_PER_MINUTE=20

# Scraper
SCRAPE_WINDOW_MINUTES=120

# Sampler
SAMPLER_POLL_INTERVAL_SECONDS=30
SAMPLER_BATCH_SIZE=5

# LLM Service
LLM_POLL_INTERVAL_SECONDS=30
LLM_BATCH_SIZE=10

# Expiry Job
EXPIRY_THRESHOLD_HOURS=6
IRRELEVANT_EXPIRY_HOURS=24
FAILED_RETRY_MINUTES=30
EXPIRY_CHECK_INTERVAL_MINUTES=30

# API
API_SECRET_KEY=change_me_in_production
```

---

## Docker Services

```bash
# Build all images
docker compose build

# Start all services
docker compose up -d

# View logs
docker compose logs -f api sampler llm expiry

# Stop all
docker compose down

# Run migrations
docker compose run --rm api alembic upgrade head
```

---

## Team 4 Integration

Team 4 consumes enriched keywords via the REST API:

```bash
# Get all enriched keywords with expanded search terms
GET /keywords/enriched

# Response shape:
{
  "total": 120,
  "limit": 50,
  "offset": 0,
  "items": [
    {
      "id": 1,
      "keyword": "kenaikan BBM",
      "source": "trends24",
      "rank": 3,
      "scraped_at": "2026-04-10T08:00:00Z",
      "expanded_keywords": ["harga BBM", "subsidi energi", "pertamina"]
    }
  ]
}
```

Webhook/Scheduler integration: `POST /pipeline/trigger` with X-API-Key header.

---

## Project Structure

```
├── shared/
│   └── shared/               # Pip-installable package (import: shared.shared.*)
│       ├── constants.py      # KeywordStatus, sources, thresholds
│       ├── db.py            # asyncpg SQLAlchemy engine
│       └── models.py        # ORM models (Keyword, Article, Justification, Enrichment, ScrapeRun)
├── services/
│   ├── scraper/             # Library only (no container)
│   │   ├── trends24.py      # Trends24 HTTP scraper
│   │   ├── google_trends.py # Google Trends HTTP scraper
│   │   └── delta.py         # Delta detection
│   ├── sampler/             # Article crawler
│   ├── llm/                 # OpenRouter justifier + enricher
│   ├── expiry/              # APScheduler cleanup job
│   ├── api/                 # FastAPI REST API
│   └── demo/                # Streamlit read-only dashboard
│       └── dashboard_pages/ # P01–P05 Streamlit pages (radio-button nav)
├── alembic/                  # Database migrations
├── docs/                     # Architecture diagrams (Mermaid.js)
├── tests/                    # pytest + pytest-asyncio
├── docker-compose.yml
└── SPEC.md                   # Full specification document
```

---

## Tests

```bash
# Run all tests
pytest tests/ -v

# 38 tests covering:
# - Delta detection logic
# - Body summarization
# - URL deduplication and article capping
# - LLM justification and enrichment
# - 3-pass expiry job
# - API endpoints and auth
# - Streamlit demo dashboard
```

---

## Architecture

See [docs/architecture_diagrams.md](docs/architecture_diagrams.md) for 11 Mermaid.js diagrams covering:
- System architecture (C4-style container diagram)
- Keyword lifecycle state machine
- Database ER diagram (5 tables)
- Polling query pattern (SELECT FOR UPDATE SKIP LOCKED)
- API endpoint flow
- Sampler data flow
- LLM service (justifier + enricher) flow
- Expiry service three-pass flow
- Scraper delta detection flow
- Streamlit demo dashboard structure
- Complete end-to-end data flow

---

**Developed by AITF Tim 1 — Universitas Gadjah Mada**
