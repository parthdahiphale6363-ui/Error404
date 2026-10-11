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

### P2 to P9 Status Tracker
- **P2 Detect with Mistral**: Pending (60 candidate items generated in `data/labeled/labeled_items.jsonl`, awaiting 40 user labels)
- **P3 Consensus + review lane**: Pending
- **P4 Risk Index**: Pending
- **P5 Graph Explain**: Pending
- **P6 Dashboard**: Pending
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

---

## g. Runbook
- **Backend**: `uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload`
- **Frontend**: `cd frontend && npm run dev`
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
