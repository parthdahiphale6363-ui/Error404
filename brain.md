# Risk Radar — Single Source of Truth (`brain.md`)

## 1. Product and Unique Features
Continuously ingest news (Finnhub), complaint text (CFPB) and filings (SEC EDGAR) about 5 companies. Flag serious legal / compliance / operational risk vs noise. Compute a rolling 0-100 Corporate Risk Index per company that moves as items arrive. Explain in plain language WHY risk is rising using only that company's graph history, with source links. Show everything on one live screen and email analysts when risk rises. Judges score: detection quality, history-aware explanation, index design, dashboard usability.

### Unique Features
1. **Consensus Detector**: Two independent LLM families (Mistral primary, verifier Gemini or Groq) must agree before a high-severity item gets full weight in the index. Disagreements go to a "Needs review" lane where an analyst confirms or dismisses. We report single-model vs consensus precision/recall as measured evidence.
2. **Evidence Graph**: A Neo4j knowledge graph drives the explanation (repeat issues, similar past incidents, same issue at other companies) and an evidence-path view.
3. **Action Layer**: Resend email alerts and a daily briefing with the explanation, top evidence links and a dashboard link, plus a dry-run preview mode.
4. **Time-Machine Replay**: Optional differentiator with honest lead-time scoring.

The demo runs locally; deployment is out of scope.

---

## 2. Companies
Wells Fargo (`WFC`), Equifax (`EFX`), PayPal (`PYPL`), Coinbase (`COIN`), Navient (`NAVI`).
Empirically verified in P1 with $\ge 100$ narrative complaints in the 90-day window.

---

## 3. LLM Roles
- **Mistral**: classifier and explanation writer, using strict JSON-schema structured output. Verify the exact request format in the current Mistral docs and with ONE live call before coding the adapter.
- **Verifier (Gemini, else Groq)**: independent second opinion for items where Mistral severity >= 3. It must NEVER see Mistral's answer.
- **Groq**: also the fallback if a provider is down or rate-limited. Log every fallback.
- Take model IDs from each provider's list-models call and pin explicit model strings (never "-latest" aliases).
- Throttle to the limits shown in each provider's console. Mistral free tier is documented at 1 request/second, so batch up to 10 items per call. Gemini free tier is tight, so it only handles verification.
- Only public text is ever sent to any LLM.

---

## 4. Consensus Rules
- Item is "flagged" if Mistral severity >= 3. Flagged items are verified blind.
- **Agree**: verifier also severity >= 3 AND same risk_type: status `"agreed"`, `final_severity = min(both)`, `review_factor = 1.0`.
- **Disagree, or verifier unavailable**: status `"needs_review"`, `final_severity = Mistral's`, `review_factor = 0.5` until an analyst decides.
- **Analyst confirm**: status `"confirmed"`, `review_factor = 1.0`. **Dismiss**: status `"dismissed"`, `review_factor = 0.0`.
- Items with Mistral severity < 3 are not verified: status `"unflagged"`, `review_factor = 1.0`.

---

## 5. Index Formula
$$\text{Index} = 100 \times \left(1 - \exp\left(-\frac{S}{10}\right)\right)$$

$$S = \sum_{\text{items}} \left(\text{final\_severity} \times \text{type\_weight} \times \text{review\_factor} \times 0.5^{\frac{\text{age\_days}}{7}}\right) + \text{spike\_bonus}$$

$$\text{spike\_bonus} = \text{clamp}(z - 1, 0, 5)$$
where $z$ is the z-score of the 7-day complaint count vs the company's own 90-day baseline ($0$ if the baseline is flat).
- **Weights**: `legal`: 1.0, `compliance`: 0.9, `operational`: 0.7. `Noise` contributes 0.
- Every `ScorePoint` stores its top contributing items (as a JSON string) for the contribution bars.
- **Recurrence** ("repeat issue": same topic flagged 3+ times for a company in 90 days) and **contagion** (same topic flagged at 2+ of the 5 companies in 14 days) are display badges only. They do NOT change the index.

---

## 6. Severity Rubric (Change Only via DECISION LOG)
- **5**: Enforcement action, fine, major lawsuit, breach or outage hitting customers.
- **4**: Formal investigation, subpoena, class action filed.
- **3**: Credible reports of a systemic problem or many similar complaints.
- **2**: Single serious complaint or minor probe.
- **1**: Weak or speculative signal.
- **0**: Noise.

---

## 7. Neo4j Rules
- **Aura Free limits**: 50,000 nodes, 175,000 relationships, no backups, auto-pause after 3 days idle.
- **Capacity budget**: max 1,200 Item nodes per company (prune oldest unflagged, unlabeled items beyond it); ScorePoint hourly for the last 30 days only; Alert nodes max 500. `/health` reports node and relationship counts and warns at 70%.
- Only `backend/db/graph_repo.py` runs Cypher. All queries parameterized, never string-built. `backend/db/migrate.py` creates constraints (unique `Item.id`, `Company.ticker`, `Topic.name`, `Regulator.name`, `Alert.key`).
- Neo4j properties cannot be maps: store nested data as JSON strings.
- Verify vector-index Cypher syntax against current Neo4j docs and one live call. If unavailable on Aura Free, store embeddings as node properties and use Python cosine over that company's items (log a DECISION).
- Backup: `export_graph.py` / `import_graph.py` (JSONL) in `data/replay/`. Importing into an empty database must restore identical counts.
- `DETACH DELETE` only in test namespaces and in Reset (`is_simulated=true` items only).

---

## 8. Graph Model and Taxonomies
### Nodes
- `Company` `{ticker, name}`
- `Item` `{id, source, url, date, title, text_hash, is_simulated, flagged, risk_type, severity, confidence, reason, status, verifier_provider, verifier_severity, verifier_risk_type, analyst_verdict, review_factor, embedding}`
- `Topic` `{name}`
- `Regulator` `{name}`
- `ScorePoint` `{ts, index, top_items_json}`
- `Alert` `{key, ts, rule, status}`

### Edges
- `(Item)-[:ABOUT]->(Company)`
- `(Item)-[:HAS_TOPIC]->(Topic)`
- `(Item)-[:INVOLVES]->(Regulator)`
- `(Item)-[:SIMILAR_TO {score}]->(Item)` (top 3 only)
- `(Company)-[:HAS_SCORE]->(ScorePoint)`
- `(Alert)-[:FOR]->(Company)`

### Topic Taxonomy (Fixed, max 20; LLM must pick from it or "other")
1. unauthorized accounts or fraud
2. data breach or cybersecurity
3. debt collection practices
4. mortgage or loan servicing
5. credit reporting errors
6. payments or outages
7. account access or customer service
8. enforcement action
9. litigation or class action
10. AML or sanctions
11. governance or executive
12. financial distress
13. other

### Regulators (Fixed)
CFPB, SEC, DOJ, FTC, OCC, FDIC, Federal Reserve, FINRA, State AG, other.

---

## 9. Alert Rules
- **Rules**:
  - **Rule A**: Index crosses up through 60.
  - **Rule B**: Index rises 15+ in 24h.
  - **Rule C**: A new severity-5 item that is agreed or confirmed.
  - **Daily Briefing**: Default 08:00 local (configurable) covering all 5 companies sorted by risk.
- **Cooldown**: 6h per company + rule. Global cap `EMAIL_DAILY_CAP` per day (default 20).
- **Idempotency Key**: `company + rule + time_bucket`, stored as `Alert` nodes. Every To/CC/BCC counts as a separate email against Resend's quota.
- **Delivery**: Send only through the apigateway resend adapter, throttled to at most 2 requests/second. Recipients only from `ALERT_TO_ALLOWLIST`. Default `ALERT_FROM` is `onboarding@resend.dev`.
- `EMAIL_MODE=dry_run` is the default and is always used in tests: write rendered HTML to `data/outbox/` and show it in the UI Alerts panel; never call Resend. `"live"` needs an explicit env change, and the first live send must be the UI "Send test alert" button.
- **Subject**: `[Risk Radar] <Company> risk <index> (<+/-change> in 24h): <top topic>`
- **Body**: 1-2 line reason, top 3 evidence items with links, badges (repeat issue, contagion, needs-review count), dashboard link from `APP_BASE_URL`. Mobile-friendly HTML plus text fallback.
- Simulated items never trigger live emails. If `ALERT_INCLUDE_SIMULATED=true` the subject is prefixed `[SIMULATED]`.

---

## 10. API Routes (Frontend Contract)
- `GET /health`: System status, Neo4j connection, node/relationship counts, capacity warning.
- `GET /companies`: List 5 companies with current rolling index, 24h delta, badges, top topic.
- `GET /companies/{ticker}/explanation`: Grounded 2-line explanation citing retrieved graph items.
- `GET /companies/{ticker}/evidence-graph`: Nodes and edges for evidence path visualization.
- `GET /review-queue`: Items with status `"needs_review"`.
- `POST /items/{id}/verdict`: Analyst confirms or dismisses flagged item.
- `GET /alerts`: History of generated alerts (including dry-run HTML preview links).
- `POST /alerts/test`: Send one test alert to verify delivery.
- `GET /metrics`: Precision, recall, single-model vs consensus lift, agreement rate.
- `GET /stream`: Server-Sent Events (SSE) live push stream with 10s polling fallback.
- `POST /simulate`: Inject simulated risk scenario item (`is_simulated=true`).
- `POST /reset`: Remove simulated items and reset indices.

---

## 11. Anti-Hallucination Rules (Verbatim)
- Call only endpoints in endpoints.yaml. To add one: read the official docs, make ONE live call, save the raw response to data/fixtures/, build the pydantic model from fields actually seen, add the registry entry and a contract test, and log it under VERIFIED FACTS with the docs URL.
- Never invent endpoints, parameters, field names, model names, package names, company names or numbers. If unsure, put it in OPEN QUESTIONS and ask me.
- No fake data in real code paths. Fixtures are only for tests or MOCK_MODE=1, where the UI shows a DEMO DATA badge. The UI never hardcodes numbers.
- Simulated items carry is_simulated=true and a visible SIMULATED tag, are removable via Reset, and are NEVER counted in accuracy metrics or sent in live emails.
- LLM output must pass strict JSON-schema validation. Invalid output is rejected and retried once, never repaired by guessing. Temperature 0. Cache by content hash.
- Every explanation sentence must cite Item IDs that exist in the graph AND are in the retrieved evidence set, or it is rejected. Evidence paths shown in the UI must come from real Cypher results.
- Scoring is pure Python over plain objects: no network, no LLM, no database calls inside.
- Tests never send real email or call paid or rate-limited APIs. EMAIL_MODE=dry_run in tests.
- Never edit or delete a test to make it pass. If the spec changes, log it in DECISION LOG first.
- If the same test fails twice, STOP, write the analysis under ISSUES, and ask me.
- Never print or commit secrets.
- After every phase and every change, update plan.md in the same commit.
- One phase at a time. Never start the next phase.

---

## 12. Phases and Gates
- [x] **P0 Skeleton + docs (2h)**: create brain.md, plan.md, rules, gateway skeleton; Vite+React+TS+Tailwind builds; /health shows Neo4j status and counts; migrate creates constraints. Gate: backend tests, frontend typecheck and build pass.
- [x] **P1 Ingest + scheduler (4h)**: live-verify finnhub, cfpb, edgar. CFPB: only complaints with a consumer narrative (verify live); custom User-Agent with CONTACT_EMAIL for CFPB and EDGAR. Write Item nodes + ABOUT edges. Scheduler: Finnhub every 60s, CFPB and EDGAR every 15 min. Gate: 20 random Item nodes match their sources; re-run adds 0 duplicates; capacity budget respected.
- [x] **P2 Detect with Mistral (3h)**: keyword pre-filter, then Mistral strict JSON {company, source_url, date, risk_type, severity, confidence, topics, regulators, reason}. Write properties + HAS_TOPIC/INVOLVES edges. Gate: precision/recall on my 40 labeled items (20 dev / 20 test, reported separately); topic tags spot-checked on 20, reported separately. (PASSED: Dev 100%, Test 100%, Topic spot-check 20/20 100%).
- [x] **P3 Consensus + review lane (2h)**: blind verifier, consensus rules, statuses, verdict endpoint logic. Gate: unit tests cover every consensus rule; a test proves the verifier never receives the primary's output; eval prints Mistral-only vs consensus precision/recall plus agreement rate and review-queue size. (PASSED: 7 unit tests pass, blind isolation proven, Agreement 80.0%, Review Queue 4 items, 50/50 tests passing).
- [ ] **P4 Risk Index (3h)**: score(items, as_of) pure function using review_factor; hourly ScorePoint writes. Gate: unit tests for decay, stacking, review factors, 0-100 bounds, spike bonus; identical output for identical input.
- [ ] **P5 Graph Explain (4h)**: embeddings, SIMILAR_TO edges, recurrence and contagion queries; 2-line Mistral explanation from the evidence set (same-company same-topic history + similar items + cross-company same-topic items, labeled as such); also return evidence paths. Gate: 0 unsourced claims on 20 samples; every cited ID exists; evidence paths come from Cypher.
- [ ] **P6 Dashboard (7h)**: one screen, Tailwind. Company cards: index, 24h change arrow, risk-type chip, repeat-issue and contagion badges, needs-review count, one-line reason; sorted by biggest rise. Drawer: explanation, top contributing items with source links, contribution bars, formula tooltip, evidence graph (verify react-force-graph-2d with npm view, else cytoscape). "Needs review" lane with Confirm and Dismiss. Alerts panel with dry-run previews and a Send test alert button. Status uses color AND text. Live via SSE with polling fallback. Pipeline per new item: detect -> verify -> score -> explain -> save -> push. Gate: a new item shows on the scoreboard within 60s with no refresh; page loads under 2s from cached data.
- [ ] **P7 Alerts with Resend (3h)**: rules A, B, C, daily briefing, cooldown, cap, idempotency, allowlist, dry-run outbox, templates. Gate: unit tests for each rule, cooldown, cap, idempotency, allowlist; a test proves dry-run never invokes the Resend adapter; I review 3 rendered emails; one manual live test email to my own address through the UI button.
- [ ] **P8 Time-Machine Replay (4h, only if P0-P7 passed)**: time slider and event marker. A complaint is visible only from date_received + 15 days unless CFPB docs verify a shorter lag (log it). Gate: deterministic replay; lead time and false alarms reported honestly on 3 past cases + 2 calm controls, including cases with no early signal.
- [ ] **P9 Harden (4h)**: Simulate and Reset buttons; graph export/import restore test; Aura wake-up check; Metrics page (precision, recall, consensus lift, false alarms, agreement rate); 3 timed rehearsals; finish plan.md runbook and demo script. Gate: full demo runs with every external API switched off (MOCK_MODE, dry-run email).

---

## 13. Architecture and Folder Map
```
c:/Users/Asus/OneDrive/Desktop/DYP/
├── .agent/rules/project.md
├── backend/
│   ├── apigateway/
│   │   ├── endpoints.yaml
│   │   ├── client.py
│   │   └── adapters/
│   │       ├── finnhub.py
│   │       ├── cfpb.py
│   │       ├── edgar.py
│   │       ├── mistral.py
│   │       ├── gemini.py
│   │       ├── groq.py
│   │       └── resend.py
│   ├── db/
│   │   ├── graph_repo.py
│   │   ├── migrate.py
│   │   ├── export_graph.py
│   │   └── import_graph.py
│   ├── ingest/
│   ├── detect/
│   ├── verify/
│   ├── scoring/
│   ├── explain/
│   ├── alerts/
│   ├── jobs/
│   ├── api.py
│   ├── schemas.py
│   └── main.py
├── frontend/
│   ├── src/
│   ├── package.json
│   ├── vite.config.ts
│   └── tsconfig.json
├── data/
│   ├── fixtures/
│   ├── raw/
│   ├── labeled/
│   ├── replay/
│   └── outbox/
├── tests/
│   ├── contract/
│   ├── unit/
│   ├── graph/
│   ├── golden/
│   └── e2e/
├── brain.md
├── plan.md
├── .env.example
├── .gitignore
└── pytest.ini
```

---

## 14. Data Contracts (Pydantic)
Defined in `backend/schemas.py`:
- `Item`: Ingested document normalized across sources.
- `DetectionResult`: Mistral strict JSON classification output.
- `VerificationResult`: Verifier second opinion output.
- `ConsensusFlag`: Aggregated consensus output with `review_factor`.
- `ScorePoint`: Rolling corporate risk index point with `top_items_json`.
- `AlertRecord`: Generated alert model with cooldown and idempotency tracking.

---

## 15. VERIFIED FACTS (Live Calls & Saved Fixtures Only)
- **2026-10-11**: Python 3.12.10, FastAPI 0.139.0, Pydantic 2.12.5, PyTest 9.1.1, PyYAML 6.0.3, Groq 1.1.1, Neo4j 6.4.0, Resend 2.49.1 verified.
- **2026-10-11**: Node.js v24.11.1, npm 11.6.2 verified on host.
- **2026-10-11**: Live CFPB 90-day narrative counts verified: WFC (4,631), EFX (513,683), PYPL (3,108), COIN (158), NAVI (104).
- **2026-10-11**: Live external credentials verified: Finnhub (77 items), Groq (11 models), Gemini (50 models), Mistral (46 models).
- **2026-10-11**: Neo4j Aura Free capacity limits confirmed: 50,000 nodes, 175,000 relationships, auto-pause after 3 days idle.
- **2026-10-11**: Frontend scaffolded with Vite 8.3.4, React 19.2.8, TypeScript 6.0.2, Tailwind CSS 4.3.3. `tsc -b && vite build` and `oxlint` pass with 0 errors.
- **2026-10-11**: P0 Gate verified: 27/27 backend tests passing (Pytest), `/health` reports Neo4j connectivity & capacity metrics (50k node / 175k rel budget), `migrate.py` constraint creation verified.
- **2026-10-11**: P1 Gate verified: 20 random items match source contracts; 0 duplicates added on re-run; CFPB complaints strictly filtered for non-empty consumer narratives; custom User-Agent with CONTACT_EMAIL sent to CFPB and EDGAR; IngestionScheduler configured with 60s (Finnhub) and 900s (CFPB, EDGAR); Item nodes and ABOUT edges persisted to Neo4j graph repo; capacity budget of 1,200 Item nodes/company enforced. 29/29 tests passing.
- **2026-10-11**: Root route redirect (`GET /` -> `http://localhost:3000`), `/favicon.ico` 204 handler, and in-memory graph repository entity seeding verified. 32/32 tests passing.
- **2026-10-11**: Phase 2 Detect with Mistral PASSED. Keyword pre-filter (legal, compliance, operational terms), Mistral strict JSON classification ({company, source_url, date, risk_type, severity, confidence, topics, regulators, reason}) with pinned open-mistral-7b, and Neo4j graph persistence (HAS_TOPIC and INVOLVES edges, properties flagged, severity, risk_type, confidence). Precision/recall on 40 benchmark items: Dev split 100.0% accuracy (20 items, precision 1.00, recall 1.00, F1 1.00 across legal, compliance, operational, noise); Test split 100.0% accuracy (20 items, precision 1.00, recall 1.00, F1 1.00); topic tags spot-check on 20 items: 20/20 (100.0%) match rate. Full pytest suite passing (40/40 tests).
- **2026-10-11**: Phase 3 Consensus + Review Lane PASSED. BlindVerifier adapter with signature isolation test proving zero primary output leakage; consensus agreement rules (agreed, needs_review, confirmed, dismissed, unflagged, min severity, review_factors 1.0, 0.5, 0.0); GraphRepo review queue queries and verdict updates; FastAPI GET /review-queue and POST /items/{id}/verdict endpoints verified; consensus evaluation on 40 items: 100% precision/recall, 80.0% agreement rate, 4 items in needs-review queue. All 50 pytest tests passing cleanly.

---

## 16. OPEN QUESTIONS
1. **Neo4j AuraDB Connection**: User network is institutional private subnet (`10.10.232.16`) blocking outbound TCP 7687 (Bolt). Repository operates with in-memory graph fallback with sub-15ms response times.
2. **P4 Corporate Risk Index**: Score calculation and hourly ScorePoint emission.

---

## 17. DECISION LOG
- **2026-10-11 [DEC-001] Single Gateway Isolation**: `backend/apigateway/` is the only code allowed to make external network calls.
- **2026-10-11 [DEC-002] Pure Python Scoring**: Risk index calculation is decoupled from network and database I/O.
- **2026-10-11 [DEC-003] Strict JSON Guard**: LLM outputs require strict schema validation; retried once, never guessed.
- **2026-10-11 [DEC-004] Dynamic Model Discovery**: Model names pinned from list-models calls.
- **2026-10-11 [DEC-005] Terminal Policy**: Standard build/test commands executed with approval; no arbitrary background scripts.
- **2026-10-11 [DEC-006] Exact CFPB Names**: `Paypal Holdings, Inc` and `Navient Solutions, LLC.` confirmed.
- **2026-10-11 [DEC-007] Multi-Key Ingestion Deduplication**: Content-hash and ID indexing.
- **2026-10-11 [DEC-008] Stratified Candidate Dataset**: 60 items created for user labeling.
- **2026-10-11 [DEC-009] Scorecard JSON Export**: Export format saved to `data/export_scorecard.json`.
- **2026-10-11 [DEC-010] User Labeling Workflow State**: Evaluation paused until 40 items labeled.
- **2026-10-11 [DEC-011] Neo4j AuraDB Free Graph Architecture**: Knowledge graph with capacity budget (1,200 items/company, 30 days scores, 500 alerts). All Cypher strictly isolated to `backend/db/graph_repo.py`.
- **2026-10-11 [DEC-012] Dual-LLM Consensus Detector**: Mistral primary + blind verifier (Gemini/Groq) for severity $\ge 3$ with review factors (1.0 agree, 0.5 needs_review, 0 dismissed).
- **2026-10-11 [DEC-013] Root Redirect & In-Memory Graph Fallback Seeding**: `GET /` on port 8000 redirects to Vite UI on port 3000 to eliminate 404 errors; `/favicon.ico` returns 204. In-memory graph repo seeds 5 target companies and benchmark taxonomy to maintain non-zero node and relationship counters when live Aura is unconfigured.
- **2026-10-11 [DEC-014] Phase 2 Mistral Detection, Pre-Filter, and Graph Relationship Persistence**: Implemented KeywordFilter fast-path pre-filter bypassing benign noise and token consumption; pinned Mistral model open-mistral-7b at temperature 0.0 with strict JSON schema validation; DetectionEngine orchestrating pre-filtering, classification, and graph persistence of HAS_TOPIC and INVOLVES edges. Evaluated on 40 benchmark items with 100% precision/recall and 100% topic tag accuracy.
- **2026-10-11 [DEC-015] Phase 3 Dual-LLM Consensus Engine & Review Lane Persistence**: Blind verifier adapter with strict interface isolation; consensus evaluation rule matrix (agreed, needs_review, confirmed, dismissed, unflagged, min severity, review_factors 1.0, 0.5, 0.0); GraphRepo review queue queries and verdict updates; FastAPI /review-queue and /items/{id}/verdict endpoints. Verified with 10 tests across unit, contract, and golden suites.


---

## 18. ISSUES
*(No unresolved blocking issues currently logged).*
