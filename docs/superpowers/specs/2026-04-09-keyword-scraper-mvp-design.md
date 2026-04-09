# Keyword Scraper MVP — Design Spec

**Date:** 2026-04-09
**Project:** Keyword Scraper → Keyword Manager → Keyword Expander pipeline
**Context:** Early Warning System for Indonesian social media (Kementerian Komdigi)

---

## Overview

A microservice-ready MVP that scrapes trending keywords from Google Trends and Trends24 Indonesia, lets users filter and validate them through rule-based and AI-powered pipelines, and expands relevant keywords into variants for downstream social media scraping (Phase 2).

**Out of scope:** Social media scraping, sentiment analysis, trend detection, alerting.

---

## 1. Schema

### Keyword Table

| Field | Type | Description |
|---|---|---|
| `id` | UUID v4 | Primary key |
| `keyword` | string | The keyword itself |
| `source` | enum: `GTR`, `T24` | Origin platform |
| `scraped_at` | ISO8601 datetime | When scraped |
| `rank` | integer | Original rank from source at scrape time |
| `status` | enum | `raw` → `filtered` → `fresh` → `expanded` |
| `expand_trigger` | null, `manual`, `high_trend` | What triggered expansion |
| `expanded_variants` | JSON array of strings | Deprecated; use separate rows instead |
| `ready_for_scraping` | boolean | Phase 2 consumption flag |
| `parent_id` | UUID v4, nullable | Links expanded variant to parent keyword |

### Status Lifecycle

```
raw → filtered → fresh → expanded
```

- `raw`: freshly scraped, not yet processed
- `filtered`: failed rule-based filter
- `fresh`: passed both rule-based and AI filters
- `expanded`: variants have been generated

---

## 2. Deduplication Logic

When a new scrape runs:

| Existing Status | Behavior |
|---|---|
| `fresh` | Keep status, update `rank` and `scraped_at` |
| `expanded` | Keep status, update `rank` and `scraped_at` |
| `raw` | Update `rank` and `scraped_at`, re-evaluate on next filter run |
| `filtered` | Update `rank` and `scraped_at`, re-evaluate on next filter run |

---

## 3. Keyword Scraper

### Sources
- **Google Trends Indonesia** (`GTR`): `https://trends.google.com/trending?geo=ID&category=10`
- **Trends24 Indonesia** (`T24`): `https://trends24.in/indonesia/`

### Behavior
- Max 100 keywords per source
- Scraped on-demand via user action in Streamlit
- Stored in SQLite via SQLAlchemy 2.0

### Failure Handling
- If a source fails, show error message in UI; other source continues
- No automatic retry on failure (user can re-click)

---

## 4. Keyword Manager

### Stage A: Rule-Based Filter

**Default signals** (from existing `filters.py`, ~80 governance/public-interest terms):
`korupsi`, `kpk`, `suap`, `bansos`, `gempa`, `bpjs`, `apbn`, `phk`, `banjir`, `pilkada`, `parpol`, etc.

**Matching:** Word-boundary regex (`\b`) to avoid false positives (e.g., `anak` in `anak saya` won't match seed `anak`).

**User customization:** Toggleable chips UI — default all ON. User can add/remove signals per session. Changes are session-only, not persisted.

**Behavior:** "Apply Filter" only targets `raw` status keywords. Existing `filtered` keywords are left untouched.

### Stage B: AI Filter (OpenRouter)

**Trigger:** User selects keywords → clicks "Classify via OpenRouter"

**Classification:** Binary — relevant or not relevant for government/public interest/politics in Indonesia.

**Batching:** All selected keywords classified in a **single API call** using a structured prompt. Do NOT make per-keyword calls.

**Model selection:** User selects from dropdown in Streamlit. Default: `google/gemma-4-26b-a4b-it:free` (fast/cheap). Option for `qwen/qwen3.6-plus` (higher quality).

**Output:** Relevant → status=`fresh`. Not relevant → keyword is deleted.

**Error handling:** On failure, show error; keywords remain in previous status.

---

## 5. Fresh Keywords

- Table view of all `fresh` keywords
- User can manually select keywords → click "Send to Expander"
- `ready_for_scraping = true` for all fresh keywords (Phase 2 can poll this)

---

## 6. Keyword Expander

**Trigger:** Only on explicit user click ("Expand" button).

**Auto high-trend:** Top 5 `fresh` keywords by rank are visually flagged as "high trend" candidates, but expansion only fires when user clicks.

**Behavior:** For selected keyword(s), generate expanded variants (e.g., `gempa` → `gempa bumi`, `gempa jakarta`, `gempa hari ini`).

**Output:** New keyword rows created with:
- `parent_id` = ID of parent keyword
- `status` = `expanded`
- `expand_trigger` = `manual` or `high_trend` (based on rank)
- `ready_for_scraping = true`

**Variant generation:** Via OpenRouter — single batch prompt with all keywords to expand.

**Deduplication:** If a variant already exists as a keyword in any status, skip it.

---

## 7. FastAPI Endpoints

| Method | Endpoint | Purpose |
|---|---|---|
| `POST` | `/scrape` | Trigger keyword scrape from both sources |
| `GET` | `/keywords` | List all keywords (filter by `status`, `source`) |
| `GET` | `/keywords/fresh` | List fresh keywords (Phase 2 primary entry point) |
| `POST` | `/keywords/filter` | Apply rule-based filter to `raw` keywords |
| `POST` | `/keywords/classify` | Apply OpenRouter AI filter |
| `POST` | `/keywords/{id}/expand` | Expand single keyword |
| `POST` | `/keywords/expand/batch` | Bulk expand selected keywords |
| `DELETE` | `/keywords/{id}` | Delete a keyword |
| `GET` | `/health` | Health check |

All endpoints return JSON. OpenAPI docs at `/docs`.

---

## 8. Tech Stack

| Layer | Choice | Notes |
|---|---|---|
| UI | Streamlit (latest) | No custom CSS |
| API | FastAPI 0.115+ | Runs alongside Streamlit |
| ORM | SQLAlchemy 2.0 | SQLite MVP; swap to PostgreSQL by changing connection string |
| Scrape lib | crawl4ai (existing) | Already in project |
| AI | OpenRouter + pydantic | API key via `OPENROUTER_API_KEY` env var |
| Batch AI | Single prompt batch | Never per-keyword calls |

**SQLite → PostgreSQL migration:** Change one connection string in `config.py`. Use Alembic for schema migrations when moving to Phase 2 infra.

---

## 9. Streamlit Pages

### Page 1: 🔍 Scrape
- Button: "Run Scrape"
- On click: scrape GTR + T24 → store in DB
- Table: `keyword | source | rank | status`
- Show scrape result summary

### Page 2a: 📋 Rule Filter
- Chip/toggle list of governance signals (default all ON)
- User can add/remove signals per session
- Button: "Apply Filter" → applies to all `raw` keywords

### Page 2b: 🤖 AI Filter
- Select multiple keywords via checkbox
- Dropdown: model selection (Haiku default / Sonnet option)
- Button: "Classify via OpenRouter"
- Progress indicator during API call
- Results: relevant → `fresh`, not relevant → deleted

### Page 3: ✨ Fresh Keywords
- Table of all `fresh` keywords
- Checkbox selection + "Send to Expander" button
- Visual flag for top 5 (high trend candidates)

### Page 4: 🔎 Expand
- Shows selected keywords from Fresh page (or auto-loaded top 5)
- Button: "Expand Selected"
- Table: original keyword | expanded variants | trigger reason
- New rows appear in DB with `parent_id` linking

---

## 10. Phase 2 Integration Points

Phase 2 (social media scraper team) consumes from:

1. **`GET /keywords/fresh`** — poll for all fresh keywords with `ready_for_scraping=true`
2. **`GET /keywords?status=expanded`** — get expanded variants with `parent_id` for lineage
3. Database direct access (shared PostgreSQL instance post-migration)

---

## 11. Decisions Log

| Decision | Resolution |
|---|---|
| Schema: remove `kategori_utama`, `sub_kategori`, `sentimen`, `prioritas` | Removed — Phase 2 handles categorization |
| Geo field | Removed — not needed for MVP |
| Rule filter matching | Word-boundary regex (`\b`) to reduce false positives |
| AI classification | Binary (relevant / not relevant), batch in single API call |
| Status undo/revert | Not needed — deduplication logic handles re-scraped keywords |
| Expand trigger | Only on explicit user click; top 5 flagged as high-trend candidates |
| Deduplication on scrape | Fresh/expanded keep status; raw/filtered re-evaluate |
| API key management | Via `OPENROUTER_API_KEY` env var only |
