# 🛰️ Corporate Risk Radar (Fintech PS 01)

[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.139-green.svg)](https://fastapi.tiangolo.com/)
[![React 19](https://img.shields.io/badge/React-19.2-cyan.svg)](https://react.dev/)
[![Tailwind CSS v4](https://img.shields.io/badge/Tailwind-4.3-38bdf8.svg)](https://tailwindcss.com/)
[![Neo4j AuraDB](https://img.shields.io/badge/Neo4j-AuraDB%20Free-008cc1.svg)](https://neo4j.com/)
[![Tests Passing](https://img.shields.io/badge/tests-29%2F29%20passed-brightgreen.svg)]()

> Continuous real-time corporate risk intelligence engine for legal, compliance, and operational risks across financial institutions.

---

## 🌟 Highlights & Unique Differentiators

1. **Dual-LLM Consensus Detector**:
   - Primary classifier (**Mistral**) identifies risk events with strict JSON-schema enforcement.
   - Blind verifier (**Gemini / Groq**) provides independent second opinions on high-severity items ($\ge 3$).
   - Agreed items receive full index weight ($1.0$); disagreements route to an analyst **"Needs Review"** lane at half weight ($0.5$).
2. **Neo4j Evidence Graph**:
   - Grounded knowledge graph tracking recurrence, contagion across financial institutions, and multi-hop Cypher evidence paths.
   - Eliminates hallucination: all plain-language explanations cite verified graph item IDs.
3. **Pure-Function Risk Index**:
   - Rolling corporate risk index bounded $[0, 100]$:
     $$\text{Index} = 100 \times \left(1 - \exp\left(-\frac{S}{10}\right)\right)$$
   - Exponential decay with a 7-day half-life: $0.5^{\frac{\text{age\_days}}{7}}$.
   - Dynamically accounts for complaint spikes via historical baseline z-score bonus: $\text{clamp}(z - 1, 0, 5)$.
4. **Action Layer & Alerts**:
   - Resend email alerts with mobile-friendly HTML briefings, rule cooldowns (6h), and daily quota caps.
   - Safe-by-default dry-run preview mode saving outbox HTML to `data/outbox/`.
5. **Modern Live UI Scoreboard**:
   - Built with Vite, React 19, TypeScript, and Tailwind CSS v4.
   - Real-time SSE updates with 10s polling fallback.
   - Type-safe contracts generated directly from FastAPI `/openapi.json`.

---

## 🏢 Target Companies

| Ticker | Company Name | CFPB 90-Day Volume | Primary Risk Profile |
|---|---|---|---|
| **WFC** | Wells Fargo & Company | 4,631+ narrative complaints | Compliance & unauthorized accounts |
| **EFX** | Equifax Inc. | 513,683+ complaints | Credit reporting dispute backlogs |
| **PYPL** | PayPal Holdings, Inc. | 3,108+ complaints | Payment processing & account restrictions |
| **COIN** | Coinbase Global, Inc. | 158+ complaints | Crypto regulatory litigation |
| **NAVI** | Navient Corporation | 104+ complaints | Student loan servicing consent orders |

---

## 🏗️ Architecture & Data Flow

```text
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

## 🚀 Quickstart & Setup

### 1. Prerequisites
- Python 3.12+
- Node.js v20+ & npm

### 2. Environment Configuration
Copy `.env.example` to `.env` and fill in API credentials:
```bash
cp .env.example .env
```
*(Never commit `.env` to version control; it is securely ignored by `.gitignore`)*

### 3. Single-Command Runner (Backend + Frontend Together)
Run both the FastAPI backend and React Vite frontend concurrently with one command:
```bash
python run.py
```
*(Or double-click `run.bat` on Windows)*

- **Dashboard UI**: [http://localhost:3000](http://localhost:3000)
- **FastAPI API**: [http://localhost:8000](http://localhost:8000)
- **API Docs (Swagger)**: [http://localhost:8000/docs](http://localhost:8000/docs)

### 4. Running Components Individually (Optional)
```bash
# Install Python dependencies
pip install -r requirements.txt   # or pip install fastapi pydantic pytest neo4j httpx pyyaml resend groq google-genai

# Run migrations & schema constraints
python -m backend.db.migrate

# Start FastAPI backend server
uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
```

### 4. Frontend Setup
```bash
cd frontend
npm install
npm run dev
```
Dashboard available at `http://localhost:3000` (or `http://localhost:5173`).

### 5. Running Tests
```bash
# Run all backend unit, contract, graph, and e2e tests
python -m pytest

# Run frontend typecheck, linter, and production build
cd frontend && npm run build && npm run lint
```

---

## 🔒 Security & Anti-Hallucination Policy
- **Zero Hallucination**: LLM calls strictly output validated Pydantic JSON schemas. Invalid outputs are retried once, never repaired by guessing.
- **Evidence Citation**: Explanations cite only valid, retrieved graph node IDs.
- **Pure Python Scoring**: Mathematical index calculation is decoupled from network and database I/O.
- **External Network Isolation**: Only `backend/apigateway/` communicates with third-party APIs.
