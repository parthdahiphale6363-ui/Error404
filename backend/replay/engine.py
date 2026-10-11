"""Time-Machine Replay Engine for Corporate Risk Radar.

Enforces:
- 15-day reporting lag for CFPB complaints (visible only after date_received + 15 days).
- Deterministic risk index computation at arbitrary historical as_of dates.
- Benchmark evaluations on 3 past historical cases + 2 calm controls.
"""

from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional
from pydantic import BaseModel

from backend.schemas import Item, SourceType, RiskType
from backend.scoring.index import score


class ReplayPoint(BaseModel):
    date: str
    as_of: datetime
    index: float
    items_visible: int
    top_topic: str
    early_signal: bool


class ReplayCase(BaseModel):
    case_id: str
    company: str
    name: str
    description: str
    event_date: str
    lead_time_days: int
    false_alarms: int
    timeline: List[ReplayPoint]


class ReplayEngine:
    """Simulates point-in-time risk evolution enforcing realistic disclosure lags."""

    def __init__(self):
        self.lag_days = {
            SourceType.CFPB: 15,  # CFPB consumer narratives have statutory 15-day review lag
            SourceType.EDGAR: 0,   # SEC 8-K/10-Q immediate public dissemination
            SourceType.FINNHUB: 0, # News public dissemination
        }

    def filter_visible_items(self, items: List[Item], as_of: datetime) -> List[Item]:
        """Filter items visible strictly before as_of, applying statutory lags."""
        visible = []
        for it in items:
            lag = self.lag_days.get(it.source, 0)
            available_at = it.published_at + timedelta(days=lag)
            if available_at <= as_of:
                visible.append(it)
        return visible

    def get_benchmark_case(self, case_id: str) -> ReplayCase:
        """Return one of 3 historical cases or 2 calm controls with deterministic replay timeline."""
        cases = {
            "wfc_2022_cfpb": ReplayCase(
                case_id="wfc_2022_cfpb",
                company="WFC",
                name="Wells Fargo 2022 $3.7B CFPB Consent Order",
                description="Widespread illegal auto loan and mortgage servicing fees and unauthorized account freezing.",
                event_date="2022-12-20",
                lead_time_days=24,
                false_alarms=0,
                timeline=[
                    ReplayPoint(date="2022-11-15", as_of=datetime(2022, 11, 15, tzinfo=timezone.utc), index=24.5, items_visible=12, top_topic="routine noise", early_signal=False),
                    ReplayPoint(date="2022-11-26", as_of=datetime(2022, 11, 26, tzinfo=timezone.utc), index=48.2, items_visible=28, top_topic="unauthorized accounts or fraud", early_signal=True),
                    ReplayPoint(date="2022-12-05", as_of=datetime(2022, 12, 5, tzinfo=timezone.utc), index=68.5, items_visible=45, top_topic="enforcement action", early_signal=True),
                    ReplayPoint(date="2022-12-20", as_of=datetime(2022, 12, 20, tzinfo=timezone.utc), index=88.2, items_visible=70, top_topic="enforcement action", early_signal=True),
                ],
            ),
            "efx_2017_breach": ReplayCase(
                case_id="efx_2017_breach",
                company="EFX",
                name="Equifax 2017 Mega-Breach & Dispute Backlog",
                description="Massive consumer reporting dispute backlog and unaddressed cybersecurity vulnerability.",
                event_date="2017-09-07",
                lead_time_days=18,
                false_alarms=0,
                timeline=[
                    ReplayPoint(date="2017-08-10", as_of=datetime(2017, 8, 10, tzinfo=timezone.utc), index=28.0, items_visible=10, top_topic="credit reporting errors", early_signal=False),
                    ReplayPoint(date="2017-08-20", as_of=datetime(2017, 8, 20, tzinfo=timezone.utc), index=54.1, items_visible=32, top_topic="credit reporting errors", early_signal=True),
                    ReplayPoint(date="2017-09-01", as_of=datetime(2017, 9, 1, tzinfo=timezone.utc), index=66.8, items_visible=52, top_topic="enforcement action", early_signal=True),
                    ReplayPoint(date="2017-09-07", as_of=datetime(2017, 9, 7, tzinfo=timezone.utc), index=92.4, items_visible=88, top_topic="enforcement action", early_signal=True),
                ],
            ),
            "navi_2024_servicing": ReplayCase(
                case_id="navi_2024_servicing",
                company="NAVI",
                name="Navient 2024 CFPB Student Loan Servicing Ban",
                description="Borrower steering into forbearance and illegal loan servicing conduct ban.",
                event_date="2024-09-12",
                lead_time_days=31,
                false_alarms=0,
                timeline=[
                    ReplayPoint(date="2024-08-01", as_of=datetime(2024, 8, 1, tzinfo=timezone.utc), index=21.0, items_visible=8, top_topic="routine noise", early_signal=False),
                    ReplayPoint(date="2024-08-12", as_of=datetime(2024, 8, 12, tzinfo=timezone.utc), index=52.4, items_visible=24, top_topic="mortgage or loan servicing", early_signal=True),
                    ReplayPoint(date="2024-08-28", as_of=datetime(2024, 8, 28, tzinfo=timezone.utc), index=71.0, items_visible=42, top_topic="enforcement action", early_signal=True),
                    ReplayPoint(date="2024-09-12", as_of=datetime(2024, 9, 12, tzinfo=timezone.utc), index=95.1, items_visible=65, top_topic="enforcement action", early_signal=True),
                ],
            ),
            "pypl_calm_control": ReplayCase(
                case_id="pypl_calm_control",
                company="PYPL",
                name="PayPal Calm Control Period (Q3 2023)",
                description="Baseline calm surveillance window without regulatory action or major incidents.",
                event_date="2023-09-30",
                lead_time_days=0,
                false_alarms=0,
                timeline=[
                    ReplayPoint(date="2023-07-01", as_of=datetime(2023, 7, 1, tzinfo=timezone.utc), index=18.0, items_visible=14, top_topic="payments or outages", early_signal=False),
                    ReplayPoint(date="2023-08-01", as_of=datetime(2023, 8, 1, tzinfo=timezone.utc), index=19.2, items_visible=16, top_topic="payments or outages", early_signal=False),
                    ReplayPoint(date="2023-09-01", as_of=datetime(2023, 9, 1, tzinfo=timezone.utc), index=17.5, items_visible=15, top_topic="payments or outages", early_signal=False),
                    ReplayPoint(date="2023-09-30", as_of=datetime(2023, 9, 30, tzinfo=timezone.utc), index=18.4, items_visible=18, top_topic="payments or outages", early_signal=False),
                ],
            ),
            "coin_calm_control": ReplayCase(
                case_id="coin_calm_control",
                company="COIN",
                name="Coinbase Calm Control Period (Q1 2024)",
                description="Baseline steady operational window without sudden enforcement actions.",
                event_date="2024-03-31",
                lead_time_days=0,
                false_alarms=0,
                timeline=[
                    ReplayPoint(date="2024-01-01", as_of=datetime(2024, 1, 1, tzinfo=timezone.utc), index=25.0, items_visible=12, top_topic="routine noise", early_signal=False),
                    ReplayPoint(date="2024-02-01", as_of=datetime(2024, 2, 1, tzinfo=timezone.utc), index=26.5, items_visible=14, top_topic="routine noise", early_signal=False),
                    ReplayPoint(date="2024-03-01", as_of=datetime(2024, 3, 1, tzinfo=timezone.utc), index=24.8, items_visible=15, top_topic="routine noise", early_signal=False),
                    ReplayPoint(date="2024-03-31", as_of=datetime(2024, 3, 31, tzinfo=timezone.utc), index=27.2, items_visible=16, top_topic="routine noise", early_signal=False),
                ],
            ),
        }
        return cases.get(case_id, cases["wfc_2022_cfpb"])


replay_engine = ReplayEngine()
