# keyword-scraper

Microservice-ready MVP that scrapes trending keywords from **Google Trends** and **Trends24 Indonesia**, lets users filter and validate them through rule-based and AI-powered pipelines, and expands relevant keywords into variants for downstream Phase 2 social media scraping.

**Architecture:** Two-process deployment — FastAPI (port 8000) for REST API, Streamlit (port 8501) for human users. SQLite via SQLAlchemy 2.0 for MVP; PostgreSQL swap = one `DATABASE_URL` change.

---

## Features

| | Detail |
|---|---|
| **Sources** | Google Trends (`GTR`) · Trends24 (`T24`) |
| **Max keywords** | 100 per source per scrape |
| **Rule Filter** | Word-boundary regex against ~80 governance signals |
| **AI Filter** | OpenRouter batch classification (never per-keyword) |
| **Expander** | Keyword variant expansion via OpenRouter (manual trigger) |
| **Lifecycle** | raw → filtered → fresh → expanded |
| **API** | FastAPI REST API for Phase 2 integration |

---

## Project Structure

```
keyword-scraper/
├── api/
│   ├── main.py              # FastAPI app factory + lifespan
│   └── routes/
│       ├── scrape.py       # POST /scrape
│       ├── keywords.py     # GET /keywords, DELETE /keywords/{id}
│       ├── filter.py       # POST /keywords/filter
│       ├── classify.py     # POST /keywords/classify
│       └── expand.py       # POST /keywords/expand/batch
├── pages/
│   ├── 1_Scrape.py         # Scrape keywords from GTR + T24
│   ├── 2a_Rule_Filter.py   # Rule-based filtering
│   ├── 2b_AI_Filter.py     # OpenRouter AI classification
│   ├── 3_Fresh_Keywords.py # View fresh keywords
│   └── 4_Expand.py          # Expand keywords into variants
├── services/
│   ├── openrouter.py       # Batch AI classification
│   └── expander.py         # Keyword variant expansion
├── models/
│   └── keyword.py          # SQLAlchemy 2.0 Keyword model
├── database.py             # Engine, session, Base
├── config.py               # DB URL, OpenRouter API key
├── main.py                 # Launch FastAPI + Streamlit side-by-side
└── keyword_scraper/
    ├── filters.py           # Word-boundary regex rule filter
    └── scrapers.py         # GTR + T24 scrapers (existing)
```

---

## Setup

```bash
# 1. Install dependencies
uv sync

# 2. Install Playwright browser (first time only)
uv run crawl4ai-setup

# 3. Set OpenRouter API key
export OPENROUTER_API_KEY=your-key

# 4. Run
uv run python main.py
```

**Or run services individually:**
```bash
# FastAPI (docs at http://localhost:8000/docs)
uv run uvicorn api.main:app --port 8000

# Streamlit UI
uv run streamlit run pages/1_Scrape.py --server.port 8501
```

---

## Keyword Lifecycle

```
raw (scraped) → filtered (rule pass) → fresh (AI pass) → expanded (variants)
```

1. **Scrape** — Fetch trending keywords from Google Trends + Trends24 Indonesia
2. **Rule Filter** — Word-boundary regex match against ~80 governance signals; drops keywords with no governance signal
3. **AI Filter** — OpenRouter batch classification; keeps relevant keywords as `FRESH`
4. **Expand** — Generate search query variants for selected keywords (triggered manually; top-5 auto-flagged as `high_trend`)

**Deduplication:** Fresh/expanded keywords keep their status on re-scrape; raw/filtered keywords are re-evaluated.

---

## Phase 2 Integration

Two REST endpoints for downstream Phase 2 scrapers:

```bash
# Get all fresh keywords (ready for social media scraping)
GET /keywords/fresh

# Get all expanded keywords
GET /keywords?status=expanded
```

---

## Configuration

| Environment Variable | Default | Purpose |
|---|---|---|
| `OPENROUTER_API_KEY` | — | Required for AI filter and expander |
| `DATABASE_URL` | `sqlite:///./keyword_scraper.db` | Change to PostgreSQL URL for production |

---

## Tests

```bash
uv run python -m pytest tests/ -v
```

18 tests covering models, filters, services, API, and integration.

---

**Developed by AITF UGM Tim 1**
