"""Database migration and constraint initialization for Neo4j.

Creates uniqueness constraints and initializes metadata for:
- Item.id
- Company.ticker
- Topic.name
- Regulator.name
- Alert.key
"""

import sys
from backend.db.graph_repo import graph_repo

COMPANIES = [
    {"ticker": "WFC", "name": "Wells Fargo & Company"},
    {"ticker": "EFX", "name": "Equifax Inc."},
    {"ticker": "PYPL", "name": "PayPal Holdings, Inc."},
    {"ticker": "COIN", "name": "Coinbase Global, Inc."},
    {"ticker": "NAVI", "name": "Navient Corporation"},
]

TOPICS = [
    "unauthorized accounts or fraud",
    "data breach or cybersecurity",
    "debt collection practices",
    "mortgage or loan servicing",
    "credit reporting errors",
    "payments or outages",
    "account access or customer service",
    "enforcement action",
    "litigation or class action",
    "AML or sanctions",
    "governance or executive",
    "financial distress",
    "other",
]

REGULATORS = [
    "CFPB",
    "SEC",
    "DOJ",
    "FTC",
    "OCC",
    "FDIC",
    "Federal Reserve",
    "FINRA",
    "State AG",
    "other",
]


def run_migrations():
    """Execute constraint creation and initial seeding."""
    print("Executing Neo4j schema migrations and constraints...")
    constraints = graph_repo.init_constraints()
    for c in constraints:
        print(f"  [Constraint] {c}")

    # Seed standard companies
    for comp in COMPANIES:
        graph_repo.upsert_company(comp["ticker"], comp["name"])
    print(f"  [Seeded] {len(COMPANIES)} companies")

    health = graph_repo.check_health()
    print(f"  [Health] Status: {health.get('status')}, Connected: {health.get('connected')}")
    print(f"  [Counts] Nodes: {health.get('node_count')}, Relationships: {health.get('relationship_count')}")
    return health


if __name__ == "__main__":
    health = run_migrations()
    if not health.get("connected") and not health.get("status") == "offline_fallback":
        sys.exit(1)
    sys.exit(0)
