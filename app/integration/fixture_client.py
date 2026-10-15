from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.integration.base import FetchResult

ROOT = Path(__file__).resolve().parents[2]
FIXTURE_DIR = ROOT / "fixtures"
SYNTHETIC_DIR = ROOT / "fixtures" / "synthetic"


class FixtureNotFound(FileNotFoundError):
    pass


def _load(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FixtureNotFound(str(path))
    return json.loads(path.read_text(encoding="utf-8"))


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class FixtureChartsClient:
    source_kind = "fixture"

    def __init__(self, fixture_dir: Path | None = None) -> None:
        self.fixture_dir = fixture_dir or FIXTURE_DIR

    def train_composition(self, train_no: str, journey_date: str, boarding_station: str) -> FetchResult:
        candidates = [self.fixture_dir / f"train_composition_{train_no}.json"]
        if self.fixture_dir == SYNTHETIC_DIR:
            candidates.append(SYNTHETIC_DIR / "train_composition.json")
        for path in candidates:
            if path.exists():
                return FetchResult(payload=_load(path), retrieved_at=_now(), source="fixture")
        raise FixtureNotFound(f"No train composition fixture for {train_no}")

    def coach_composition(
        self,
        train_no: str,
        boarding_station: str,
        remote_station: str,
        train_source_station: str,
        journey_date: str,
        coach: str,
        cls: str,
    ) -> FetchResult:
        candidates = [self.fixture_dir / f"coach_{train_no}_{coach}_{cls}.json"]
        if self.fixture_dir == SYNTHETIC_DIR:
            candidates.append(self.fixture_dir / f"coach_{coach}_{cls}.json")
            candidates.append(SYNTHETIC_DIR / "coach_composition.json")
        elif train_no == "18609":
            # Captured 18609 samples used the unprefixed names.
            candidates.append(self.fixture_dir / f"coach_{coach}_{cls}.json")
        for path in candidates:
            if path.exists():
                return FetchResult(payload=_load(path), retrieved_at=_now(), source="fixture")
        raise FixtureNotFound(f"No coach fixture for {coach}/{cls}")

    def train_schedule(self, train_no: str) -> FetchResult:
        candidates = [self.fixture_dir / f"schedule_{train_no}.json"]
        if self.fixture_dir == SYNTHETIC_DIR:
            candidates.append(SYNTHETIC_DIR / "schedule.json")
        for path in candidates:
            if path.exists():
                return FetchResult(payload=_load(path), retrieved_at=_now(), source="fixture")
        raise FixtureNotFound(f"No schedule fixture for {train_no}")
