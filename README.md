# AITF Keyword Manager v2

Microservice pipeline that scrapes trending keywords from Google Trends and Trends24 Indonesia, samples relevant news articles via crawler, uses OpenRouter LLM to determine government relevance, and enriches relevant keywords with expanded search terms. Output consumed by Team 4 via REST API.

**Architecture:** 6-service Docker Compose deployment (API, Scraper, Sampler, LLM, Expiry, Demo) + PostgreSQL.

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

Dashboard operators can browse all keywords across every status via:

```bash
# Get all keywords with optional filters
GET /keywords/all?status=all&source=trends24&search=BBM&limit=50

# Get expired/archived keywords only
GET /keywords/all?status=expired&limit=200

# Response shape (same as /keywords/enriched):
{
  "total": 450,
  "limit": 50,
  "offset": 0,
  "items": [
    {
      "id": 2,
      "keyword": "BBM naik",
      "source": "trends24",
      "rank": 5,
      "scraped_at": "2026-04-09T10:00:00Z",
      "expanded_keywords": [],
      "is_relevant": true
    }
  ]
}
```

Webhook/Scheduler integration: `POST /pipeline/trigger` with X-API-Key header.

---

## Local Development

```bash
# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -e shared/
pip install alembic psycopg2-binary asyncpg sqlalchemy loguru fastapi uvicorn pydantic httpx crawl4ai streamlit pytest pytest-asyncio
playwright install chromium --with-deps  # required by sampler

# Set up Alembic (one-time)
alembic init alembic
# Edit alembic/env.py to import Base from shared.shared.models
alembic revision --autogenerate -m "initial schema"
alembic upgrade head

# Run individual services
python services/scraper/main.py
uvicorn services.api.main:app --host 127.0.0.1 --port 8000
python services/sampler/main.py
python services/llm/main.py
python services/expiry/main.py
streamlit run services/demo/app.py

# Run tests
export DATABASE_URL="postgresql+asyncpg://aitf:change_me_in_production@localhost:5432/aitf_test"
pytest tests/ -v
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
