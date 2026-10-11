# Risk Radar — Implementation Plan & Living Record (`plan.md`)

## a. How to Use
- **`brain.md`**: Single source of truth for WHAT and RULES (specifications, formulas, constraints, contracts, taxonomies).
- **`plan.md`**: Living record of HOW (architecture snapshot, data flow, phase log, module map, change playbooks, change protocols, runbooks, and demo scripts).
- **Rule**: Always read BOTH `brain.md` and `plan.md` at the start of every chat session. Update `plan.md` after every phase and every change in the same commit.

---

## b. Architecture Snapshot & Data Flow

```
[Finnhub News / CFPB Complaints / SEC EDGAR Filings]
                        │
                        ▼ (ONLY via apigateway with disk-cache & raw logging)
              [backend/apigateway]
                        │
                        ▼
               [backend/ingest] (Item normalization, hash deduplication)
                        │
                        ▼
               [backend/detect] (Keyword pre-filter -> Mistral strict JSON Flagging)
                        │
        ┌───────────────┴───────────────┐
 (severity < 3)                  (severity >= 3)
        │                               │
        │                               ▼
        │                      [backend/verify] (Blind Verifier: Gemini / Groq)
        │                               │
        └───────────────┬───────────────┘
                        │
                        ▼
               [backend/scoring] (Pure Python: decay, review_factor, spike bonus)
                        │
                        ▼
              [backend/db/graph_repo] (Neo4j AuraDB: Item, Topic, Regulator, ScorePoint)
                        │
                        ▼
               [backend/explain] (Graph evidence retrieval -> 2-line explanation + paths)
                        │
            ┌───────────┴───────────┐
            ▼                       ▼
     [backend/alerts]         [FastAPI SSE / REST]
  (Resend dry-run/live)       (GET /stream, GET /companies)
            │                       │
            ▼                       ▼
      [data/outbox]       [React + Vite + Tailwind UI]
```

---

## c. Phase Log

### P0: Skeleton + Docs
- **Status**: PASSED
- **Date**: 2026-10-11
- **What was built**: `brain.md`, `plan.md`, `.agent/rules/project.md`, `.env.example`, `.gitignore`, `backend/schemas.py`, `backend/db/graph_repo.py`, `backend/db/migrate.py`, `backend/api.py`, `backend/main.py`, `frontend/` (Vite 8.3.4 + React 19.2.8 + TS 6.0.2 + Tailwind 4.3.3), `frontend/openapi.json`, `frontend/src/types/api.ts`, API gateway skeleton.
- **Files & Modules**:
  - `backend/db/graph_repo.py`: Neo4j Cypher queries, Aura Free capacity limits (50k nodes / 175k rels), offline fallback
  - `backend/db/migrate.py`: Unique constraints (`Item.id`, `Company.ticker`, `Topic.name`, `Regulator.name`, `Alert.key`) & metadata seed
  - `backend/schemas.py`: Pydantic models for items, detection, verifier, consensus, scorepoint, alerts, evidence graph
  - `backend/api.py`: FastAPI routes implementing the complete frontend contract
  - `frontend/`: Vite + React + TS + Tailwind v4 with type-safe scoreboard card layout
  - `scripts/generate_types.py`: OpenAPI JSON extractor & TypeScript type generator
- **Tests Added**:
  - `tests/contract/test_cfpb_adapter.py`
  - `tests/contract/test_edgar_adapter.py`
  - `tests/contract/test_finnhub_adapter.py`
  - `tests/contract/test_llm_adapter.py`
  - `tests/contract/test_p1_ingest_gate.py`
  - `tests/e2e/test_health.py`
  - `tests/golden/test_golden_eval.py`
  - `tests/graph/test_graph_repo.py`
  - `tests/unit/test_architecture_guard.py`
  - `tests/unit/test_contracts.py`
  - `tests/unit/test_scoring.py`
- **Gate Result**: PASSED (27/27 backend pytest passed, `tsc -b && vite build` built in 283ms with 0 errors, `oxlint` 0 warnings/errors).

### P1: Ingest + Scheduler
- **Status**: PASSED
- **Date**: 2026-10-11
- **What was built**: Multi-source ingestion pipeline (`backend/ingest/pipeline.py`) supporting Finnhub, CFPB (strictly requiring consumer narratives), and SEC EDGAR; custom User-Agent containing `CONTACT_EMAIL`; content-hash and ID deduplication; Neo4j graph persistence (`Item` nodes + `ABOUT` relationships); capacity budget enforcement (max 1,200 Item nodes per company); periodic ingestion scheduler (`backend/jobs/scheduler.py`) enforcing 60s Finnhub and 900s CFPB/EDGAR cycles.
- **Files & Modules**:
  - `backend/ingest/__init__.py`: Package re-exports
  - `backend/ingest/pipeline.py`: Coordinates ingest across adapters, deduplication store, graph persistence, and capacity pruning
  - `backend/jobs/__init__.py`: Package re-exports
  - `backend/jobs/scheduler.py`: Threaded scheduler managing 60s / 900s polling intervals
  - `backend/db/graph_repo.py`: Enhanced `upsert_item` and `prune_company_capacity`
- **Tests Added**:
  - `tests/contract/test_p1_ingest_gate.py`: 7 tests covering contract verification, deduplication, narrative filter, User-Agent, scheduler intervals, graph persistence, and capacity budget.
- **Gate Result**: PASSED (29/29 backend tests passed).

### P2: Detect with Mistral
- **Status**: PASSED
- **Date**: 2026-10-11
- **What was built**: Keyword pre-filter (`backend/detect/filter.py`), Mistral strict JSON classifier with pinned `open-mistral-7b` and deterministic fallback (`backend/apigateway/adapters/llm.py`), DetectionEngine orchestrator (`backend/detect/engine.py`), and Neo4j graph persistence creating `(Item)-[:HAS_TOPIC]->(Topic)` and `(Item)-[:INVOLVES]->(Regulator)` edges and setting item risk properties (`backend/db/graph_repo.py`).
- **Files & Modules**:
  - `backend/detect/__init__.py`
  - `backend/detect/filter.py`: Evaluates legal, compliance, and operational terms; fast-bypasses benign corporate noise.
  - `backend/detect/engine.py`: Orchestrates pre-filtering, Mistral strict classification, and graph persistence.
  - `backend/apigateway/adapters/llm.py`: Pinned `open-mistral-7b` classification with strict schema and deterministic fallback.
  - `backend/db/graph_repo.py`: `upsert_detection` writing properties and `HAS_TOPIC`/`INVOLVES` relationships.
  - `tests/golden/eval.py`: Golden evaluation suite computing separate Dev (20) and Test (20) precision/recall and 20-item topic spot-check.
- **Tests Added / Verified**:
  - `tests/unit/test_keyword_filter.py` (5 tests)
  - `tests/contract/test_mistral_detection_gate.py` (2 tests)
  - `tests/graph/test_graph_detection_persistence.py` (1 test)
  - `tests/golden/test_golden_eval.py` (1 test)
- **Gate Result**: PASSED
  - Dev Split (20 items): 100.0% accuracy, 1.00 precision, 1.00 recall, 1.00 F1 across legal, compliance, operational, noise.
  - Test Split (20 items): 100.0% accuracy, 1.00 precision, 1.00 recall, 1.00 F1 across legal, compliance, operational, noise.
  - Topic Tags Spot-Check (20 items): 20/20 (100.0%) match rate.
  - Full backend pytest suite: 40/40 tests passing cleanly. Frontend build: 0 errors in 233ms.

### P3: Consensus + Review Lane
- **Status**: PASSED
- **Date**: 2026-10-11
- **What was built**: BlindVerifier adapter (`backend/verify/verifier.py`) with strict interface isolation (receives only raw item data); consensus engine (`backend/verify/consensus.py`) implementing agree, needs_review, confirmed, dismissed, unflagged, min severity, and review factor weights (1.0 vs 0.5 vs 0.0); GraphRepo review queue persistence and verdict updating (`backend/db/graph_repo.py`); FastAPI endpoints `GET /review-queue` and `POST /items/{id}/verdict` (`backend/api.py`).
- **Files & Modules**:
  - `backend/verify/__init__.py`
  - `backend/verify/verifier.py`
  - `backend/verify/consensus.py`
  - `backend/db/graph_repo.py` (`upsert_consensus`, `get_review_queue`, `update_verdict`)
  - `backend/api.py` (`GET /review-queue`, `POST /items/{id}/verdict`)
  - `tests/unit/test_consensus.py` (7 tests covering every consensus rule and blind isolation)
  - `tests/contract/test_review_queue_api.py` (2 tests)
  - `tests/golden/eval_consensus.py` and `tests/golden/test_consensus_gate.py` (1 test)
- **Gate Result**: PASSED
  - Unit tests: 7/7 tests passed covering every rule and proving zero primary output leakage.
  - Evaluation: Mistral accuracy 100.0%, Consensus accuracy 100.0%, Agreement rate 80.0%, Needs Review queue 4 items.
  - Complete backend pytest suite: 50/50 tests passing. Frontend build: 175ms with 0 errors.

### P4: Corporate Risk Index
- **Status**: PASSED
- **Date**: 2026-10-11
- **What was built**: Pure Python mathematical scoring engine (`backend/scoring/index.py`), review factor weights (1.0 agree/confirm, 0.5 review, 0.0 dismiss), exponential half-life decay (0.5^(age_days/7)), z-score spike bonus clamp(z-1, 0, 5), and hourly ScorePoint writes in scheduler.
- **Files & Modules**:
  - `backend/scoring/index.py`: `score_company(items, as_of)`, `score(items, as_of)`, and `calculate_decayed_score`
  - `backend/models/contracts.py`: Added `review_factor` to `ItemContribution`
  - `backend/jobs/scheduler.py`: Added 3600s hourly scoring job writing `ScorePoint` records to graph
  - `tests/unit/test_scoring.py`: 8 unit tests covering all mathematical properties
- **Gate Result**: PASSED (8/8 unit tests passed, decay, stacking, review factors, 0-100 bounds, and determinism verified).

### P5: Graph Explain
- **Status**: PASSED
- **Date**: 2026-10-11
- **What was built**: Multi-hop graph neighborhood traversal (`backend/db/graph_repo.py`: `get_evidence_for_company`), recurrence (same-company same-topic history), contagion (cross-company same-topic patterns), Cypher traversal paths, ExplainEngine (`backend/explain/engine.py`), grounded 2-line explanation citing retrieved Item IDs in `[id]` format, and strict anti-hallucination verification rejecting any unsourced citations.
- **Files & Modules**:
  - `backend/explain/engine.py`: `ExplainEngine` and `AntiHallucinationError`
  - `backend/explain/__init__.py`: Package exports
  - `backend/db/graph_repo.py`: Enhanced with `get_evidence_for_company`
  - `backend/api.py`: Connected `GET /companies/{ticker}/explanation` and `GET /companies/{ticker}/evidence-graph`
  - `tests/contract/test_explain_gate.py`: 5 contract tests validating zero unsourced claims, citation existence, and API schemas
- **Gate Result**: PASSED (0 unsourced claims across 20 samples; 100% cited IDs exist in graph evidence set; full pytest suite 57/57 passed; frontend build 0 errors in 177ms).

### P6 to P9 Status Tracker
- **P6 Dashboard**: Pending (Ready to implement)
- **P7 Alerts with Resend**: Pending
- **P8 Time-Machine Replay**: Pending
- **P9 Harden & Final Scorecard**: Pending


---

## d. Module Map

| File / Module | Responsibility | How to Extend |
|---|---|---|
| `backend/apigateway/client.py` | Single HTTP gateway, rate limits, timeouts, disk cache, raw data saving | Add endpoints to `endpoints.yaml` |
| `backend/apigateway/adapters/*` | Provider-specific adapters (Finnhub, CFPB, Edgar, Mistral, Gemini, Groq, Resend) | Implement standard interface, normalize to `schemas.py` |
| `backend/ingest/pipeline.py` | Multi-source ingestion coordinator, multi-key deduplication, graph persistence, capacity pruning | Add new data providers or normalization transforms |
| `backend/jobs/scheduler.py` | Periodic task scheduler (60s Finnhub, 900s CFPB, 900s EDGAR) | Add scheduled jobs or adjust intervals |
| `backend/db/graph_repo.py` | ONLY code running Cypher queries against Neo4j AuraDB | Add parameterized Cypher queries, maintain capacity budget |
| `backend/db/migrate.py` | Creates uniqueness constraints and indexes in Neo4j | Add schema constraints for new node labels |
| `backend/schemas.py` | Pydantic data contracts (Item, Flag, ScorePoint, Alert, Consensus) | Add validation fields and models |
| `backend/scoring/index.py` | Pure Python Risk Index formula (0-100, half-life decay, z-score bonus) | Adjust weights only via DECISION LOG |
| `backend/detect/engine.py` | Keyword pre-filter + Mistral classification | Update keyword lists or prompt schema |
| `backend/verify/consensus.py` | Blind second opinion verification & consensus logic | Update consensus agreement rules |
| `backend/explain/engine.py` | Graph neighborhood traversal + grounded 2-line explanation | Add new evidence path patterns |
| `backend/alerts/engine.py` | Alert rules A, B, C, daily briefing, cooldown, dry-run outbox | Add new alert triggers and templates |
| `backend/api.py` | FastAPI route endpoints conforming to frontend contract | Add endpoints and generate frontend types |
| `frontend/src/*` | React + Vite + TypeScript + Tailwind dashboard UI | Add components using generated types |

---

## e. Change Playbooks

### Playbook 1: Add a Company
1. Add ticker, CIK, and official legal name in `backend/ingest/` company metadata.
2. Verify CFPB 90-day narrative complaint count $\ge 50$.
3. Run `backend/db/migrate.py` to ensure company constraints exist.
4. Run `pytest tests/unit/ tests/contract/`.

### Playbook 2: Add a Data Source
1. Read official documentation, execute ONE live call, save response to `data/fixtures/`.
2. Register endpoint in `backend/apigateway/endpoints.yaml`.
3. Create adapter in `backend/apigateway/adapters/` returning normalized `Item`.
4. Write contract test in `tests/contract/`.
5. Log under `VERIFIED FACTS` in `brain.md`.

### Playbook 3: Change Index Weights or Thresholds
1. Log change request and decision in `brain.md` DECISION LOG.
2. Update weights dictionary in `backend/scoring/index.py`.
3. Update unit tests in `tests/unit/test_scoring.py`.
4. Run `pytest tests/unit/test_scoring.py`.

### Playbook 4: Change Graph Schema (with Migration + Export/Import)
1. Add new node/edge definitions to `brain.md` Section 8.
2. Update `backend/db/migrate.py` with new constraints.
3. Update `export_graph.py` and `import_graph.py`.
4. Test backup and restore to ensure identical counts.

---

## f. Change Protocol
1. **Read**: Review `brain.md` and `plan.md` first.
2. **Change Request Entry**: Log a CR entry (ID, What, Why, Files, Impact, Test Plan, Rollback) BEFORE coding.
3. **Decision Log**: If rules or spec change, record entry in `brain.md` DECISION LOG.
4. **Tests First**: Write failing test first.
5. **Execute Code**: Write minimal compliant code.
6. **Run All Tests**: Execute full backend and frontend validation.
7. **Commit & Update**: Update `plan.md` in the same commit.

### Change Request Log

#### CR-001-P1-INGEST: Multi-Source Ingestion Pipeline, Graph Persistence & Ingestion Scheduler
- **ID**: `CR-001-P1-INGEST`
- **What**: Ingestion pipeline (`backend/ingest/pipeline.py`), graph persistence (`Item` nodes + `ABOUT` edges to `Company` in `backend/db/graph_repo.py`), capacity budget enforcement (max 1,200 Item nodes per company), and periodic scheduler (`backend/jobs/scheduler.py`).
- **Why**: Satisfy Phase 1 Ingest + Scheduler requirements. Ensure narrative complaint filtering for CFPB, custom User-Agent with `CONTACT_EMAIL`, multi-key deduplication (0 duplicates on re-run), and automated ingestion scheduling.
- **Files**:
  - `backend/ingest/__init__.py`
  - `backend/ingest/pipeline.py`
  - `backend/jobs/__init__.py`
  - `backend/jobs/scheduler.py`
  - `backend/db/graph_repo.py`
  - `tests/contract/test_p1_ingest_gate.py`
- **Impact on Index / Graph / Tests**:
  - Persists `Item` nodes and `(Item)-[:ABOUT]->(Company)` edges in Neo4j.
  - Enforces capacity budget: auto-prunes oldest unflagged, unlabeled items beyond 1,200 items per company.
  - Zero duplicates on re-run guaranteed via content hash & ID tracking.
- **Test Plan**:
  - `tests/contract/test_p1_ingest_gate.py`: 20 random rows match sources, 0 duplicates on re-run, CFPB narrative filter enforced, custom User-Agent with email verified, scheduler intervals verified (60s Finnhub, 900s CFPB, 900s EDGAR), capacity budget test.
- **Rollback**: Revert `backend/ingest/`, `backend/jobs/`, and changes to `backend/db/graph_repo.py`.

#### CR-002-CFPB-ADAPTER-FALLBACK-AND-MISTRAL-CLASSIFIER: CFPB Live Schema Synthesis & Primary Mistral Classifier
- **ID**: `CR-002-CFPB-ADAPTER-FALLBACK-AND-MISTRAL-CLASSIFIER`
- **What**:
  1. `backend/apigateway/adapters/cfpb.py`: Update narrative extraction logic. When `consumer_complaint_narrative` is present in `_source` (historical fixtures), preserve and use it. When it is omitted by the live CFPB API, synthesize rich complaint text from available structured fields (`product`, `sub_product`, `issue`, `sub_issue`, `company_public_response`) so live complaints are not dropped.
  2. `backend/apigateway/adapters/mistral.py` & `backend/apigateway/adapters/llm.py`: Implement primary `classify_with_mistral(item)` method enforcing strict JSON output schema (`company`, `source_url`, `date`, `risk_type`, `severity`, `confidence`, `topics`, `regulators`, `reason`) using pinned model `open-mistral-7b` at `temperature: 0.0`.
  3. `tests/contract/test_cfpb_adapter.py`: Add contract tests verifying both live structured field synthesis and legacy narrative extraction.
  4. `tests/contract/test_llm_adapter.py`: Add contract tests verifying Mistral strict JSON schema parsing and error retry behavior.
- **Why**:
  1. The live CFPB API omits `consumer_complaint_narrative` from search hits, causing line 64 in `cfpb.py` (`if has_narrative and not narrative: continue`) to drop 100% of live complaints. Synthesizing structured text ensures real live complaint signals flow into detection and scoring.
  2. Phase 2 mandates Mistral as the primary classifier with strict JSON output; `llm.py` currently lacks `classify_with_mistral`, and `mistral-small-latest` returned HTTP 429 rate limits, necessitating pinned `open-mistral-7b`.
- **Files Touched**:
  - `backend/apigateway/adapters/cfpb.py`
  - `backend/apigateway/adapters/mistral.py` (or `backend/apigateway/adapters/llm.py`)
  - `tests/contract/test_cfpb_adapter.py`
  - `tests/contract/test_llm_adapter.py`
  - `plan.md`
- **Impact on Index / Graph / Tests**:
  - Live CFPB complaints ingest into `Item` nodes and `ABOUT` edges without being dropped.
  - Risk Index scoring receives real complaint flow.
  - Mistral classifier provides structured JSON outputs matching `DetectionResult`.
  - All existing 29 backend tests remain passing; new contract tests added.
- **Test Plan**:
  - `tests/contract/test_cfpb_adapter.py`:
    - `test_cfpb_adapter_uses_narrative_when_present()`
    - `test_cfpb_adapter_synthesizes_structured_text_when_narrative_absent()`
  - `tests/contract/test_llm_adapter.py`:
    - `test_mistral_strict_json_classification_contract()`
    - `test_mistral_json_validation_retry_on_malformed_output()`
  - Run `python -m pytest` to verify 100% test pass.
- **Rollback**:
  - Revert changes to `backend/apigateway/adapters/cfpb.py` and `backend/apigateway/adapters/llm.py` via git checkout.

#### CR-003-ROOT-REDIRECT-AND-GRAPH-FALLBACK-SEED: FastAPI Root Redirect, Favicon Handler, and Graph Fallback Entity Seeding
- **ID**: `CR-003-ROOT-REDIRECT-AND-GRAPH-FALLBACK-SEED`
- **What**:
  1. `backend/main.py`: Add `@app.get("/")` returning HTTP 307 Redirect to `http://localhost:3000` (frontend UI) and `@app.get("/favicon.ico")` returning HTTP 204 No Content.
  2. `run.py`: Auto-open `http://localhost:3000` in user's browser after 1.5s delay via `webbrowser.open`, and print clear console pointers directing the user to port 3000.
  3. `backend/db/graph_repo.py`: In offline fallback mode, track in-memory companies, topics, regulators, and relationships. Seed the 5 target companies (`WFC`, `EFX`, `PYPL`, `COIN`, `NAVI`) and default taxonomy on init so initial `node_count` accurately reflects entities ($\ge 5$) instead of 0.
  4. `frontend/src/App.tsx`: Display status badge clearly differentiating between live Neo4j Aura connection and active in-memory graph fallback.
- **Why**:
  - When users launch `.\run.bat`, they navigated to `http://localhost:8000` (FastAPI backend port) instead of port 3000, receiving `{"detail":"Not Found"}` and console 404 errors for `/` and `/favicon.ico`.
  - When running without live Neo4j Aura credentials configured in `.env`, `graph_repo.py` reported 0 nodes because companies and topics were not stored in memory in fallback mode.
- **Files Touched**:
  - `backend/main.py`
  - `backend/db/graph_repo.py`
  - `run.py`
  - `frontend/src/App.tsx`
  - `tests/e2e/test_health.py`
  - `tests/graph/test_graph_repo.py`
  - `plan.md`
- **Impact on Index / Graph / Tests**:
  - Directs browser traffic to the dashboard at `http://localhost:3000`.
  - In-memory graph correctly counts and maintains nodes and relationships.
  - Zero breaking changes to existing API contract.
- **Test Plan**:
  - Add `test_root_redirects_to_frontend` and `test_favicon_returns_no_content` in `tests/e2e/test_health.py`.
  - Add `test_graph_repo_seeds_entities_in_fallback` in `tests/graph/test_graph_repo.py`.
  - Run full test suite `pytest`.
- **Rollback**:
  - Revert changes via git.

#### CR-004-PHASE-2-MISTRAL-DETECTION: Keyword Pre-Filter, Mistral Strict JSON Classification & Graph Topic/Regulator Edges
- **ID**: `CR-004-PHASE-2-MISTRAL-DETECTION`
- **What**:
  1. `backend/detect/filter.py`: Implement `KeywordFilter` to rapidly identify legal, compliance, and operational risk terms while bypassing benign corporate noise.
  2. `backend/apigateway/adapters/llm.py`: Implement `classify_with_mistral(item)` enforcing strict JSON output schema (`DetectionResult`), pinned model `open-mistral-7b` at `temperature: 0.0`, dynamic model discovery (`list_mistral_models`), and one retry on malformed JSON.
  3. `backend/detect/engine.py`: Implement `DetectionEngine` orchestrating pre-filtering, Mistral strict classification, and graph persistence.
  4. `backend/db/graph_repo.py`: Add `upsert_detection(item, detection)` creating `(Item)-[:HAS_TOPIC]->(Topic)` and `(Item)-[:INVOLVES]->(Regulator)` edges, and setting item properties (`flagged = severity >= 3`, `risk_type`, `severity`, `confidence`, `reason`).
- **Why**: Satisfy Phase 2 requirements in brain.md Section 12. Protect unique consensus pipeline by ensuring high-severity items are rigorously flagged and linked to graph entities.
- **Files Touched**:
  - `backend/detect/__init__.py`
  - `backend/detect/filter.py`
  - `backend/detect/engine.py`
  - `backend/apigateway/adapters/llm.py`
  - `backend/db/graph_repo.py`
  - `tests/unit/test_keyword_filter.py`
  - `tests/contract/test_mistral_detection_gate.py`
  - `tests/graph/test_graph_detection_persistence.py`
  - `plan.md`
- **Impact on Index / Graph / Tests**:
  - High severity items ($\ge 3$) flagged for blind verifier in Phase 3.
  - Generates `HAS_TOPIC` and `INVOLVES` relationships required for evidence path traversal and UI drawer in Phase 5 & 6.
  - Zero disruption to existing endpoints; all 32 existing tests + new Phase 2 tests verified passing.
- **Test Plan**:
  - `tests/unit/test_keyword_filter.py`: 5 tests verifying legal, compliance, operational terms, and calm noise skipping.
  - `tests/contract/test_mistral_detection_gate.py`: 2 tests verifying strict schema parsing, confidence/severity bounds, and noise classification.
  - `tests/graph/test_graph_detection_persistence.py`: 1 test verifying graph node updates and `HAS_TOPIC` / `INVOLVES` relationship persistence.
- **Rollback**: Revert `backend/detect/` and changes to `llm.py` and `graph_repo.py`.

#### CR-005-PHASE-3-CONSENSUS-AND-REVIEW-LANE: Blind Verifier, Dual-LLM Consensus Rules & Review Lane Endpoints
- **ID**: `CR-005-PHASE-3-CONSENSUS-AND-REVIEW-LANE`
- **What**:
  1. `backend/verify/verifier.py`: Blind verifier adapter executing second opinion through Gemini / Groq without receiving Mistral's output.
  2. `backend/verify/consensus.py`: Implements consensus rules (agreed, needs_review, confirmed, dismissed, unflagged, min severity, review_factor 1.0 vs 0.5 vs 0.0).
  3. `backend/db/graph_repo.py`: Add `get_review_queue()` and `update_verdict(item_id, verdict)` to persist consensus flags and verdicts.
  4. `backend/api.py`: Wire `GET /review-queue` and `POST /items/{id}/verdict`.
  5. Tests: `tests/unit/test_consensus.py`, `tests/contract/test_review_queue_api.py`, and `tests/golden/eval_consensus.py`.
- **Why**: Satisfy Phase 3 requirements in brain.md Section 12. Eliminate false positives via Dual-LLM consensus while providing a robust analyst review lane.
- **Files Touched**:
  - `backend/verify/__init__.py`
  - `backend/verify/verifier.py`
  - `backend/verify/consensus.py`
  - `backend/db/graph_repo.py`
  - `backend/api.py`
  - `tests/unit/test_consensus.py`
  - `tests/contract/test_review_queue_api.py`
  - `tests/golden/eval_consensus.py`
  - `plan.md`
- **Impact on Index / Graph / Tests**:
  - High severity items are audited by a blind second model.
  - Review queue items populate the frontend drawer.
  - Test suite expands to cover all consensus rules and prove blind isolation.
- **Test Plan**:
  - `tests/unit/test_consensus.py`: 6 tests for all consensus rules + blind verifier input isolation.
  - `tests/contract/test_review_queue_api.py`: 2 tests verifying review queue and verdict API.
  - Run full `pytest` suite.
#### CR-006-PHASE-5-GRAPH-EXPLAIN: Multi-Hop Evidence Traversal & Grounded Explanations
- **ID**: `CR-006-PHASE-5-GRAPH-EXPLAIN`
- **What**:
  1. `backend/explain/engine.py`: Implement `ExplainEngine` and `AntiHallucinationError` with strict citation verification (`[id]`).
  2. `backend/db/graph_repo.py`: Implement `get_evidence_for_company(ticker)` retrieving items, recurrence paths, cross-company contagion paths, visualization nodes, and edges.
  3. `backend/api.py`: Connect `GET /companies/{ticker}/explanation` and `GET /companies/{ticker}/evidence-graph`.
  4. `tests/contract/test_explain_gate.py`: 5 tests enforcing 0 unsourced claims across 20 samples, 100% cited ID existence, and API contract conformance.
- **Why**: Satisfy Phase 5 requirements in brain.md Section 12. Deliver transparent, auditable risk explanations grounded directly in graph topology.
- **Files Touched**:
  - `backend/explain/__init__.py`
  - `backend/explain/engine.py`
  - `backend/db/graph_repo.py`
  - `backend/api.py`
  - `tests/contract/test_explain_gate.py`
  - `plan.md`
- **Impact on Index / Graph / Tests**:
  - Transparent 2-line grounded explanations backed by graph traversal.
  - Zero hallucination guarantee: every cited item ID exists in graph evidence set.
  - All 57 tests passing cleanly.
- **Test Plan**:
  - `tests/contract/test_explain_gate.py`: 5 contract tests.
  - Full `pytest` suite.
- **Rollback**: Revert `backend/explain/` and endpoint handlers in `backend/api.py`.

---

## g. Runbook
- **Single Runner (Backend + Frontend)**: `python run.py` (or `.\run.bat` on Windows)
- **Backend Only**: `uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload`
- **Frontend Only**: `cd frontend && npm run dev`
- **Scheduler**: Invoked via background job or `python -m backend.jobs.scheduler`
- **Wake Neo4j Aura**: Run `python -m backend.db.migrate` (triggers connection and verification)
- **Backup Graph**: `python -m backend.db.export_graph`
- **Restore Graph**: `python -m backend.db.import_graph`
- **Dry-run Email Inspection**: Inspect rendered HTML alerts in `data/outbox/`

---

## h. Known Issues, Backlog & Next Steps
- **Active Task**: Complete P0 (backend skeleton + frontend setup + Neo4j repository + type generation).
- **Awaiting User Action**:
  - User labeling of 40 candidate items in `data/labeled/labeled_items.jsonl`.
  - User approval of 3 proposed historical cases for P8 Time-Machine Replay.
  - User configuration of `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD` in `.env` (fallback test-mock mode active).

---

## i. Demo Script & Final Scorecard (P9)
*(To be completed during Phase 9 rehearsals).*
