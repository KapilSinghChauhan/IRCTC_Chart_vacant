"""Live charts adapter that reads IRCTC from inside a hidden Chrome tab over CDP."""

from __future__ import annotations

import os
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

from app.forbidden import assert_allowed_path
from app.integration.base import FetchResult
from app.integration.cdp_session import default_cdp, fetch_json
from app.integration.live_client import CHARTS_COACH, CHARTS_TRAIN, SCHEDULE, LiveAccessError

PageFetch = Callable[[str, str, dict[str, Any] | None], dict[str, Any]]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class CdpChartsClient:
    source_kind = "live"

    def __init__(
        self,
        page_fetch: PageFetch | None = None,
        cdp: str | None = None,
        timeout: float | None = None,
    ) -> None:
        self._page_fetch = page_fetch
        self.cdp = (cdp or default_cdp()).rstrip("/")
        self.timeout = timeout or float(os.environ.get("IRCTC_TIMEOUT_SECONDS", "20"))
        self.origin = os.environ.get("IRCTC_CHARTS_ORIGIN", "https://www.irctc.co.in").rstrip("/")

    def _page_call(self, method: str, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        assert_allowed_path(path)
        if self._page_fetch is not None:
            payload = self._page_fetch(method, path, body)
        else:
            payload = fetch_json(
                method,
                path,
                body,
                cdp=self.cdp,
                timeout=self.timeout,
                origin=self.origin,
            )
        if not isinstance(payload, dict):
            raise LiveAccessError(f"Malformed JSON from {path} via Chrome CDP.")
        return payload

    def train_composition(self, train_no: str, journey_date: str, boarding_station: str) -> FetchResult:
        payload = self._page_call(
            "POST",
            CHARTS_TRAIN,
            {"trainNo": train_no, "jDate": journey_date, "boardingStation": boarding_station},
        )
        return FetchResult(payload=payload, retrieved_at=_now(), source="live")

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
        payload = self._page_call(
            "POST",
            CHARTS_COACH,
            {
                "trainNo": train_no,
                "boardingStation": boarding_station,
                "remoteStation": remote_station,
                "trainSourceStation": train_source_station,
                "jDate": journey_date,
                "coach": coach,
                "cls": cls,
            },
        )
        return FetchResult(payload=payload, retrieved_at=_now(), source="live")

    def train_schedule(self, train_no: str) -> FetchResult:
        payload = self._page_call("GET", SCHEDULE.format(train_no=train_no), None)
        return FetchResult(payload=payload, retrieved_at=_now(), source="live")
