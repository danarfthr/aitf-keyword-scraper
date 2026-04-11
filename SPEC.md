# SPEC.md — Keyword Manager Pipeline (v2 Architecture)
## AITF Tim 1 — Dashboard Monev Komdigi

---

## AGENT INSTRUCTIONS

This document is the single source of truth for implementing the v2 architecture of the
keyword manager pipeline. Read this file in full before writing any code.

**Critical rules for the agent:**
- This is a full revamp. Do NOT patch or extend the existing code. Rewrite from scratch.
- Use the branch `feat/v2-pipeline` for all work. Never touch `main`.
- Follow the implementation order in Section 9 exactly. Do not skip ahead.
- Every service is stateless. All state lives in PostgreSQL only.
- Keyword lifecycle is driven by the `status` column. Services poll by status.
- Every polling query MUST use `SELECT FOR UPDATE SKIP LOCKED`. No exceptions.
- Do not invent abstractions not specified here. Build exactly what is described.
- When a section says "see Section X", read that section before proceeding.
- All environment variables must be read from `.env` via `python-dotenv`. Never hardcode.
- Every function must have a docstring. Every module must have a module-level docstring.
- Use `loguru` for all logging. No `print()` statements in production code.
- Use `pytest` with `pytest-asyncio` for all tests. No bare assert scripts.
- Write `# TODO(team4):` comments at every integration point with Team 4.
- Write `# TODO(team-other):` comments at integration points with other teams.

---

## TABLE OF CONTENTS

1. Project Overview
2. Branch & Repository Strategy
3. System Architecture
4. Directory Structure
5. PostgreSQL Schema & Migrations
6. Service Specifications
7. API Contract (FastAPI)
8. Environment Variables
9. Implementation Order
10. Docker & Deployment
11. Streamlit Demo Spec
12. LLM Prompt Templates
13. Testing Requirements

---

## 1. PROJECT OVERVIEW

**Project name:** aitf-keyword-manager (v2)
**Purpose:** Automatically discover trending keywords from Indonesian platforms (Trends24,
Google Trends), sample relevant news articles, use an LLM to determine government/ministry
relevance, and enrich relevant keywords with expanded search terms. Output is consumed by
Team 4 (fullstack/scheduler) via REST API and shared PostgreSQL.

**Key design decisions:**
- Keyword filtering happens AFTER news sampling. The LLM sees article content, not just
  the keyword string.
- All services are stateless containers. All state lives in PostgreSQL.
- OpenRouter is the LLM provider. The model is configurable via env var.
- The scraper is not a standalone container. It is a library imported and invoked by the
  API service as a FastAPI BackgroundTask. This avoids the dual-container contradiction.
- The Streamlit demo calls the FastAPI endpoints only. It does not hold DB credentials.
- All concurrent DB access uses `SELECT FOR UPDATE SKIP LOCKED` to prevent race conditions.
- Schema changes are managed by Alembic. Raw SQL is never used for migrations.
- Google Trends and Trends24 both use direct HTTP scraping. Do NOT use pytrends or any
  third-party trends library. Use the existing HTTP scraper implementations.

---

## 2. BRANCH & REPOSITORY STRATEGY

```
main                  <- stable, do not touch
feat/v2-pipeline      <- all v2 work goes here
```

**Setup:**
```bash
git checkout main
git pull origin main
git checkout -b feat/v2-pipeline
git push -u origin feat/v2-pipeline
```

**Commit message convention:**
```
<scope>: <short description>

Scopes: schema, shared, scraper, sampler, llm, expiry, api, demo, infra, tests

Examples:
  schema: add initial alembic migration
  scraper: implement delta detection with configurable window
  sampler: add SELECT FOR UPDATE SKIP LOCKED to polling query
  api: add POST /pipeline/trigger with idempotency lock
  infra: add healthchecks to all containers
```

**`.gitignore` must include:**
```
.env
*.pyc
__pycache__/
.DS_Store
*.log
.pytest_cache/
htmlcov/
```

Do not commit `.env`, secrets, or compiled files.

---

## 3. SYSTEM ARCHITECTURE

### Data Flow

```
[Team 4 Scheduler]
       |
       | POST /pipeline/trigger  (with X-API-Key header)
       v
[keyword-manager-api]
   Checks idempotency: is there a running scrape_run?
   If yes: return 409 Conflict
   If no: insert scrape_run (status=running), fire BackgroundTask
       |
       v
[Scraper Library — runs inside API process as BackgroundTask]
   Scrapes Trends24  (existing HTTP scraper, no pytrends)
   Scrapes Google Trends (existing HTTP scraper, no pytrends)
   Detects delta using SCRAPE_WINDOW_MINUTES
   Bulk inserts delta keywords with status: raw
   Updates scrape_run (finished_at, keywords_inserted, status=done)
       |
       v
[PostgreSQL: keywords.status = raw]
       |
       v
[news-sampler container — continuous polling loop]
   SELECT FOR UPDATE SKIP LOCKED WHERE status = raw
   Runs 3 crawlers concurrently (asyncio.gather)
   Caps total articles at MAX_ARTICLES_TOTAL_PER_KEYWORD
   Deduplicates by URL (memory + DB ON CONFLICT DO NOTHING)
   Stores summary only if body > SUMMARY_CHAR_THRESHOLD (body set to NULL)
   Updates keyword: status = news_sampled
   On unhandled exception: status = failed, failure_reason = str(e)
       |
       v
[PostgreSQL: keywords.status = news_sampled]
       |
       v
[llm-service container — continuous polling loop, Phase 1: Justifier]
   SELECT FOR UPDATE SKIP LOCKED WHERE status = news_sampled
   Builds article context from summary/body
   Calls OpenRouter (rate-limited to LLM_MAX_CALLS_PER_MINUTE)
   Parses JSON verdict: {is_relevant: bool, justification: str}
   Saves to keyword_justifications
   Updates keyword: status = llm_justified
   On LLMError: status = failed, failure_reason = "LLM permanent failure: justifier"
       |
       v
[PostgreSQL: keywords.status = llm_justified]
   |
   |-- is_relevant = false: stays here, expired by expiry job after IRRELEVANT_EXPIRY_HOURS
   |
   +-- is_relevant = true:
       v
[llm-service container — Phase 2: Enricher]
   SELECT FOR UPDATE SKIP LOCKED
   WHERE status = llm_justified AND keyword_justifications.is_relevant = true
   Calls OpenRouter (rate-limited)
   Parses JSON: {expanded_keywords: [str, ...]}
   Saves to keyword_enrichments
   Updates keyword: status = enriched
   On LLMError: status = failed, failure_reason = "LLM permanent failure: enricher"
       |
       v
[PostgreSQL: keywords.status = enriched]
       |
       v
[expiry-job container — APScheduler cron]
   Pass 1: enriched WHERE last article crawled_at > EXPIRY_THRESHOLD_HOURS
            -> status = expired
   Pass 2: llm_justified + is_relevant=false WHERE processed_at > IRRELEVANT_EXPIRY_HOURS
            -> status = expired
   Pass 3: failed WHERE updated_at > FAILED_RETRY_MINUTES
            -> status = raw (auto-retry), failure_reason = NULL
       |
       v
[keyword-manager-api]
   GET /keywords/enriched         <- Team 4 reads expanded keywords
   GET /pipeline/health           <- Team 4 monitors pipeline state
   POST /pipeline/trigger         <- Team 4 scheduler calls this
       |
       v
[streamlit-demo container]
   Calls FastAPI only via httpx. No direct DB access. No DATABASE_URL.
```

### Container Map

| Container           | Responsibility                              | Triggered By                    |
|---------------------|---------------------------------------------|---------------------------------|
| keyword-manager-api | REST API + runs scraper as BackgroundTask   | Always running                  |
| news-sampler        | Article crawling loop                       | Polls DB (status=raw)           |
| llm-service         | Justifier + enricher loop                   | Polls DB (status=news_sampled)  |
| expiry-job          | Lifecycle cleanup cron                      | APScheduler inside container    |
| streamlit-demo      | Read-only stakeholder demo                  | Always running                  |

There is NO standalone scraper container. Scraper logic lives in `services/scraper/`
as a library and is imported by `services/api/`.

---

## 4. DIRECTORY STRUCTURE

Rewrite the entire repository to match this structure. Delete all files and folders
from the old codebase that do not fit this layout.

```
aitf-keyword-manager/
├── .env                              <- never commit
├── .env.example                      <- commit with placeholder values
├── .gitignore
├── docker-compose.yml
├── SPEC.md
├── README.md
│
├── alembic.ini                       <- alembic config, root-level
├── alembic/
│   ├── env.py
│   └── versions/
│       └── 001_initial_schema.py     <- first migration (autogenerated)
│
├── shared/                           <- pip-installable local package
│   ├── pyproject.toml
│   └── shared/
│       ├── __init__.py
│       ├── constants.py
│       ├── db.py
│       └── models.py
│
├── services/
│   ├── scraper/                      <- library only, NO Dockerfile, NO container
│   │   ├── __init__.py
│   │   ├── trends24.py               <- Trends24 HTTP scraper (existing implementation)
│   │   ├── google_trends.py          <- Google Trends HTTP scraper (existing implementation)
│   │   └── delta.py                  <- delta detection logic
│   │
│   ├── sampler/
│   │   ├── Dockerfile
│   │   ├── requirements.txt
│   │   ├── main.py
│   │   ├── crawler.py
│   │   └── summarizer.py
│   │
│   ├── llm/
│   │   ├── Dockerfile
│   │   ├── requirements.txt
│   │   ├── main.py
│   │   ├── client.py
│   │   ├── justifier.py
│   │   ├── enricher.py
│   │   └── prompts.py
│   │
│   ├── expiry/
│   │   ├── Dockerfile
│   │   ├── requirements.txt
│   │   └── main.py
│   │
│   ├── api/
│   │   ├── Dockerfile
│   │   ├── requirements.txt
│   │   ├── main.py
│   │   ├── auth.py
│   │   ├── routers/
│   │   │   ├── keywords.py
│   │   │   └── pipeline.py
│   │   ├── schemas.py
│   │   └── db.py
│   │
│   └── demo/
│       ├── Dockerfile
│       ├── requirements.txt
│       └── app.py
│
└── tests/
    ├── conftest.py
    ├── test_scraper.py
    ├── test_delta.py
    ├── test_sampler.py
    ├── test_justifier.py
    ├── test_enricher.py
    ├── test_expiry.py
    └── test_api.py
```

### shared/ as a pip-installable package

`shared/pyproject.toml`:
```toml
[build-system]
requires = ["setuptools"]
build-backend = "setuptools.backends.legacy:build"

[project]
name = "aitf-shared"
version = "1.0.0"
dependencies = [
    "sqlalchemy[asyncio]>=2.0",
    "asyncpg",
    "psycopg2-binary",
    "python-dotenv",
]
```

Each service Dockerfile installs it as:
```dockerfile
COPY shared/ /shared
RUN pip install -e /shared
```

This works both locally and on cloud container platforms (Cloud Run, ECS) where
there is no shared filesystem between containers.

---

## 5. POSTGRESQL SCHEMA & MIGRATIONS

Use Alembic for all schema management. Never run raw SQL manually.

**One-time Alembic setup:**
```bash
pip install alembic psycopg2-binary
alembic init alembic
# Edit alembic/env.py (see below)
alembic revision --autogenerate -m "initial schema"
alembic upgrade head
```

**`alembic/env.py` requirements:**
- Read `DATABASE_URL_SYNC` (psycopg2) from `os.environ`.
- Import `Base` from `shared.models`.
- Set `target_metadata = Base.metadata`.
- Alembic uses synchronous psycopg2 — not asyncpg.

**Future schema changes:** always create a new revision via
`alembic revision --autogenerate -m "description"`. Never modify existing migrations.

---

### Schema (reflected in shared/shared/models.py as ORM models)

All models use `Mapped` and `mapped_column` from SQLAlchemy 2.x.
Define a single `Base = DeclarativeBase()` in `shared/shared/models.py`.

---

#### TABLE: keywords

| Column         | Type        | Constraints                                                        |
|----------------|-------------|--------------------------------------------------------------------|
| id             | SERIAL      | PRIMARY KEY                                                        |
| keyword        | TEXT        | NOT NULL                                                           |
| source         | TEXT        | NOT NULL, CHECK IN ('trends24', 'google_trends')                   |
| rank           | INT         | nullable                                                           |
| scraped_at     | TIMESTAMPTZ | NOT NULL, DEFAULT NOW()                                            |
| status         | TEXT        | NOT NULL, DEFAULT 'raw', CHECK IN (see KeywordStatus below)        |
| failure_reason | TEXT        | nullable — set when status = failed                                |
| updated_at     | TIMESTAMPTZ | NOT NULL, DEFAULT NOW(), auto-updated by trigger on every UPDATE   |

Valid status values: `raw`, `news_sampled`, `llm_justified`, `enriched`, `expired`, `failed`

Indexes:
- `idx_keywords_status` on `(status)`
- `idx_keywords_scraped_at` on `(scraped_at)`
- `idx_keywords_status_updated` on `(status, updated_at)`

Trigger: define `update_updated_at_column()` function and trigger in Alembic migration
using `op.execute()`.

---

#### TABLE: articles

| Column      | Type        | Constraints                                            |
|-------------|-------------|--------------------------------------------------------|
| id          | SERIAL      | PRIMARY KEY                                            |
| keyword_id  | INT         | NOT NULL, FK -> keywords(id) ON DELETE CASCADE         |
| source_site | TEXT        | NOT NULL, CHECK IN ('detik', 'kompas', 'tribun')       |
| url         | TEXT        | NOT NULL, UNIQUE (enforced at DB level)                |
| title       | TEXT        | nullable                                               |
| body        | TEXT        | nullable — must be NULL when summary is populated      |
| summary     | TEXT        | nullable — populated when body > SUMMARY_CHAR_THRESHOLD|
| crawled_at  | TIMESTAMPTZ | NOT NULL, DEFAULT NOW()                                |

Indexes:
- `idx_articles_keyword_id` on `(keyword_id)`
- `uq_articles_url` UNIQUE on `(url)`

---

#### TABLE: keyword_justifications

| Column        | Type        | Constraints                                      |
|---------------|-------------|--------------------------------------------------|
| id            | SERIAL      | PRIMARY KEY                                      |
| keyword_id    | INT         | NOT NULL, FK -> keywords(id) ON DELETE CASCADE   |
| is_relevant   | BOOLEAN     | NOT NULL                                         |
| justification | TEXT        | nullable                                         |
| llm_model     | TEXT        | NOT NULL                                         |
| processed_at  | TIMESTAMPTZ | NOT NULL, DEFAULT NOW()                          |

Indexes:
- `uq_justifications_keyword_id` UNIQUE on `(keyword_id)`
- `idx_justifications_is_relevant` on `(is_relevant)`

---

#### TABLE: keyword_enrichments

| Column             | Type        | Constraints                                      |
|--------------------|-------------|--------------------------------------------------|
| id                 | SERIAL      | PRIMARY KEY                                      |
| keyword_id         | INT         | NOT NULL, FK -> keywords(id) ON DELETE CASCADE   |
| expanded_keywords  | JSONB       | NOT NULL — string[]                              |
| source_article_ids | JSONB       | nullable — int[] of article IDs used as context  |
| llm_model          | TEXT        | NOT NULL                                         |
| processed_at       | TIMESTAMPTZ | NOT NULL, DEFAULT NOW()                          |

Indexes:
- `uq_enrichments_keyword_id` UNIQUE on `(keyword_id)`

---

#### TABLE: scrape_runs

Tracks every scrape cycle. Used for idempotency check and health reporting.

| Column            | Type        | Constraints                                                       |
|-------------------|-------------|-------------------------------------------------------------------|
| id                | SERIAL      | PRIMARY KEY                                                       |
| source            | TEXT        | NOT NULL — 'trends24', 'google_trends', or 'all'                  |
| started_at        | TIMESTAMPTZ | NOT NULL, DEFAULT NOW()                                           |
| finished_at       | TIMESTAMPTZ | nullable — NULL means currently running                           |
| keywords_inserted | INT         | NOT NULL, DEFAULT 0                                               |
| status            | TEXT        | NOT NULL, DEFAULT 'running', CHECK IN ('running', 'done', 'failed')|

Indexes:
- `idx_scrape_runs_started_at` on `(started_at)`
- `idx_scrape_runs_status` on `(status)`

---

## 6. SERVICE SPECIFICATIONS

---

### 6.1 shared/shared/constants.py

```python
"""Shared constants used across all services. Do not modify without updating SPEC.md."""


class KeywordStatus:
    RAW           = "raw"
    NEWS_SAMPLED  = "news_sampled"
    LLM_JUSTIFIED = "llm_justified"
    ENRICHED      = "enriched"
    EXPIRED       = "expired"
    FAILED        = "failed"

    ALL = [RAW, NEWS_SAMPLED, LLM_JUSTIFIED, ENRICHED, EXPIRED, FAILED]


class KeywordSource:
    TRENDS24      = "trends24"
    GOOGLE_TRENDS = "google_trends"


class ArticleSource:
    DETIK  = "detik"
    KOMPAS = "kompas"
    TRIBUN = "tribun"


ARTICLE_SOURCES = [ArticleSource.DETIK, ArticleSource.KOMPAS, ArticleSource.TRIBUN]

# Characters before body is replaced by a truncated summary
SUMMARY_CHAR_THRESHOLD = 3000

# Max articles fetched per individual crawler (2 per crawler x 3 crawlers = 6 candidates)
MAX_ARTICLES_PER_CRAWLER = 2

# Max total articles saved per keyword after merging all crawlers
MAX_ARTICLES_TOTAL_PER_KEYWORD = 5

# Hours with no new articles before an enriched keyword is marked expired
EXPIRY_THRESHOLD_HOURS = 6

# Hours before irrelevant (is_relevant=false) keywords are marked expired
IRRELEVANT_EXPIRY_HOURS = 24

# Minutes before a failed keyword is auto-retried (reset to raw)
FAILED_RETRY_MINUTES = 30
```

---

### 6.2 shared/shared/db.py

- Driver: `asyncpg`
- ORM: SQLAlchemy 2.x with async support
- Expose: `async_engine`, `AsyncSessionLocal`, `get_session()` async context manager
- Read `DATABASE_URL` from environment
- Pool: `pool_size=5`, `max_overflow=10`

**Mandatory polling pattern — use in every service:**

```python
async with get_session() as session:
    async with session.begin():
        result = await session.execute(
            select(Keyword)
            .where(Keyword.status == KeywordStatus.RAW)
            .order_by(Keyword.scraped_at.asc())
            .limit(batch_size)
            .with_for_update(skip_locked=True)   # MANDATORY
        )
        keywords = result.scalars().all()
```

Never poll without `.with_for_update(skip_locked=True)`. This prevents race conditions
when multiple container instances run concurrently or when Team 4 accidentally double-fires.

---

### 6.3 shared/shared/models.py

Define SQLAlchemy ORM models for all five tables using `Mapped` and `mapped_column`
from SQLAlchemy 2.x: `Keyword`, `Article`, `KeywordJustification`,
`KeywordEnrichment`, `ScrapeRun`.

Mirror the schema in Section 5 exactly — column names, types, nullability, defaults,
and check constraints. Define one `Base = DeclarativeBase()` imported by Alembic and
all services.

---

### 6.4 services/scraper/ (library only — no container, no Dockerfile)

This directory is a Python package imported by `services/api/`.
It has no `Dockerfile` and no entry in `docker-compose.yml`.

**trends24.py**

Port the existing Trends24 HTTP scraper from the old codebase. Clean it up. Keep using `crawl4ai`

Requirements:
- Return: `list[dict]` — keys: `keyword: str`, `rank: int`, `source: "trends24"`
- ETag caching: store last ETag in memory; send `If-None-Match` on subsequent requests;
  return cached result on HTTP 304.
- Exponential backoff: 3 retries, base 2s delay, on HTTP 429 or 5xx.
- Rotate user agents on each request from a list of 5 common browser UAs.
- Log each attempt: URL, status code, keyword count returned.

**google_trends.py**

Port the existing Google Trends HTTP scraper from the old codebase. Clean it up. Keep using `crawl4ai`

Requirements (same as Trends24):
- Return: `list[dict]` — keys: `keyword: str`, `rank: int`, `source: "google_trends"`
- Apply same ETag caching and retry logic.
- Log each attempt.

**delta.py**

```python
async def detect_delta(
    scraped: list[dict],
    session: AsyncSession,
    window_minutes: int,
) -> list[dict]:
    """
    Given a freshly scraped list of keyword dicts, returns only those whose
    lowercase-stripped keyword text did not appear in any keyword row inserted
    within the last `window_minutes` minutes.

    Delta detection is source-agnostic: the same keyword text from a different
    source is NOT a delta if it was already seen in the window.
    """
    cutoff = datetime.utcnow() - timedelta(minutes=window_minutes)
    result = await session.execute(
        select(Keyword.keyword).where(Keyword.scraped_at > cutoff)
    )
    existing = {k.lower().strip() for k in result.scalars().all()}
    return [kw for kw in scraped if kw["keyword"].lower().strip() not in existing]
```

---

### 6.5 services/sampler/

**crawler.py**

Implement three async crawler functions: `crawl_detik`, `crawl_kompas`, `crawl_tribun`.

Each function:
- Accepts `keyword: str`
- Returns `list[dict]` — keys: `source_site`, `url`, `title`, `body`
- Returns at most `MAX_ARTICLES_PER_CRAWLER` results
- Uses `httpx.AsyncClient` with `timeout=15.0`
- Uses `BeautifulSoup` for HTML parsing
- Handles `httpx.TimeoutException`, `httpx.HTTPStatusError`, empty result sets
- On any error: log warning, return `[]` — never raise

Selectors (mark each with `# TODO: verify selectors are current`):

```python
# Detik
DETIK_SEARCH   = "https://www.detik.com/search/searchall?query={keyword}"
DETIK_LINKS    = "article a"
DETIK_TITLE    = "h1.detail__title"
DETIK_BODY     = "div.detail__body-text"

# Kompas
KOMPAS_SEARCH  = "https://search.kompas.com/search/?q={keyword}"
KOMPAS_LINKS   = ".article__list a"
KOMPAS_TITLE   = "h1.read__title"
KOMPAS_BODY    = "div.read__content"

# Tribun
TRIBUN_SEARCH  = "https://www.tribunnews.com/search?q={keyword}"
TRIBUN_LINKS   = ".lsi a"
TRIBUN_TITLE   = "h1.f40"
TRIBUN_BODY    = "div#article-2 p"
```

CSS selectors for Indonesian news sites change frequently. The agent must NOT
change these selectors; they are a maintenance concern outside of this implementation.

**summarizer.py**

```python
def summarize_body(body: str) -> tuple[str | None, str | None]:
    """
    Returns (body_to_store, summary_to_store).

    If len(body) > SUMMARY_CHAR_THRESHOLD:
        body_to_store   = None          (do not store — saves column space)
        summary_to_store = body[:SUMMARY_CHAR_THRESHOLD] + "... [truncated]"
    Else:
        body_to_store   = body
        summary_to_store = None
    """
```

**main.py — polling loop:**

```
On startup: log "sampler started", log poll interval and batch size.

Loop every SAMPLER_POLL_INTERVAL_SECONDS:
  1. Open DB session.
  2. SELECT FOR UPDATE SKIP LOCKED WHERE status = raw, LIMIT SAMPLER_BATCH_SIZE.
  3. For each keyword in batch:
     a. Run crawl_detik, crawl_kompas, crawl_tribun concurrently:
        results = await asyncio.gather(
            crawl_detik(keyword.keyword),
            crawl_kompas(keyword.keyword),
            crawl_tribun(keyword.keyword),
            return_exceptions=True,
        )
     b. Flatten, discard exceptions (already handled inside crawlers).
     c. Deduplicate by URL in memory (keep first occurrence).
     d. Take first MAX_ARTICLES_TOTAL_PER_KEYWORD articles.
     e. For each article: call summarize_body(), set body and summary accordingly.
     f. Bulk insert into articles:
        INSERT INTO articles ... ON CONFLICT (url) DO NOTHING
     g. On any unhandled exception in steps a-f:
        keyword.status = KeywordStatus.FAILED
        keyword.failure_reason = str(exception)
        log error, continue to next keyword.
     h. On success (even if 0 articles found):
        keyword.status = KeywordStatus.NEWS_SAMPLED
        if 0 articles: log warning("No articles found for keyword: {keyword.keyword}")
  4. Commit transaction.
  5. Write NOW() timestamp to /tmp/sampler_heartbeat.txt.
  6. Sleep SAMPLER_POLL_INTERVAL_SECONDS.
```

---

### 6.6 services/llm/

**client.py**

```python
class LLMError(Exception):
    """Raised when OpenRouter returns a permanent failure after all retries."""


class OpenRouterClient:
    """
    Async client for OpenRouter chat completions API.
    Implements per-minute rate limiting and exponential retry.
    """

    BASE_URL = "https://openrouter.ai/api/v1/chat/completions"

    def __init__(self):
        """Read OPENROUTER_API_KEY, LLM_MODEL, LLM_MAX_CALLS_PER_MINUTE from env."""

    async def chat(self, messages: list[dict]) -> str:
        """
        Send messages to OpenRouter. Returns assistant response as string.
        Rate-limited to LLM_MAX_CALLS_PER_MINUTE.
        Retries 3 times with 2s backoff on HTTP 429 or 5xx.
        Raises LLMError on permanent failure.
        """
```

Rate limiting: use `asyncio.Semaphore(LLM_MAX_CALLS_PER_MINUTE)` with a 60-second
release delay. After acquiring the semaphore, schedule its release for
`60 / LLM_MAX_CALLS_PER_MINUTE` seconds later using `asyncio.ensure_future`.

Required headers on every request:
```python
{
    "Authorization": f"Bearer {OPENROUTER_API_KEY}",
    "Content-Type": "application/json",
    "HTTP-Referer": "https://aitf.ugm.ac.id",
    "X-Title": "AITF-Tim1-KeywordManager",
}
```

**justifier.py**

```python
async def justify_keyword(
    keyword: Keyword,
    articles: list[Article],
    client: OpenRouterClient,
    session: AsyncSession,
) -> None:
    """
    Determines if keyword topic is related to Indonesian government issues.
    Saves KeywordJustification row. Updates keyword status to llm_justified.
    On LLMError: sets status = failed with reason.
    """
```

Process:
1. `context = build_article_context(articles)` from `prompts.py`.
2. Call `client.chat(build_messages(JUSTIFIER_SYSTEM, build_justifier_prompt(keyword.keyword, context)))`.
3. Parse: `json.loads(response)` — expect `{"is_relevant": bool, "justification": str}`.
4. On `json.JSONDecodeError`: retry the LLM call once (same input).
5. On second parse failure: `is_relevant = False`, `justification = "LLM parse error"`.
6. Insert `KeywordJustification`.
7. `keyword.status = KeywordStatus.LLM_JUSTIFIED`.
8. On `LLMError`: `keyword.status = KeywordStatus.FAILED`,
   `keyword.failure_reason = "LLM permanent failure: justifier"`.

**enricher.py**

```python
async def enrich_keyword(
    keyword: Keyword,
    articles: list[Article],
    client: OpenRouterClient,
    session: AsyncSession,
) -> None:
    """
    Generates expanded keyword list from article context.
    Saves KeywordEnrichment row. Updates keyword status to enriched.
    On LLMError: sets status = failed with reason.
    """
```

Process:
1. `context = build_article_context(articles)`.
2. Call `client.chat(build_messages(ENRICHER_SYSTEM, build_enricher_prompt(keyword.keyword, context)))`.
3. Parse: `json.loads(response)` — expect `{"expanded_keywords": list[str]}`.
4. Validate: must be a non-empty `list[str]`.
5. On parse or validation failure: retry once.
6. On second failure: use `[keyword.keyword]` as fallback.
7. Insert `KeywordEnrichment` with `source_article_ids = [a.id for a in articles]`.
8. `keyword.status = KeywordStatus.ENRICHED`.
9. On `LLMError`: `keyword.status = KeywordStatus.FAILED`,
   `keyword.failure_reason = "LLM permanent failure: enricher"`.

**main.py — polling loop:**

```
Loop every LLM_POLL_INTERVAL_SECONDS:

  Phase 1 — Justifier:
    SELECT FOR UPDATE SKIP LOCKED
    WHERE status = news_sampled
    LIMIT LLM_BATCH_SIZE
    For each keyword:
      - fetch its articles
      - call justify_keyword()
      - commit after EACH keyword (not after full batch — avoids partial batch loss)

  Phase 2 — Enricher:
    SELECT FOR UPDATE SKIP LOCKED
    WHERE status = llm_justified
    JOIN keyword_justifications WHERE is_relevant = true
    LIMIT LLM_BATCH_SIZE
    For each keyword:
      - fetch its articles
      - call enrich_keyword()
      - commit after EACH keyword

  Write NOW() to /tmp/llm_heartbeat.txt
  Sleep LLM_POLL_INTERVAL_SECONDS
```

---

### 6.7 services/expiry/

**main.py**

Use `APScheduler` with `AsyncIOScheduler`. Run the full job every
`EXPIRY_CHECK_INTERVAL_MINUTES` minutes.

```
Pass 1 — Expire stale enriched keywords:
  SELECT keywords WHERE status = enriched FOR UPDATE SKIP LOCKED
  For each: get MAX(articles.crawled_at) WHERE keyword_id = keyword.id
  If NOW() - max_crawled_at > EXPIRY_THRESHOLD_HOURS hours:
    keyword.status = expired
  Log count of keywords expired in this pass.

Pass 2 — Expire irrelevant justified keywords:
  SELECT keywords WHERE status = llm_justified FOR UPDATE SKIP LOCKED
  JOIN keyword_justifications WHERE is_relevant = false
  AND keyword_justifications.processed_at < NOW() - IRRELEVANT_EXPIRY_HOURS hours
  keyword.status = expired
  Log count.

Pass 3 — Auto-retry failed keywords:
  SELECT keywords WHERE status = failed FOR UPDATE SKIP LOCKED
  AND keywords.updated_at < NOW() - FAILED_RETRY_MINUTES minutes
  keyword.status = raw
  keyword.failure_reason = NULL
  Log count of keywords reset.

After all three passes: write NOW() to /tmp/expiry_heartbeat.txt
```

---

### 6.8 services/api/

**auth.py**

```python
from fastapi import Security, HTTPException
from fastapi.security import APIKeyHeader
import os

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def require_api_key(key: str = Security(api_key_header)) -> None:
    """FastAPI dependency. Validates X-API-Key header against API_SECRET_KEY env var."""
    if not key or key != os.environ["API_SECRET_KEY"]:
        raise HTTPException(status_code=401, detail="Invalid or missing API key.")
```

Apply `Depends(require_api_key)` on ALL POST endpoints in `pipeline.py`.
GET endpoints in `keywords.py` are public — no auth dependency.

**routers/pipeline.py — idempotency logic for POST /pipeline/trigger:**

```python
# Step 1: Check for running cycle
running = await session.execute(
    select(ScrapeRun)
    .where(ScrapeRun.status == "running")
    .where(ScrapeRun.started_at > datetime.utcnow() - timedelta(minutes=10))
)
if running.scalar():
    raise HTTPException(status_code=409, detail="A scrape cycle is already running.")

# Step 2: Insert scrape_run record
run = ScrapeRun(source=body.source, status="running")
session.add(run)
await session.commit()
await session.refresh(run)

# Step 3: Fire background task
background_tasks.add_task(run_scrape_cycle, source=body.source, run_id=run.id)
return {"triggered": True, "scrape_run_id": run.id, "message": "Scrape cycle started."}
```

`run_scrape_cycle(source, run_id)` background function:
```
1. Import trends24 and google_trends from services/scraper/
2. Run requested scrapers based on source value
3. Merge results, call detect_delta()
4. Bulk insert delta keywords with status=raw
5. Update ScrapeRun: finished_at=NOW(), keywords_inserted=count, status='done'
6. On any exception: update ScrapeRun status='failed', log error
```

**main.py:**

```python
from fastapi import FastAPI
from contextlib import asynccontextmanager
from routers import keywords, pipeline


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Verify DB connection on startup. Log graceful stop on shutdown."""
    # startup: run SELECT 1 to verify DB reachable
    yield
    # shutdown: log


app = FastAPI(
    title="Keyword Manager API",
    version="2.1.0",
    description="AITF Tim 1 — Keyword Manager for Dashboard Monev Komdigi",
    lifespan=lifespan,
)

app.include_router(keywords.router, prefix="/keywords", tags=["Keywords"])
app.include_router(pipeline.router, prefix="/pipeline", tags=["Pipeline"])
```

---

## 7. API CONTRACT (FastAPI)

All responses are JSON. All timestamps are ISO 8601 UTC strings.
All list endpoints support `?limit=50&offset=0`. Default limit: 50. Max limit: 200.
Return `400 Bad Request` if limit > 200.

---

### 7.1 Keyword Endpoints (public — no auth)

**GET /keywords/enriched?limit=50&offset=0**

```json
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

**GET /keywords/{id}**

Full detail including articles, justification, enrichment.

```json
{
  "id": 1,
  "keyword": "kenaikan BBM",
  "source": "trends24",
  "rank": 3,
  "status": "enriched",
  "failure_reason": null,
  "scraped_at": "2026-04-10T08:00:00Z",
  "updated_at": "2026-04-10T08:12:00Z",
  "articles": [
    {
      "id": 10,
      "source_site": "detik",
      "url": "https://detik.com/example",
      "title": "Pemerintah Naikkan Harga BBM",
      "crawled_at": "2026-04-10T08:03:00Z"
    }
  ],
  "justification": {
    "is_relevant": true,
    "justification": "Artikel membahas kebijakan energi pemerintah.",
    "llm_model": "anthropic/claude-3-haiku",
    "processed_at": "2026-04-10T08:07:00Z"
  },
  "enrichment": {
    "expanded_keywords": ["harga BBM", "subsidi energi", "pertamina"],
    "llm_model": "anthropic/claude-3-haiku",
    "processed_at": "2026-04-10T08:10:00Z"
  }
}
```

**GET /keywords/expired?limit=50&offset=0**

Paginated wrapper. Same item shape as enriched list but without `expanded_keywords`.

**GET /keywords/failed?limit=50&offset=0**

Returns failed keywords. Includes `failure_reason` field.

**GET /keywords/status/{status}?limit=50&offset=0**

Paginated wrapper filtered by any valid status value.
Return `400 Bad Request` if status is not in `KeywordStatus.ALL`.

---

### 7.2 Pipeline Control Endpoints (require X-API-Key header)

**POST /pipeline/trigger**

Request body:
```json
{ "source": "all" }
```
`source` must be one of: `"trends24"`, `"google_trends"`, `"all"`.

Responses:
- `202 Accepted`:
  ```json
  {"triggered": true, "scrape_run_id": 42, "message": "Scrape cycle started."}
  ```
- `409 Conflict`:
  ```json
  {"detail": "A scrape cycle is already running."}
  ```
- `401 Unauthorized`:
  ```json
  {"detail": "Invalid or missing API key."}
  ```

**POST /pipeline/expire**

Manually trigger all three passes of the expiry job.

Responses:
- `202 Accepted`: `{"triggered": true, "message": "Expiry job started."}`
- `401 Unauthorized`

**POST /pipeline/retry-failed**

Immediately reset all `failed` keywords to `raw` without waiting for the auto-retry
window. Useful during debugging.

Responses:
- `200 OK`: `{"reset_count": 7}`
- `401 Unauthorized`

**GET /pipeline/health** (public — no auth)

```json
{
  "counts": {
    "raw": 3,
    "news_sampled": 1,
    "llm_justified": 2,
    "enriched": 47,
    "expired": 12,
    "failed": 0
  },
  "last_scrape": {
    "scrape_run_id": 42,
    "source": "all",
    "started_at": "2026-04-10T08:00:00Z",
    "finished_at": "2026-04-10T08:01:12Z",
    "keywords_inserted": 4,
    "status": "done"
  }
}
```

`last_scrape` is the most recent row in `scrape_runs` ordered by `started_at DESC`.
If no scrape has run yet: `"last_scrape": null`.

---

## 8. ENVIRONMENT VARIABLES

`.env` — never commit.
`.env.example` — commit with placeholder values.

```env
# PostgreSQL
POSTGRES_USER=aitf
POSTGRES_PASSWORD=change_me_in_production
POSTGRES_DB=aitf_keywords
POSTGRES_HOST=postgres
POSTGRES_PORT=5432
DATABASE_URL=postgresql+asyncpg://aitf:change_me_in_production@postgres:5432/aitf_keywords
DATABASE_URL_SYNC=postgresql+psycopg2://aitf:change_me_in_production@postgres:5432/aitf_keywords

# OpenRouter
OPENROUTER_API_KEY=sk-or-replace-me
LLM_MODEL=anthropic/claude-3-haiku
LLM_MAX_CALLS_PER_MINUTE=20

# Scraper
SCRAPE_WINDOW_MINUTES=120

# Sampler
SAMPLER_POLL_INTERVAL_SECONDS=30
SAMPLER_BATCH_SIZE=5
MAX_ARTICLES_PER_CRAWLER=2
MAX_ARTICLES_TOTAL_PER_KEYWORD=5
SUMMARY_CHAR_THRESHOLD=3000

# LLM Service
LLM_POLL_INTERVAL_SECONDS=30
LLM_BATCH_SIZE=10

# Expiry Job
EXPIRY_THRESHOLD_HOURS=6
IRRELEVANT_EXPIRY_HOURS=24
FAILED_RETRY_MINUTES=30
EXPIRY_CHECK_INTERVAL_MINUTES=30

# API
API_HOST=0.0.0.0
API_PORT=8000
API_SECRET_KEY=change_me_in_production

# Demo
DEMO_PORT=8501
API_BASE_URL=http://api:8000
```

`DATABASE_URL_SYNC` is used by Alembic only. All application code uses `DATABASE_URL`.
Never construct the DATABASE_URL by concatenating POSTGRES_* parts in application code —
read it as a single variable.

---

## 9. IMPLEMENTATION ORDER

Implement in this exact sequence. Do not start a step until the previous step passes
its smoke test. Each step ends with a commit.

```
Step 1 — Repository setup
  - Create branch feat/v2-pipeline
  - Delete all old service files
  - Create full directory structure from Section 4
  - Add .gitignore and .env.example
  Commit: "infra: initial repository structure"

Step 2 — Shared package
  - Implement shared/shared/constants.py
  - Implement shared/shared/db.py
  - Implement shared/shared/models.py
  - Implement shared/pyproject.toml
  Smoke test: python -c "from shared.constants import KeywordStatus; print(KeywordStatus.ALL)"
  Commit: "shared: implement constants, db, models"

Step 3 — Alembic and schema
  - Install alembic, configure alembic.ini and alembic/env.py
  - Run: alembic revision --autogenerate -m "initial schema"
  - Review generated file — confirm all 5 tables, indexes, trigger
  - Run: alembic upgrade head
  Smoke test: connect to DB, verify all 5 tables exist with correct columns
  Commit: "schema: add initial alembic migration"

Step 4 — Scraper library
  - Port trends24.py from old codebase, clean up
  - Port google_trends.py from old codebase, clean up (no pytrends)
  - Implement delta.py
  Smoke test: run trends24 and google_trends locally, verify list[dict] return
  Commit: "scraper: port and clean up trends24, google_trends, implement delta"

Step 5 — Sampler service
  - Implement summarizer.py
  - Implement crawler.py (all 3 crawlers)
  - Implement main.py
  Smoke test: manually insert a keyword with status=raw, run sampler,
              verify articles in DB and keyword status=news_sampled
  Commit: "sampler: implement crawler and polling loop"

Step 6 — LLM client
  - Implement client.py with rate limiting
  - Implement prompts.py
  Smoke test: instantiate OpenRouterClient, call chat() with test message,
              verify string response without hitting rate limit
  Commit: "llm: implement OpenRouter client with rate limiting"

Step 7 — LLM justifier
  - Implement justifier.py
  Smoke test: run against a keyword with status=news_sampled,
              verify keyword_justifications row and status=llm_justified
  Commit: "llm: implement justifier"

Step 8 — LLM enricher and main loop
  - Implement enricher.py
  - Implement main.py
  Smoke test: run against a relevant keyword,
              verify keyword_enrichments row and status=enriched
  Commit: "llm: implement enricher and main loop"

Step 9 — Expiry service
  - Implement expiry/main.py (all 3 passes)
  Smoke test 1: set article crawled_at to 7h ago, run expiry, verify status=expired
  Smoke test 2: set keyword status=failed with old updated_at, run expiry,
                verify status=raw and failure_reason=NULL
  Commit: "expiry: implement three-pass cleanup"

Step 10 — API service
  - Implement auth.py
  - Implement schemas.py
  - Implement routers/keywords.py
  - Implement routers/pipeline.py (with idempotency)
  - Implement main.py
  Smoke test: curl GET /pipeline/health -> 200
  Smoke test: curl POST /pipeline/trigger (no key) -> 401
  Smoke test: curl POST /pipeline/trigger (with key) -> 202
  Smoke test: curl POST /pipeline/trigger (again immediately) -> 409
  Smoke test: curl GET /keywords/enriched -> paginated JSON
  Commit: "api: implement all endpoints with auth and idempotency"

Step 11 — Streamlit demo
  - Implement demo/app.py (Section 11)
  Smoke test: streamlit run app.py, all 5 pages render without error
  Commit: "demo: implement stakeholder dashboard"

Step 12 — Docker Compose
  - Write docker-compose.yml
  - Write Dockerfiles for all services
  - Run: docker compose up --build
  - Verify all containers start and pass healthchecks
  End-to-end test: POST /pipeline/trigger -> wait -> GET /keywords/enriched
                   returns items with non-empty expanded_keywords
  Commit: "infra: docker compose and dockerfiles"

Step 13 — Tests
  - Write tests/conftest.py with all fixtures
  - Write all test files (Section 13)
  - Run: pytest tests/ -v
  - All tests must pass
  Commit: "tests: full pytest suite"
```

---

## 10. DOCKER & DEPLOYMENT

### docker-compose.yml

```yaml
version: "3.9"

services:

  postgres:
    image: postgres:15-alpine
    environment:
      POSTGRES_USER: ${POSTGRES_USER}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
      POSTGRES_DB: ${POSTGRES_DB}
    volumes:
      - pgdata:/var/lib/postgresql/data
    ports:
      - "5432:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER}"]
      interval: 10s
      timeout: 5s
      retries: 5
    restart: unless-stopped

  sampler:
    build:
      context: .
      dockerfile: services/sampler/Dockerfile
    env_file: .env
    depends_on:
      postgres:
        condition: service_healthy
    healthcheck:
      test: >
        ["CMD", "python", "-c",
        "import os,time; age=time.time()-os.path.getmtime('/tmp/sampler_heartbeat.txt'); exit(0 if age<120 else 1)"]
      interval: 60s
      timeout: 10s
      retries: 3
    restart: unless-stopped

  llm:
    build:
      context: .
      dockerfile: services/llm/Dockerfile
    env_file: .env
    depends_on:
      postgres:
        condition: service_healthy
    healthcheck:
      test: >
        ["CMD", "python", "-c",
        "import os,time; age=time.time()-os.path.getmtime('/tmp/llm_heartbeat.txt'); exit(0 if age<120 else 1)"]
      interval: 60s
      timeout: 10s
      retries: 3
    restart: unless-stopped

  expiry:
    build:
      context: .
      dockerfile: services/expiry/Dockerfile
    env_file: .env
    depends_on:
      postgres:
        condition: service_healthy
    healthcheck:
      test: >
        ["CMD", "python", "-c",
        "import os,time; age=time.time()-os.path.getmtime('/tmp/expiry_heartbeat.txt'); exit(0 if age<3600 else 1)"]
      interval: 300s
      timeout: 10s
      retries: 3
    restart: unless-stopped

  api:
    build:
      context: .
      dockerfile: services/api/Dockerfile
    env_file: .env
    ports:
      - "8000:8000"
    depends_on:
      postgres:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/pipeline/health"]
      interval: 30s
      timeout: 10s
      retries: 3
    restart: unless-stopped

  demo:
    build:
      context: .
      dockerfile: services/demo/Dockerfile
    env_file: .env
    ports:
      - "8501:8501"
    depends_on:
      - api
    restart: unless-stopped

volumes:
  pgdata:
```

Note: No `scraper` service in docker-compose.yml.

### Dockerfile template

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install shared package (dedicated layer for cache efficiency)
COPY shared/ /shared
RUN pip install --no-cache-dir -e /shared

# Install service dependencies
COPY services/<service_name>/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy service source
COPY services/<service_name>/ .

CMD ["python", "main.py"]
```

For the `api` service Dockerfile, also copy the scraper library:
```dockerfile
COPY services/scraper/ /app/scraper/
```

### Cloud deployment

On GCP Cloud Run or AWS ECS:
- Each docker-compose service maps to a separate Cloud Run service or ECS task.
- `postgres` maps to Cloud SQL (GCP) or RDS (AWS).
- Use Secret Manager (GCP) or AWS Secrets Manager for all `.env` values.
- `shared/` is baked into each image during build — no shared filesystem needed.
- `# TODO(team4): finalize VPC, cloud provider, and secret management before production.`

---

## 11. STREAMLIT DEMO SPEC

File: `services/demo/app.py`

The demo is read-only. It calls FastAPI endpoints only.
It does NOT connect to PostgreSQL directly.
It does NOT hold or use `DATABASE_URL`.
It only needs `API_BASE_URL` from env.

```python
import httpx, os, time
import streamlit as st

API = os.environ["API_BASE_URL"]


def get(path: str, params: dict = None) -> dict:
    """GET from FastAPI. Raises st.error on failure."""
    try:
        r = httpx.get(f"{API}{path}", params=params, timeout=10.0)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        st.error(f"API error: {e}")
        return {}
```

**Pages (implemented with `st.sidebar` navigation):**

**1. Pipeline Overview**
- Call `GET /pipeline/health`.
- Show `counts` as `st.bar_chart`.
- Show `last_scrape` fields as `st.metric` widgets: started_at, keywords_inserted, status.
- Auto-refresh every 30s using `time.sleep(30)` then `st.rerun()`.

**2. Trending Keywords**
- Call `GET /keywords/status/raw?limit=200` and `GET /keywords/status/news_sampled?limit=200`.
- Merge items, display as `st.dataframe`.
- Columns: keyword, source, rank, scraped_at, status.
- Add `st.selectbox` for source filter: All / trends24 / google_trends.

**3. Relevance Results**
- Call `GET /keywords/status/llm_justified?limit=200`.
- Display as `st.dataframe`.
- Color-code rows: green for `is_relevant=true`, red for false.
- Columns: keyword, is_relevant, justification, llm_model, processed_at.

**4. Enriched Keywords**
- Call `GET /keywords/enriched?limit=200`.
- Columns: keyword, expanded_keywords (join as comma-separated string), processed_at.

**5. Failed Keywords**
- Call `GET /keywords/failed?limit=200`.
- Columns: keyword, failure_reason, updated_at.
- Display note: "Failed keywords are automatically retried after FAILED_RETRY_MINUTES minutes."

---

## 12. LLM PROMPT TEMPLATES

File: `services/llm/prompts.py`

---

```python
"""LLM prompt templates for the justifier and enricher modules."""

from shared.constants import SUMMARY_CHAR_THRESHOLD


JUSTIFIER_SYSTEM = """
You are a content relevance classifier for a government issue monitoring system
operated by the Indonesian Ministry of Communication and Informatics (Komdigi).

Your task: determine whether a trending keyword is related to Indonesian government
affairs. Relevant topics include: ministry activities, public policy, regulations,
government programs, state-owned enterprises (BUMN), parliamentary proceedings,
court rulings affecting public policy, or government-linked institutions.

You will receive a keyword and samples of news articles about it.
Base your decision on the article content, not just the keyword text alone.

Respond ONLY with a valid JSON object. No text before or after the JSON.

Format when relevant:
{"is_relevant": true, "justification": "<reason in Indonesian, max 2 sentences>"}

Format when not relevant:
{"is_relevant": false, "justification": "<reason in Indonesian, max 2 sentences>"}
"""


def build_justifier_prompt(keyword: str, article_context: str) -> str:
    """Build the user message for the justifier LLM call."""
    return f"""Keyword trending: {keyword}

Sampel artikel:
{article_context}

Apakah keyword ini berkaitan dengan isu pemerintahan Indonesia?"""


ENRICHER_SYSTEM = """
You are a keyword expansion assistant for a government issue monitoring system
operated by the Indonesian Ministry of Communication and Informatics (Komdigi).

Your task: given a trending keyword and sample news articles about it, generate
related search keywords that will help a crawler find more government-relevant
articles on the same topic.

Rules:
- Generate 5 to 10 expanded keywords.
- All keywords must be in Indonesian.
- Base keywords strictly on the article content — do not invent unrelated terms.
- Each keyword must be specific and directly related to the government topic.
- Avoid generic terms such as: "berita", "indonesia", "terbaru", "informasi".
- Keep each keyword concise: 1 to 4 words.

Respond ONLY with a valid JSON object. No text before or after the JSON.

Format:
{"expanded_keywords": ["keyword1", "keyword2", "keyword3"]}
"""


def build_enricher_prompt(keyword: str, article_context: str) -> str:
    """Build the user message for the enricher LLM call."""
    return f"""Keyword utama: {keyword}

Sampel artikel:
{article_context}

Hasilkan keyword pencarian yang relevan berdasarkan artikel di atas."""


def build_article_context(articles: list) -> str:
    """
    Build a compact article context string for LLM prompts.
    Uses summary if available, otherwise truncates body to SUMMARY_CHAR_THRESHOLD.
    Numbers each article for readability.
    """
    parts = []
    for i, article in enumerate(articles, 1):
        content = (
            article.summary
            if article.summary
            else (article.body or "")[:SUMMARY_CHAR_THRESHOLD]
        )
        title = article.title or "(no title)"
        parts.append(f"[Artikel {i}] {title}\n{content}")
    return "\n\n".join(parts)


def build_messages(system: str, user: str) -> list[dict]:
    """Build the messages list for an OpenRouter chat completion request."""
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
```

---

## 13. TESTING REQUIREMENTS

Use `pytest` with `pytest-asyncio`. Decorate all async tests with `@pytest.mark.asyncio`.

### tests/conftest.py fixtures

| Fixture           | Type          | Description                                                       |
|-------------------|---------------|-------------------------------------------------------------------|
| `test_session`    | async fixture | Isolated AsyncSession using a test DB; rolls back after each test |
| `mock_llm_client` | fixture       | Returns valid JSON strings without network calls                  |
| `sample_keyword`  | async fixture | Keyword ORM object with `status=raw`, persisted in test DB        |
| `sample_articles` | async fixture | 3 Article ORM objects linked to `sample_keyword`                  |

For `test_session`: use a dedicated `aitf_test` database. Apply `alembic upgrade head`
before the test session starts. Wrap each test in a transaction that is rolled back on
teardown so tests are fully isolated.

---

### Required tests

| File | Test name | What to verify |
|------|-----------|----------------|
| test_scraper.py | `test_trends24_returns_list` | Returns `list[dict]` with keys keyword, rank, source |
| test_scraper.py | `test_google_trends_returns_list` | Same shape, source = "google_trends" |
| test_delta.py | `test_delta_excludes_existing` | Keyword already in DB window is excluded |
| test_delta.py | `test_delta_case_insensitive` | "APBN" and "apbn" are treated as the same |
| test_delta.py | `test_delta_cross_source` | Same text from different source is NOT a delta |
| test_delta.py | `test_delta_passes_new_keyword` | Keyword not in window is included in delta |
| test_sampler.py | `test_crawlers_return_articles` | At least 1 crawler returns articles for "APBN" |
| test_sampler.py | `test_url_deduplication_in_memory` | Duplicate URLs removed before DB insert |
| test_sampler.py | `test_article_total_capped` | Total articles per keyword <= MAX_ARTICLES_TOTAL |
| test_sampler.py | `test_body_null_when_summary_generated` | Long body -> body=NULL, summary populated |
| test_sampler.py | `test_status_failed_on_exception` | Unhandled exception -> keyword.status = failed |
| test_sampler.py | `test_status_news_sampled_on_zero_articles` | 0 articles found -> status = news_sampled (with warning) |
| test_justifier.py | `test_saves_justification_row` | KeywordJustification row created |
| test_justifier.py | `test_status_becomes_llm_justified` | keyword.status = llm_justified after call |
| test_justifier.py | `test_parse_error_fallback` | Bad JSON -> retries once -> is_relevant=False, no exception |
| test_justifier.py | `test_llm_error_sets_failed` | LLMError -> keyword.status = failed with reason |
| test_enricher.py | `test_saves_enrichment_row` | KeywordEnrichment row created |
| test_enricher.py | `test_status_becomes_enriched` | keyword.status = enriched after call |
| test_enricher.py | `test_fallback_on_parse_error` | Bad JSON after retry -> expanded = [original keyword] |
| test_enricher.py | `test_llm_error_sets_failed` | LLMError -> keyword.status = failed with reason |
| test_expiry.py | `test_pass1_expires_stale_enriched` | Enriched keyword with old crawled_at -> expired |
| test_expiry.py | `test_pass1_keeps_fresh_enriched` | Enriched keyword with recent crawled_at -> stays enriched |
| test_expiry.py | `test_pass2_expires_irrelevant` | Old irrelevant llm_justified keyword -> expired |
| test_expiry.py | `test_pass3_resets_failed` | Old failed keyword -> raw, failure_reason=NULL |
| test_expiry.py | `test_pass3_keeps_recent_failed` | Recently failed keyword -> not reset yet |
| test_api.py | `test_health_returns_all_statuses` | All 6 statuses in counts including failed |
| test_api.py | `test_health_last_scrape_null_if_none` | No scrape run -> last_scrape=null |
| test_api.py | `test_trigger_requires_api_key` | POST without X-API-Key -> 401 |
| test_api.py | `test_trigger_accepts_valid_key` | POST with valid key -> 202 |
| test_api.py | `test_trigger_idempotency_409` | Second trigger while running -> 409 |
| test_api.py | `test_enriched_list_paginated` | GET /keywords/enriched returns total, limit, offset, items |
| test_api.py | `test_invalid_status_400` | GET /keywords/status/nonsense -> 400 |
| test_api.py | `test_retry_failed_resets_keywords` | POST /pipeline/retry-failed -> reset_count > 0 |

---

## FINAL CHECKLIST FOR AGENT

Before marking implementation complete, verify every item below.

**Schema**
- [ ] All 5 tables exist: keywords, articles, keyword_justifications, keyword_enrichments, scrape_runs
- [ ] `keywords.status` CHECK constraint includes `failed`
- [ ] `keywords.failure_reason` column exists (TEXT, nullable)
- [ ] `articles.url` has a UNIQUE constraint at DB level
- [ ] `updated_at` trigger exists on `keywords` table
- [ ] All indexes from Section 5 exist

**Services**
- [ ] No standalone scraper container in docker-compose.yml
- [ ] Scraper library is imported by api service, not a separate process
- [ ] Every polling query uses `.with_for_update(skip_locked=True)`
- [ ] Sampler sets `body=NULL` when summary is generated
- [ ] Total articles capped at `MAX_ARTICLES_TOTAL_PER_KEYWORD` after merging crawlers
- [ ] `INSERT INTO articles ... ON CONFLICT (url) DO NOTHING` used
- [ ] LLM rate limiter is implemented and tested
- [ ] `LLMError` is raised and correctly sets `status=failed` in both modules
- [ ] Expiry job runs all three passes
- [ ] Pass 3 resets failed keywords to raw and clears failure_reason
- [ ] Every service writes a heartbeat file for its healthcheck
- [ ] Commit happens after EACH keyword in LLM loop (not after full batch)

**API**
- [ ] All POST control endpoints require and validate `X-API-Key`
- [ ] GET endpoints have no auth requirement
- [ ] All list endpoints return paginated shape: total, limit, offset, items
- [ ] POST /pipeline/trigger returns 409 when a cycle is already running
- [ ] POST /pipeline/trigger inserts a scrape_run row before firing BackgroundTask
- [ ] GET /pipeline/health includes `failed` count and `last_scrape` from scrape_runs
- [ ] GET /keywords/status/{invalid} returns 400

**Streamlit demo**
- [ ] Demo holds only API_BASE_URL, not DATABASE_URL
- [ ] All 5 pages implemented: Overview, Trending, Relevance, Enriched, Failed
- [ ] All data fetched via FastAPI endpoints using httpx

**Infrastructure**
- [ ] All containers have `restart: unless-stopped`
- [ ] All application containers have heartbeat-based healthchecks
- [ ] Postgres credentials come from env vars in docker-compose.yml (not hardcoded)
- [ ] `shared/` is installed via `pip install -e /shared` in each Dockerfile (no volume mount)
- [ ] `build: context: .` in docker-compose allows Dockerfiles to copy shared/

**Quality**
- [ ] No `print()` statements — loguru used everywhere
- [ ] All functions and modules have docstrings
- [ ] `pytest tests/ -v` passes with zero failures
- [ ] `.env.example` committed with placeholder values only
- [ ] No secrets committed to git
- [ ] All `# TODO(team4):` comments placed at integration points

---

*SPEC version: 2.1.0 — Last updated: 2026-04-11*
*Author: Danar Fathurahman — AITF Tim 1 UGM*
*Changes from v2.0.0: resolved all 20 analyst-identified gaps;*
*scraper consolidated into API as BackgroundTask; Google Trends uses existing HTTP scraper.*