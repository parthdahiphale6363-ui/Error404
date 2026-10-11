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

## 🚀 Quickstart & Running Instructions

### Method 1: Run with Docker Compose (Recommended for Production & Containers)
Launch both the **FastAPI Backend** and the **React 19 Frontend (Nginx)** in isolated containers with a single command:

```bash
# Build and run all containers in attached mode
docker compose up --build

# Or run in detached (background) mode
docker compose up -d --build

# View running container logs
docker compose logs -f

# Stop all containers
docker compose down
```

Once running:
- 🌐 **Dashboard UI**: [http://localhost:3000](http://localhost:3000)
- 🔌 **FastAPI Backend API**: [http://localhost:8000](http://localhost:8000)
- 📚 **Interactive Swagger API Docs**: [http://localhost:8000/docs](http://localhost:8000/docs)
- 🩺 **Health Check**: [http://localhost:8000/health](http://localhost:8000/health)

---

### Method 2: Single-Command Local Runner (Backend + Frontend Together)
If running directly on your host machine without Docker:

```bash
# Prerequisites: Python 3.12+ and Node.js v20+

# 1. Configure environment variables (optional for local mock mode)
cp .env.example .env

# 2. Run both Backend and Frontend concurrently with auto-browser launch:
python run.py

# (On Windows, you can alternatively double-click or run):
.\run.bat
```

The runner script automatically launches `http://localhost:3000` in your default browser once the backend health probe passes, and safely terminates both processes on `Ctrl+C`.

---

### Method 3: Running Components Individually

#### A. Backend (FastAPI + Uvicorn)
```bash
# Install Python dependencies
pip install -r requirements.txt

# Run database schema migrations & constraints
python -m backend.db.migrate

# Start FastAPI server on port 8000 with auto-reload
uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
```

#### B. Frontend (React 19 + Vite)
```bash
cd frontend

# Install Node dependencies
npm install

# Start Vite dev server on port 3000
npm run dev
```

---

### 🧪 Running Tests & Quality Verification

```bash
# Run all backend unit, contract, graph, and e2e tests (29/29 tests)
python -m pytest

# Run frontend type-check, linter, and production build
cd frontend
npm run build
npm run lint
```

---

## 🔒 Security & Anti-Hallucination Policy
- **Zero Hallucination**: LLM calls strictly output validated Pydantic JSON schemas. Invalid outputs are retried once, never repaired by guessing.
- **Evidence Citation**: Explanations cite only valid, retrieved graph node IDs.
- **Pure Python Scoring**: Mathematical index calculation is decoupled from network and database I/O.
- **External Network Isolation**: Only `backend/apigateway/` communicates with third-party APIs.
