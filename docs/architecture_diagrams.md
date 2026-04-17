# AITF Keyword Manager v2 — Mermaid Architecture Diagrams

## 1. System Architecture (C4-style Container Diagram)

```mermaid
graph TB
    subgraph "External Systems"
        GG["Google Trends\n(https://trends.google.com)"]
        T24["Trends24 Indonesia\n(https://trends24.in)"]
        DK["Detik.com"]
        KP["Kompas.com"]
        TB["Tribunnews.com"]
        OR["OpenRouter API\n(LLM - anthropic/claude-3-haiku)"]
        T4["Team 4\n(Consumer)"]
    end

    subgraph "keyword-scraper-2"
        subgraph "services/api"["API Service (FastAPI :8000)"]
            API["FastAPI App"]
            SCR["Scraper Library\n(BackgroundTask)"]
            AUTH["X-API-Key Auth"]
        end

        subgraph "services/sampler"["Sampler Service"]
            SM["run_sampler()"]
            CR["crawler.py\n(detik/kompas/tribun)"]
            SM_HB["/tmp/sampler_heartbeat.txt"]
        end

        subgraph "services/llm"["LLM Service"]
            JUST["justify_keyword()\nPhase 1: Justifier"]
            ENRICH["enrich_keyword()\nPhase 2: Enricher"]
            CLIENT["OpenRouterClient\n(Semaphore rate limit)"]
            LLM_HB["/tmp/llm_heartbeat.txt"]
        end

        subgraph "services/expiry"["Expiry Service"]
            EXP["run_expiry_job()\n(APScheduler cron)"]
            EXP_HB["/tmp/expiry_heartbeat.txt"]
        end

        subgraph "services/demo"["Demo Dashboard (Streamlit :8501)"]
            ST["Streamlit App\n(Read-only, no DB access)"]
            P01["P01 Pipeline Overview"]
            P02["P02 Trending Keywords"]
            P03["P03 Relevance Results"]
            P04["P04 Enriched Keywords"]
            P05["P05 Failed Keywords"]
        end

        subgraph "PostgreSQL"
            PG["keywords\narticles\nkeyword_justifications\nkeyword_enrichments\nscrape_runs"]
        end
    end

    %% API triggers scraper
    API -->|"POST /pipeline/trigger"| SCR
    API -->|"BackgroundTask"| SCR

    %% Scraper writes to DB
    SCR -->|"INSERT keywords\n(status=raw)"| PG

    %% Sampler reads/writes
    PG -->|"SELECT status=raw\nFOR UPDATE SKIP LOCKED"| SM
    SM --> CR
    CR --> DK
    CR --> KP
    CR --> TB
    DK -->|"Article content"| SM
    KP -->|"Article content"| SM
    TB -->|"Article content"| SM
    SM -->|"INSERT articles\nUPDATE status=news_sampled"| PG
    SM --> SM_HB

    %% LLM reads/writes
    PG -->|"SELECT status=news_sampled"| JUST
    JUST --> CLIENT
    CLIENT --> OR
    OR -->|"{is_relevant, justification}"| JUST
    JUST -->|"UPSERT keyword_justifications\nUPDATE status=llm_justified"| PG

    PG -->|"SELECT status=llm_justified\n+ is_relevant=true"| ENRICH
    ENRICH --> CLIENT
    CLIENT --> OR
    OR -->|"{expanded_keywords}"| ENRICH
    ENRICH -->|"UPSERT keyword_enrichments\nUPDATE status=enriched"| PG
    LLM_HB -.->|"heartbeat"| SM_HB

    %% Expiry reads/writes
    EXP -->|"Pass 1: stale enriched"| PG
    EXP -->|"Pass 2: irrelevant"| PG
    EXP -->|"Pass 3: retry failed"| PG
    EXP --> EXP_HB

    %% Demo reads via API
    ST -->|"GET /keywords/enriched"| API
    ST -->|"GET /pipeline/health"| API
    ST --> P01
    ST --> P02
    ST --> P03
    ST --> P04
    ST --> P05

    %% Team 4 consumes
    API -->|"GET /keywords/enriched"| T4

    %% Auth
    T4 -->|"X-API-Key header"| AUTH
    AUTH --> API

    style API fill:#2d6a4f,color:#fff
    style SCR fill:#40916c,color:#fff
    style SM fill:#52b788,color:#fff
    style JUST fill:#74c69d,color:#000
    style ENRICH fill:#74c69d,color:#000
    style EXP fill:#95d5b2,color:#000
    style ST fill:#b7e4c7,color:#000
    style PG fill:#1d3557,color:#fff
```

---

## 2. Keyword Lifecycle State Machine

```mermaid
stateDiagram-v2
    [*] --> raw
    raw --> news_sampled : sampler crawls articles
    news_sampled --> llm_justified : justifier classifies
    llm_justified --> enriched : is_relevant=true
    llm_justified --> expired : is_relevant=false (24h)
    enriched --> expired : stale > 6h
    enriched --> failed_keyword : LLM permanent failure
    news_sampled --> failed_keyword : LLM permanent failure
    failed_keyword --> raw : expiry retry (30 min)

    note right of raw
        Status values:
        raw, news_sampled,
        llm_justified,
        enriched, expired, failed
    end note
```

---

## 3. Database ER Diagram

```mermaid
erDiagram
    KEYWORDS {
        int id PK
        text keyword "NOT NULL"
        text source "NOT NULL, CHECK (trends24|google_trends)"
        int rank "nullable"
        timestamptz scraped_at "NOT NULL, DEFAULT NOW()"
        text status "NOT NULL, CHECK (raw|news_sampled|llm_justified|enriched|expired|failed)"
        text failure_reason "nullable"
        timestamptz updated_at "NOT NULL, auto-updated"
    }

    ARTICLES {
        int id PK
        int keyword_id FK "NOT NULL, ON DELETE CASCADE"
        text source_site "NOT NULL, CHECK (detik|kompas|tribun)"
        text url "NOT NULL, UNIQUE"
        text title "nullable"
        text body "nullable"
        text summary "nullable"
        timestamptz crawled_at "NOT NULL, DEFAULT NOW()"
    }

    KEYWORD_JUSTIFICATIONS {
        int id PK
        int keyword_id FK "NOT NULL, UNIQUE, ON DELETE CASCADE"
        boolean is_relevant "NOT NULL"
        text justification "nullable"
        text llm_model "NOT NULL"
        timestamptz processed_at "NOT NULL, DEFAULT NOW()"
    }

    KEYWORD_ENRICHMENTS {
        int id PK
        int keyword_id FK "NOT NULL, UNIQUE, ON DELETE CASCADE"
        jsonb expanded_keywords "NOT NULL, string[]"
        jsonb source_article_ids "nullable, int[]"
        text llm_model "NOT NULL"
        timestamptz processed_at "NOT NULL, DEFAULT NOW()"
    }

    SCRAPE_RUNS {
        int id PK
        text source "NOT NULL, CHECK (trends24|google_trends|all)"
        timestamptz started_at "NOT NULL, DEFAULT NOW()"
        timestamptz finished_at "nullable"
        int keywords_inserted "NOT NULL, DEFAULT 0"
        text status "NOT NULL, CHECK (running|done|failed)"
    }

    KEYWORDS ||--o{ ARTICLES : "1 keyword → many articles"
    KEYWORDS ||--o| KEYWORD_JUSTIFICATIONS : "1 keyword → 0-1 justification"
    KEYWORDS ||--o| KEYWORD_ENRICHMENTS : "1 keyword → 0-1 enrichment"
    KEYWORDS ||--o{ SCRAPE_RUNS : "1 scrape_run → many keywords"
```

---

## 4. Polling Query Pattern (All Services)

```mermaid
sequenceDiagram
    participant S as Service
    participant PG as PostgreSQL
    participant HB as Heartbeat

    loop Every poll interval
        S->>PG: SELECT ... WHERE status=X
        Note over PG: FOR UPDATE SKIP LOCKED
        PG->>S: N keyword rows (locked)
        S->>S: Process each keyword
        S->>PG: UPDATE keywords SET status=Y
        S->>HB: Write timestamp
    end

    Note over S,PG: SKIP LOCKED prevents race conditions
    Note over S,PG: Multiple instances can run safely
```

---

## 5. API Endpoint Flow

```mermaid
graph LR
    subgraph "Team 4 / External Client"
        TRIGGER["POST /pipeline/trigger\n(X-API-Key required)"]
        HEALTH["GET /pipeline/health"]
        STUCK["GET /pipeline/stuck"]
        ENRICHED["GET /keywords/enriched"]
        DETAIL["GET /keywords/{id}"]
        STATUS["GET /keywords/status/{status}"]
        RETRY["POST /pipeline/retry-failed\n(X-API-Key required)"]
    end

    subgraph "FastAPI (services/api/main.py)"
        AUTH["X-API-Key Auth\n(Security dependency)"]
        TRIG["POST /trigger → ScrapeRun + BackgroundTask"]
        SCR["Scraper Library\n(BackgroundTask)"]
        HLTH["/health → keyword counts + scrape_runs"]
        STCK["/stuck → stuck alerts + throughput"]
        ENRCH["/enriched → paginated enriched keywords"]
        DTL["/{id} → full detail + articles + justification + enrichment"]
        STAT["/status/{status} → filter by status/source/since"]
        RTRY["/retry-failed → UPDATE failed → raw"]
    end

    subgraph "PostgreSQL"
        KW["keywords table"]
        ART["articles table"]
        JUST["keyword_justifications table"]
        ENR["keyword_enrichments table"]
        RUN["scrape_runs table"]
    end

    TRIGGER --> AUTH --> TRIG --> SCR
    SCR -->|"INSERT keywords (raw)"| KW

    HEALTH --> HLTH --> KW
    STUCK --> STCK --> KW
    ENRICHED --> ENRCH --> KW
    DETAIL --> DTL --> KW
    DETAIL --> ART
    DETAIL --> JUST
    DETAIL --> ENR
    STATUS --> STAT --> KW
    RETRY --> AUTH --> KW

    style TRIGGER fill:#e63946,color:#fff
    style RETRY fill:#e63946,color:#fff
    style HEALTH fill:#457b9d,color:#fff
    style ENRICHED fill:#457b9d,color:#fff
    style AUTH fill:#f4a261,color:#000
```

---

## 6. Sampler Data Flow

```mermaid
graph TD
    START["keyword.status = raw"] --> POLL["SELECT FOR UPDATE SKIP LOCKED\nbatch_size=5"]

    POLL --> GATHER["asyncio.gather()"]
    GATHER -->|"detik.com"| DK["crawl_detik(keyword)\nmax 2 articles"]
    GATHER -->|"kompas.com"| KP["crawl_kompas(keyword)\nmax 2 articles"]
    GATHER -->|"tribunnews.com"| TB["crawl_tribun(keyword)\nmax 2 articles"]

    DK --> UNIQ["Deduplicate by URL\nmax 5 total articles"]
    KP --> UNIQ
    TB --> UNIQ

    UNIQ --> BODY{"body length\n> 3000 chars?"}
    BODY -->|yes| TRUNC["truncate body to 3000\nstore summary"]
    BODY -->|no| KEEP["keep full body\nsummary=NULL"]
    TRUNC --> INSERT["INSERT articles\nON CONFLICT DO NOTHING"]
    KEEP --> INSERT

    INSERT --> UPDATE["UPDATE keyword.status\n= 'news_sampled'"]

    UPDATE --> SLEEP["Sleep 30s\nreturn to POLL"]

    style POLL fill:#2d6a4f,color:#fff
    style INSERT fill:#40916c,color:#fff
    style UPDATE fill:#52b788,color:#fff
```

---

## 7. LLM Service — Justifier & Enricher Flow

```mermaid
graph TD
    subgraph "Phase 1: Justifier"
        J_POLL["SELECT status=news_sampled\nbatch_size=10\nFOR UPDATE SKIP LOCKED"]
        J_ART["build_article_context()\ntruncate articles to token limit"]
        J_PROMPT["JUSTIFIER_SYSTEM prompt\n+ article context"]
        J_CALL["OpenRouter API\nPOST /chat/completions"]
        J_RESP["Parse {is_relevant: bool, justification: str}"]
        J_RESP -->|valid| J_UPSERT["UPSERT keyword_justifications\nis_relevant, justification, llm_model, processed_at"]
        J_UPSERT --> J_STATUS["UPDATE keyword.status\n= 'llm_justified'"]
        J_STATUS --> J_NEXT["Next keyword"]
        J_RESP -->|parse error| J_FALLBACK["fallback is_relevant=false"]
        J_FALLBACK --> J_FAIL["UPDATE keyword.status\n= 'failed'\nfailure_reason=LLM_PARSE_ERROR"]
        J_CALL -->|429/5xx after 3 retries| J_ERR["LLMError → set status=failed\nfailure_reason=LLM_PERMANENT_FAILURE"]
    end

    subgraph "Phase 2: Enricher"
        E_POLL["SELECT status=llm_justified\n+ keyword_justifications.is_relevant=true\nFOR UPDATE SKIP LOCKED"]
        E_BUILD["build_article_context()\ntruncate articles"]
        E_PROMPT["ENRICHER_SYSTEM prompt\n+ article context"]
        E_CALL["OpenRouter API\nPOST /chat/completions"]
        E_RESP["Parse {expanded_keywords: list[str]}"]
        E_RESP -->|valid| E_UPSERT["UPSERT keyword_enrichments\nexpanded_keywords (JSONB), llm_model, processed_at"]
        E_UPSERT --> E_STATUS["UPDATE keyword.status\n= 'enriched'"]
        E_STATUS --> E_NEXT["Next keyword"]
        E_RESP -->|parse error| E_FALLBACK["fallback expanded=[keyword.keyword]"]
        E_FALLBACK --> E_STATUS
        E_CALL -->|429/5xx after 3 retries| E_ERR["LLMError → set status=failed"]
    end

    J_NEXT --> E_POLL

    style J_POLL fill:#2d6a4f,color:#fff
    style E_POLL fill:#2d6a4f,color:#fff
    style J_CALL fill:#e63946,color:#fff
    style E_CALL fill:#e63946,color:#fff
```

---

## 8. Expiry Service — Three Pass Flow

```mermaid
graph TD
    START["APScheduler trigger\n(every 30 minutes)"]

    subgraph "Pass 1: Stale Enriched"
        P1["SELECT status=enriched\nJOIN articles ON keyword.id=articles.keyword_id\nGROUP BY keyword.id"]
        P1 --> P1_CHECK{"MAX(articles.crawled_at)\nvs now > 6 hours?"}
        P1_CHECK -->|yes| P1_EXP["UPDATE keyword.status\n= 'expired'"]
        P1_CHECK -->|no| P1_SKIP["Skip — still fresh"]
    end

    subgraph "Pass 2: Irrelevant Justified"
        P2["SELECT status=llm_justified\nJOIN keyword_justifications\nWHERE is_relevant=false"]
        P2 --> P2_CHECK{"keyword_justifications.processed_at\nvs now > 24 hours?"}
        P2_CHECK -->|yes| P2_EXP["UPDATE keyword.status\n= 'expired'"]
        P2_CHECK -->|no| P2_SKIP["Skip — too recent"]
    end

    subgraph "Pass 3: Retry Failed"
        P3["SELECT status=failed"]
        P3 --> P3_CHECK{"keyword.updated_at\nvs now > 30 minutes?"}
        P3_CHECK -->|yes| P3_RETRY["UPDATE keyword.status\n= 'raw'\nClear failure_reason"]
        P3_CHECK -->|no| P3_SKIP["Skip — not ready"]
    end

    START --> P1
    P1_SKIP --> P2
    P1_EXP --> P2
    P2_SKIP --> P3
    P2_EXP --> P3

    P1_EXP --> FINISH["Write heartbeat\n/tmp/expiry_heartbeat.txt"]
    P1_SKIP --> FINISH
    P2_EXP --> FINISH
    P2_SKIP --> FINISH
    P3_RETRY --> FINISH
    P3_SKIP --> FINISH

    P3_RETRY -->|"Next cycle"| P3b["Sampler picks up\nstatus=raw again"]

    style START fill:#e63946,color:#fff
    style P1_EXP fill:#f4a261,color:#000
    style P2_EXP fill:#f4a261,color:#000
    style P3_RETRY fill:#52b788,color:#fff
```

---

## 9. Scraper Delta Detection Flow

```mermaid
graph LR
    START["Scheduler triggers\nPOST /pipeline/trigger"]

    SCRape["Scrape both sources\nconcurrently via crawl4ai"]
    SCRape --> T24["Trends24 → list[dict]\n{keyword, rank, source=trends24}"]
    SCRape --> GT["Google Trends → list[dict]\n{keyword, rank, source=google_trends}"]

    T24 --> MERGE["Merge all keywords\ndedupe by lowercase keyword"]
    GT --> MERGE

    MERGE --> DELTA["delta.py check\nSCRAPE_WINDOW_MINUTES=120"]

    subgraph "Delta Detection"
        DELTA --> LOOKUP["SELECT keyword, MAX(scraped_at)\nFROM keywords\nWHERE scraped_at > (now - 120min)"]
        LOOKUP --> KNOWN["Build set of\nrecently-seen keywords"]
        DELTA --> NEW["Filter: only keep keywords\nNOT in recently-seen set"]
    end

    NEW --> INSERT["INSERT keywords\n(status=raw)\nReturn count"]

    INSERT --> IDEM["Create ScrapeRun row\nstatus=running"]
    IDEM --> DONE["Return 200 OK\nkeywords_inserted=N"]

    MERGE --> EXISTING["Keywords already in DB\nwithin window → skipped"]

    style INSERT fill:#2d6a4f,color:#fff
    style NEW fill:#52b788,color:#fff
    style EXISTING fill:#e63946,color:#fff
```

---

## 10. Streamlit Demo Dashboard Structure

```mermaid
graph TD
    ST["Streamlit App (:8501)\nservices/demo/app.py"]
    NAV["Sidebar Radio Buttons\n(5 navigation options)"]

    ST --> NAV

    NAV -->|"Option 1"| P01["P01 Pipeline Overview"]
    NAV -->|"Option 2"| P02["P02 Trending Keywords"]
    NAV -->|"Option 3"| P03["P03 Relevance Results"]
    NAV -->|"Option 4"| P04["P04 Enriched Keywords"]
    NAV -->|"Option 5"| P05["P05 Failed Keywords"]

    subgraph "Shared Components"
        API["_api.py\nhttpx client → FastAPI"]
        MODELS["_models.py\nDataclass response models"]
        THEME["_theme.py\nDark theme CSS injection"]
        CMPS["components/\n_metric_card, _status_badge\n_freshness_indicator, _detail_expander"]
    end

    P01 --> API
    P02 --> API
    P03 --> API
    P04 --> API
    P05 --> API

    P01 --> MODELS
    P02 --> MODELS
    P03 --> MODELS
    P04 --> MODELS
    P05 --> MODELS

    P01 --> CMPS
    P02 --> CMPS
    P03 --> CMPS
    P04 --> CMPS
    P05 --> CMPS

    API -->|"GET /pipeline/health"| FP["FastAPI (:8000)"]
    API -->|"GET /keywords/enriched"| FP
    API -->|"GET /keywords/status/{status}"| FP

    subgraph "P01 Metrics"
        M1["Total keywords by status"]
        M2["Last scrape run info"]
        M3["Stuck keyword alerts"]
        M4["Throughput KPIs"]
        M5["Status distribution bar chart"]
    end
    P01 --> M1 & M2 & M3 & M4 & M5

    subgraph "P02 Filters"
        F2["Source filter\n(trends24 / google_trends)"]
        F3["Time range filter\n(since timestamp)"]
    end
    P02 --> F2 & F3

    subgraph "P03 Color Coding"
        C3["is_relevant=true → green"]
        C4["is_relevant=false → red/orange"]
    end
    P03 --> C3 & C4

    subgraph "P04 Chips"
        C4["expanded_keywords\ndisplayed as chips/tags"]
    end
    P04 --> C4

    subgraph "P05 Details"
        F5["failure_reason displayed\nfor each failed keyword"]
    end
    P05 --> F5

    style ST fill:#1d3557,color:#fff
    style API fill:#2d6a4f,color:#fff
    style FP fill:#457b9d,color:#fff
```

---

## 11. Complete Data Flow (Full Pipeline)

```mermaid
flowchart LR
    subgraph "Trigger"
        SCH["Team 4 Scheduler\nor Manual trigger"]
    end

    subgraph "1. Scrape"
        TRIGGER["POST /pipeline/trigger"]
        SCR["Scraper BackgroundTask"]
        T24["Trends24"]
        GT["Google Trends"]
        DELTA["delta.py filter"]
        KW_RAW["keywords: raw"]
    end

    subgraph "2. Sample"
        SM["Sampler Service\npoll: status=raw"]
        DK["Detik"]
        KP["Kompas"]
        TB["Tribun"]
        ART["articles"]
        KW_SAMPLED["keywords: news_sampled"]
    end

    subgraph "3. Justify (LLM)"
        JUST["LLM Justifier\npoll: status=news_sampled"]
        OR1["OpenRouter\n{is_relevant, justification}"]
        JUSTIF["keyword_justifications"]
        KW_JUST["keywords: llm_justified"]
    end

    subgraph "4. Enrich (LLM)"
        ENRICH["LLM Enricher\npoll: llm_justified\n+ is_relevant=true"]
        OR2["OpenRouter\n{expanded_keywords}"]
        ENRCH["keyword_enrichments"]
        KW_ENR["keywords: enriched"]
    end

    subgraph "5. Expire (Cron)"
        EXP["Expiry Service\nevery 30 min"]
        E1["Pass 1: stale enriched"]
        E2["Pass 2: irrelevant"]
        E3["Pass 3: retry failed"]
        KW_EXP["keywords: expired\nor back to raw"]
    end

    subgraph "6. Consume"
        API_ENRICH["GET /keywords/enriched"]
        T4["Team 4 API Consumer"]
    end

    SCH --> TRIGGER --> SCR
    SCR --> T24
    SCR --> GT
    GT --> DELTA
    T24 --> DELTA
    DELTA --> KW_RAW
    KW_RAW --> SM
    SM --> DK & KP & TB
    DK & KP & TB --> ART
    ART --> KW_SAMPLED
    KW_SAMPLED --> JUST
    JUST --> OR1
    OR1 --> JUSTIF
    JUSTIF --> KW_JUST
    KW_JUST --> ENRICH
    ENRICH --> OR2
    OR2 --> ENRCH
    ENRCH --> KW_ENR
    KW_ENR --> EXP
    EXP --> E1 & E2 & E3
    E1 & E2 & E3 --> KW_EXP
    KW_ENR --> API_ENRICH
    API_ENRICH --> T4

    style SCH fill:#e63946,color:#fff
    style T4 fill:#e63946,color:#fff
    style KW_RAW fill:#2d6a4f,color:#fff
    style KW_SAMPLED fill:#40916c,color:#fff
    style KW_JUST fill:#52b788,color:#fff
    style KW_ENR fill:#74c69d,color:#000
    style KW_EXP fill:#95d5b2,color:#000
```