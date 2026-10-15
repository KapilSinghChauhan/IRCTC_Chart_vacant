from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class FetchResult:
    payload: dict[str, Any]
    retrieved_at: str
    source: str
    warnings: list[str] = field(default_factory=list)


class ChartsClient(Protocol):
    source_kind: str

    def train_composition(self, train_no: str, journey_date: str, boarding_station: str) -> FetchResult: ...

    def coach_composition(
        self,
        train_no: str,
        boarding_station: str,
        remote_station: str,
        train_source_station: str,
        journey_date: str,
        coach: str,
        cls: str,
    ) -> FetchResult: ...

    def train_schedule(self, train_no: str) -> FetchResult: ...
