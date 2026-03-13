# keyword-scraper

Unified trending keyword scraper for **Google Trends** and **Trends24 Indonesia**, with a 3-stage relevance filter and taxonomy classification pipeline.  
Output: `/data/merged_trends_<YYYYMMDD_HHMMSS>.json` — schema-compliant with [`scraped_item.schema.json`](./scraped_item.schema.json).

---

## Features

| | Detail |
|---|---|
| **Sources** | Google Trends (`GTR`) · Trends24 (`T24`) |
| **Max raw keywords** | 100 per source |
| **Stage 0 — Relevance gate** | Drops K-pop fandom, hashtag noise, entertainment brands |
| **Stage 1 — Rule-based** | Seed-term match → instant label, `confidence_score: null` |
| **Stage 2 — Zero-shot NLI** | `mDeBERTa-v3-base-mnli-xnli` against 11 label descriptions |
| **Taxonomy** | 3 `kategori_utama` × 11 `sub_kategori` (see [taxonomy-kpm.json](./taxonomy-kpm.json)) |
| **Output** | `/data/merged_trends_<YYYYMMDD_HHMMSS>.json` |

---

## Project Structure

```
keyword-scraper/
├── main.py                   # Unified scraper — only entry point needed
├── pyproject.toml            # Project metadata & dependencies
├── uv.lock                   # Locked dependency tree
├── scraped_item.schema.json  # JSON Schema for output items
├── taxonomy-kpm.json         # Full category/sub-category definitions
└── data/                     # Output directory (auto-created, git-ignored)
    └── merged_trends_<timestamp>.json
```

---

## Setup

```bash
# 1. Install all dependencies
uv sync

# 2. Install Playwright browser (first time only)
uv run crawl4ai-setup
```

> **Note:** The mDeBERTa model (~180 MB) downloads automatically from Hugging Face on first run.

---

## Usage

```bash
uv run python main.py

# Or via the project script shorthand
uv run scrape
```

Sample console output:

```
[GTR] Running Stage 0 filter + classification (14 raw keywords)…
  ✗ (  4/14) SKIP [entertainment/fandom pattern]  freya jkt48
  ✓ (  9/14) KEEP  japto soerjosoemarno kpk
  ...

[T24] Running Stage 0 filter + classification (100 raw keywords)…
  ✗ (  6/100) SKIP [entertainment/fandom pattern]  #봄볕의따스함은알콩이전해준사랑
  ✓ ( 13/100) KEEP  BPJS
  ✓ ( 59/100) KEEP  Gempa
  ...

✅ Done! 79 items saved to data/merged_trends_20260313_000212.json
   GTR  → accepted:  13  skipped:   1  (of 14)
   T24  → accepted:  66  skipped:  34  (of 100)
```

---

## Classification Pipeline

### Stage 0 — Relevance Gate (blocks entertainment noise)

Applied before classification. A keyword is **dropped** if it matches any hard-block pattern, or if it contains **no governance/public-interest signal**.

| Hard-block patterns | Example |
|---|---|
| Korean / Thai / Japanese Unicode | `#봄볕의따스함은알콩이전해준사랑` |
| K-pop fandom hashtags (`#XxxDay`, `#XxxFandom` …) | `#OurHalfBeomgyuDay` |
| K-pop group / idol name fragments (50+ names) | `ENHYPEN IS SEVEN`, `beomgyu` |
| Sports merchandise brands | `Kelme`, `Erspo`, `Mills` |
| Entertainment event noise | `ON AIR WITH DJ JAEMIN`, `PRESSTOUR` |

Keywords that pass the block-list must also contain at least one signal from ~80 Indonesian governance/public-interest terms (e.g. `bpjs`, `gempa`, `kpk`, `apbn`, `banjir`, `pdp`, `netanyahu`, …).

### Stage 1 — Rule-Based Seed Match

Substring match (case-insensitive) against taxonomy seed terms. On match: label assigned instantly, `confidence_score: null`.

| Code | Parent | Example seeds |
|---|---|---|
| `IPH` | POG | korupsi, kpk, suap, lhkpn |
| `KLP` | POG | kebijakan, regulasi, e-government |
| `KPM` | POG | apbn, audit bpk, kinerja menteri |
| `KSD` | POG | judi online, hoaks, hack, phishing, scam |
| `KBS` | ECD | bansos, pkh, blt, kemiskinan |
| `ILT` | ECD | tol, krl, bts, fiber optik, satria |
| `EKD` | ECD | fintech, startup, kripto, qris |
| `KTK` | ECD | phk, umr, pengangguran, prakerja |
| `LKS` | SEH | bpjs, wabah, pandemi, puskesmas |
| `PSD` | SEH | sekolah, ppdb, literasi digital, beasiswa |
| `KSB` | SEH | banjir, gempa, longsor, bencana |

### Stage 2 — Zero-Shot NLI (mDeBERTa)

If no rule matches: `MoritzLaurer/mDeBERTa-v3-base-mnli-xnli` classifies the keyword against all 11 label descriptions. Confidence ≥ 0.75 is reliable; below that the item is still kept but flagged `is_auto_labeled: true`. On model failure: fallback `ECD > EKD`, `confidence_score: 0.1`.

---

## Output Schema

Each item in the output JSON array conforms to [`scraped_item.schema.json`](./scraped_item.schema.json):

```jsonc
{
  "id": "<uuid-v4>",
  "source_platform": "GTR",          // "GTR" | "T24"
  "keyword": "Japto Soerjosoemarno KPK",
  "url": "https://trends.google.com/trending?geo=ID",
  "scraped_at": "2026-03-13T00:02:12Z",
  "trend_date": "2026-03-13",
  "rank": 8,
  "search_volume": null,
  "volume_label": null,
  "related_queries": null,
  "geo": { "country": "ID", "region": null },
  "kategori_utama": "POG",           // POG | ECD | SEH
  "sub_kategori": "IPH",             // one of 11 codes
  "sentimen": "NET",                 // POS | NEG | NET
  "prioritas": "S",                  // T | S | R
  "is_auto_labeled": true,
  "confidence_score": null,          // null if rule-based
  "ews_flag": false,
  "ews_reason": null,
  "raw_payload": null,
  "created_at": "2026-03-13T00:02:12Z",
  "updated_at": null
}
```

---

## Configuration

All tuneable constants live at the top of `main.py`:

| Constant | Purpose |
|---|---|
| `TAXONOMY_RULES` | Seed terms per sub-category for Stage 1 |
| `_BLOCK_PATTERNS` | Regex of hard-blocked entertainment patterns (Stage 0) |
| `_RELEVANCE_SIGNALS` | Regex of required governance signal terms (Stage 0) |
| `CANDIDATE_LABELS` | Label descriptions used by mDeBERTa (Stage 2) |
| `NEGATIVE_TERMS` / `POSITIVE_TERMS` | Sentiment heuristic keywords |
| `OUTPUT_DIR` | Output path (default: `./data`) |

---

**Developed by AITF UGM Tim 1 🚀**
