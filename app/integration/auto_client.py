from __future__ import annotations

from collections.abc import Callable
from typing import Any

from app.integration.base import FetchResult
from app.integration.cdp_client import CdpChartsClient
from app.integration.fixture_client import FixtureChartsClient, FixtureNotFound
from app.integration.live_client import LiveAccessError


class AutoChartsClient:
    """Use a captured fixture when present; otherwise try the live charts API."""

    source_kind = "auto"

    def __init__(
        self,
        fixture: FixtureChartsClient | None = None,
        live_factory: Callable[[], Any] | None = None,
    ) -> None:
        self.fixture = fixture or FixtureChartsClient()
        self._live_factory = live_factory or CdpChartsClient
        self._live: Any | None = None
        self._live_failed: Exception | None = None
        self._failed_methods: set[str] = set()
        self.last_source = "fixture"

    def _get_live(self) -> Any:
        if self._live is None:
            self._live = self._live_factory()
        return self._live

    def _with_fallback(self, method: str, *args, **kwargs) -> FetchResult:
        try:
            result = getattr(self.fixture, method)(*args, **kwargs)
            self.last_source = "fixture"
            return result
        except FixtureNotFound as missing:
            if method in self._failed_methods:
                raise LiveAccessError(
                    f"{missing}. Live chart lookup skipped after earlier failure: {self._live_failed}"
                ) from self._live_failed
            try:
                result = getattr(self._get_live(), method)(*args, **kwargs)
            except LiveAccessError as live_error:
                self._live_failed = live_error
                self._failed_methods.add(method)
                raise LiveAccessError(
                    f"{missing}. Live chart lookup also failed: {live_error}"
                ) from live_error
            self.last_source = "live"
            return result

    def train_composition(self, train_no: str, journey_date: str, boarding_station: str) -> FetchResult:
        return self._with_fallback("train_composition", train_no, journey_date, boarding_station)

    def coach_composition(self, **kwargs) -> FetchResult:
        return self._with_fallback("coach_composition", **kwargs)

    def train_schedule(self, train_no: str) -> FetchResult:
        return self._with_fallback("train_schedule", train_no)
