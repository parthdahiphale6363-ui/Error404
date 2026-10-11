# Project Rules for Risk Radar

Read brain.md and plan.md first. Obey brain.md. Update plan.md after every phase and every change.

## Core Directives
1. **Single Source of Truth**: `brain.md` governs all rules, taxonomy, models, scoring formulas, Neo4j rules, consensus mechanisms, and decision logs.
2. **Living Execution Record**: `plan.md` tracks architectural flow, phase log, module maps, change protocols, and runbooks. Must be updated in the same commit after every phase and every change.
3. **Accuracy & Verifiability**: Never guess. Only documented facts confirmed by live calls or saved fixtures belong in verified facts.
4. **Anti-Hallucination**:
   - Call only endpoints defined in `backend/apigateway/endpoints.yaml`.
   - Never invent endpoints, parameters, field names, model names, package names, company names, or numbers.
   - No fake data in real code paths. Fixtures are strictly for tests or `MOCK_MODE=1` (with visual DEMO DATA badge). UI never hardcodes numbers.
   - Simulated items carry `is_simulated=true`, display a visible SIMULATED tag, are removable via Reset, and are NEVER counted in accuracy metrics or sent in live emails.
   - LLM output must pass strict Pydantic JSON-schema validation. Temperature 0. Cache by content hash.
   - Every explanation sentence must cite Item IDs existing in the graph AND in the retrieved evidence set. Evidence paths shown in the UI must come from real Cypher results.
   - Scoring is pure Python over plain objects: no network, no LLM, no database calls inside.
   - Tests never send real email or call paid/rate-limited APIs. `EMAIL_MODE=dry_run` in tests.
5. **Gateway Boundary**:
   - `backend/apigateway/` is the ONLY code allowed to import `requests`, `httpx`, or external provider SDKs.
   - Frontend talks only to FastAPI.
6. **Neo4j Rules**:
   - Only `backend/db/graph_repo.py` runs Cypher. All queries parameterized, never string-built.
   - Capacity budget respected (max 1,200 Item nodes per company, 30 days ScorePoint, max 500 Alert nodes).
   - `/health` reports node/rel counts and warns at 70% threshold.
7. **Phase-Gate Discipline**:
   - Complete one phase at a time.
   - Never start the next phase until the current phase's gate criteria are met and approved.
   - Never edit or delete a test to make it pass. If specifications change, record it in the DECISION LOG first.
   - If the same test fails twice, STOP, write analysis in ISSUES, and ask the user.
8. **Terminal Execution Policy**:
   - Standard test and execution commands (e.g., `python -m pytest`, `npm run build`) are executed with prompt approval.
   - Never run arbitrary background shell/powershell scripts.
