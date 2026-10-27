# Review Intelligence MVP SaaS

Turn Google Play Store and Apple App Store customer reviews into an actionable, prioritized, version-aware product feedback report powered by Google Gemini and deterministic statistical formulas.

---

## 1. Architecture Overview

```mermaid
flowchart TD
    subgraph Store_Sources[Data Sources: India Storefront ('in')]
        PS[Google Play Store API]
        AS[Apple App Store Public RSS Feed]
    end

    subgraph Pipeline[Pipeline Engine (s01 - s07)]
        S1[s01_collect: Scrape & Snapshot raw_reviews.csv]
        S2[s02_clean: NFKC, PII Scrub, Hinglish Script Filter, RapidFuzz Dedupe]
        S3[s03_sample_taxonomy: Stratified Sample + LLM Taxonomy Discovery]
        S4[s04_classify: Multi-Label Batch Classification + Checkpointing]
        S5[s05_reconcile: LLM Proposal Clustering + Expanded Taxonomy]
        S6[s06_summarize: Proof-Ranking D7 + Deterministic Priority + Executive Synthesis]
        S7[s07_aggregate: Distributions, Version Progression, Heatmap, Resolution Signals]
    end

    subgraph Persistence[Persistence & Caching]
        DB[(SQLite WAL: app.db)]
        CACHE[(SHA-256 Prompt Disk Cache: llm_cache/)]
        ARTIFACTS[Run Directory: data/runs/run_id/]
    end

    subgraph Delivery[Delivery & UI]
        API[FastAPI REST API]
        DASH[Single-Page Dashboard /dashboard: Alpine.js/Vanilla + Chart.js]
    end

    PS --> S1
    AS --> S1
    S1 --> S2 --> S3 --> S4 --> S5 --> S6 --> S7
    S1 -. Snapshot .-> ARTIFACTS
    S3 -. Cache .-> CACHE
    S4 -. Cache .-> CACHE
    S6 -. Cache .-> CACHE
    Pipeline --> DB
    Pipeline --> ARTIFACTS
    DB --> API
    ARTIFACTS --> API
    API --> DASH
```

---

## 2. Key Design Decisions

| Decision | Implementation | Rationale |
|---|---|---|
| **D1: Stratified Sampling** | Stratify by store × star bucket × version. Clamped to min 150, max 300. | Avoids biasing complaint categories toward a single version or time window. |
| **D2: Review Type Gate** | Gate into `complaint`, `praise`, `feature_request`, `question`, `spam_or_irrelevant`. | Prevents 5-star compliments from polluting complaint categories. |
| **D3: Null Bucket** | Stored as `null` for vague complaints lacking actionable detail (e.g. "worst app"). | Distinct from spam/praise; acts as an actionable clarification target list. |
| **D4: Multi-Label** | Output CSV has one row per (review, category) assignment. | Real-world customer reviews routinely describe multiple distinct issues. |
| **D5: Taxonomy Reconciliation** | Classification returns proposed categories; clusters them into new categories or maps to `other`. | Captures emerging issues that did not appear in the initial sample. |
| **D6: Ordinal Scoring** | 1–5 ordinal relevance and severity; score exposed as `relevance / 5.0`. | Self-reported LLM confidence percentages are poorly calibrated. |
| **D7: Proof Review Ranking** | Composite score: `0.5*rel_norm + 0.2*sev_norm + 0.15*thumbs_norm + 0.15*recency_norm`. | Balances relevance with social proof and freshness. |
| **D8: State Persistence** | SQLite WAL for status and metadata; CSV/JSON files for auditability. | Fast indexing and clean immutable file exports. |
| **D9: Reproducibility Contract** | Run dir stores `config.json`, raw snapshot, artifacts, and SHA-256 prompt cache. | Guarantees identical outputs upon snapshot replay with `reuse_snapshot: true`. |
| **D10: Hinglish Support** | Unicode script ratio (≥70% Latin letters) keeps English & Hinglish. | Preserves the high volume of Hinglish reviews common in the Indian market. |
| **D11: PII Scrubbing** | Regex strips Indian mobile numbers (`+91`/10-digit 6–9) and email addresses. | User privacy and security before sending text to LLM or dashboard. |
| **D12: India Storefront Focus** | Country fixed to `in` for both stores. | Streamlines scraping coherence; App Store cap is ~500 for India. |
| **D13: Gemini Integration** | Google Gemini via official `google-genai` SDK with JSON structured schemas. | Cost-effective, high context window, fast structured generation. |

---

## 3. Quickstart

### Prerequisites
- Docker & Docker Compose **OR** Python 3.11+
- Google Gemini API Key (`GEMINI_API_KEY`)

### Option A: Run via Docker Compose (Recommended)

1. Clone and configure environment:
   ```bash
   cp .env.example .env
   # Edit .env and enter your GEMINI_API_KEY
   ```

2. Start the service:
   ```bash
   docker compose up --build
   ```

3. Open your browser:
   ```
   http://localhost:8000/dashboard
   ```

> **Data Persistence:** Docker Compose utilizes a named volume `review_intel_data` mapped to `/app/data` to ensure all runs, SQLite database records, and LLM caches persist across container restarts. To use a local directory bind mount instead, uncomment `./data:/app/data` in `docker-compose.yml`.

### Option B: Run Locally

1. Create and activate a virtual environment:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install --upgrade pip
   pip install -r requirements.txt
   ```

2. Set environment variables:
   ```bash
   export GEMINI_API_KEY="your_api_key_here"
   export LLM_MODEL="gemini-2.5-flash"
   export DATA_DIR="./data"
   ```

3. Run the application:
   ```bash
   uvicorn app.main:app --host 0.0.0.0 --port 8000
   ```
   Access the dashboard at `http://localhost:8000/dashboard`.

---

## 4. CLI Shortcuts & Standalone Execution

Every pipeline stage is idempotent and can be executed independently from the command line:

```bash
# Execute Stage 1: Review Collection
python -m app.pipeline.s01_collect --run-id <run_id>

# Execute Stage 2: Data Cleaning & Deduplication
python -m app.pipeline.s02_clean --run-id <run_id>

# Execute Stage 3: Stratified Taxonomy Discovery
python -m app.pipeline.s03_sample_taxonomy --run-id <run_id>

# Execute Stage 4: Batch Review Classification
python -m app.pipeline.s04_classify --run-id <run_id>

# Execute Stage 5: Taxonomy Reconciliation
python -m app.pipeline.s05_reconcile --run-id <run_id>

# Execute Stage 6: Category Summarization & Action Plan
python -m app.pipeline.s06_summarize --run-id <run_id>

# Execute Stage 7: Metrics Aggregations & Version Signals
python -m app.pipeline.s07_aggregate --run-id <run_id>
```

### Running Tests
```bash
# Run complete test suite (unit, API contracts, e2e, reproducibility)
pytest -v
```

### Running Smoke Test
```bash
# Run offline smoke test with synthetic fixtures (no API key needed)
python scripts/smoke.py --offline --sample-size 50

# Run live smoke test against Swiggy Play Store reviews
python scripts/smoke.py --app-name "Swiggy" --play-package "in.swiggy.android" --sample-size 50
```

---

## 5. API Reference

All responses use JSON format. Domain errors return standard error structures:
```json
{
  "error": {
    "code": "APP_NOT_FOUND",
    "message": "Human readable explanation",
    "details": {},
    "retryable": false
  }
}
```

### App Validation
- `POST /apps/validate`
  - Validates store package IDs and numeric IDs against official store endpoints.
  - Body: `{"stores": ["playstore", "appstore"], "play_package": "in.swiggy.android", "appstore_id": "989506690", "app_name": "Swiggy", "country": "in"}`
  - Returns metadata (icon, current version, rating, reviews count) and App Store search candidates if ID is omitted.

### Run Lifecycle
- `POST /runs` — Submit and queue an analysis run (returns `201 {"run_id": "...", "status": "queued"}`).
- `GET /runs` — List analysis runs with status, review counts, and estimated cost.
- `GET /runs/{run_id}` — Get detailed run state, stage progression checkpoints, timings, warnings, and error details.
- `GET /runs/{run_id}/logs?lines=100` — Live tail of `data/runs/<run_id>/logs/pipeline.log`.
- `POST /runs/{run_id}/cancel` — Cooperative cancellation between batches.
- `POST /runs/{run_id}/resume` — Resume an interrupted or failed run from its last checkpoint.
- `POST /runs/{run_id}/rerun` — Spawn a new run. Body option `{"reuse_snapshot": true}` replays against prior raw snapshot with hot LLM cache.

### Reporting & Exports
- `GET /runs/{id}/report` — Unified dashboard payload (executive summary, action plan, charts, issues, unaddressed feedback).
- `GET /runs/{id}/categories` — List of categories with priority rankings and version signals.
- `GET /runs/{id}/categories/{cat_id}/reviews?limit=50&sort=score` — Proof reviews supporting a category.
- `GET /runs/{id}/null-reviews?unaddressed_only=true` — Vague complaints requiring user clarification.
- `GET /runs/{id}/versions` — Semantic version metrics table.
- `GET /runs/{id}/export/{artifact}` — Downloadable artifact CSV or JSON (`reviews_clean`, `classifications`, `taxonomy`, `summary`, `aggregates`, `raw_reviews`, `unaddressed_feedback`).

---

## 6. Pipeline Stages & Data Contracts

Each analysis run creates an isolated directory in `data/runs/<run_id>/`:

| File | Purpose | Stage |
|---|---|---|
| `config.json` | Inputs, random seed, Git SHA, model name, prompt versions | Init / s01 |
| `raw_reviews.csv` | Immutable scrape snapshot (never modified) | s01_collect |
| `reviews_clean.csv` | Sanitized, deduplicated, PII-scrubbed reviews | s02_clean |
| `taxonomy.json` | Discovered complaint categories from stratified sample | s03_sample_taxonomy |
| `classifications.csv` | Multi-label assignments with relevance and severity | s04_classify |
| `classification_batches/` | Checkpointed batch JSON files for crash recovery | s04_classify |
| `taxonomy_final.json` | Reconciled taxonomy with clustered categories | s05_reconcile |
| `summary.json` | Executive summary, category deep-dives, action plan | s06_summarize |
| `aggregates.json` | Chart data, version table, heatmap, version signals | s07_aggregate |
| `llm_cache/` | SHA-256 prompt-keyed cached responses (D9) | s03, s04, s05, s06 |
| `logs/pipeline.log` | Execution log stream | All |

---

## 7. Known Constraints & Design Limitations

1. **Apple App Store Review Cap (~500 for India):** The public Apple iTunes RSS feed serves a maximum of 10 pages × 50 entries = ~500 reviews for any specific storefront country (`country=in`). If a user requests a sample size of 1000 across both stores, the system scrapes up to 1000 from Play Store and caps at ~500 for App Store, issuing a `STORE_LIMIT_REACHED` warning.
2. **Apple RSS Developer Replies:** Public App Store RSS feeds do not contain developer responses. App Store reviews set `dev_reply=""` and `has_dev_reply=null` (unknown). The UI labels these as "N/A for App Store" rather than claiming unaddressed.
3. **Single Uvicorn Worker Design:** The server runs with a single worker (`--workers 1`) to preserve SQLite Write-Ahead Logging (WAL) concurrency and ensure the background thread executor safely manages pipeline execution without database lock contention.
4. **Heuristic Version Signals:** Version trajectory signals (`likely_resolved`, `regression`, `persistent`) are mathematical heuristics comparing relative complaint share between release versions; they are labeled as heuristic insights, not certified facts.
5. **India Storefront Focus (v1):** Both Play Store and App Store are locked to `country="in"`. Multi-country storefront aggregation is planned for v2.
6. **Gemini Free-Tier Rate Limits:** The system limits concurrency to `MAX_LLM_CONCURRENCY=3` by default with exponential backoff on HTTP 429 quota responses.
