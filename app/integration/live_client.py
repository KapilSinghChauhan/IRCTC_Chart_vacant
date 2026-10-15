from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from app.forbidden import assert_allowed_path
from app.integration.base import FetchResult
from app.logging_util import configure_logging, redact_mapping

logger = configure_logging()

DEFAULT_ORIGIN = "https://www.irctc.co.in"
CHARTS_TRAIN = "/online-charts/api/trainComposition"
CHARTS_COACH = "/online-charts/api/coachComposition"
SCHEDULE = "/eticketing/protected/mapps1/trnscheduleenquiry/{train_no}"


class LiveAccessError(RuntimeError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_cookie_header() -> str | None:
    raw = os.environ.get("IRCTC_COOKIES")
    cookie_file = os.environ.get("IRCTC_COOKIE_FILE")
    if cookie_file:
        path = Path(cookie_file).expanduser()
        if path.exists():
            raw = path.read_text(encoding="utf-8", errors="replace").strip()
    if not raw:
        return None
    return raw.strip()


class LiveChartsClient:
    source_kind = "live"

    def __init__(self, timeout: float | None = None) -> None:
        self.origin = os.environ.get("IRCTC_CHARTS_ORIGIN", DEFAULT_ORIGIN).rstrip("/")
        self.timeout = timeout or float(os.environ.get("IRCTC_TIMEOUT_SECONDS", "8"))
        cookie = _load_cookie_header()
        self._headers = {
            "user-agent": (
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
            ),
            "accept": "application/json, text/plain, */*",
            "content-type": "application/json",
            "origin": self.origin,
            "referer": f"{self.origin}/online-charts/",
        }
        if cookie:
            self._headers["cookie"] = cookie

    def _post_json(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        assert_allowed_path(path)
        url = f"{self.origin}{path}"
        logger.info("live POST %s body=%s", path, body)
        try:
            with httpx.Client(timeout=self.timeout, follow_redirects=False) as client:
                response = client.post(url, json=body, headers=self._headers)
        except httpx.TimeoutException as exc:
            raise LiveAccessError(f"Timeout calling {path}") from exc
        logger.info(
            "live POST %s status=%s headers=%s",
            path,
            response.status_code,
            redact_mapping(dict(response.headers)),
        )
        if response.status_code in {401, 403}:
            raise LiveAccessError(f"Access denied for {path} (HTTP {response.status_code}).")
        if response.status_code >= 400:
            raise LiveAccessError(f"Upstream error for {path}: HTTP {response.status_code}.")
        try:
            payload = response.json()
        except ValueError as exc:
            raise LiveAccessError(f"Malformed JSON from {path}.") from exc
        if not isinstance(payload, dict):
            raise LiveAccessError(f"Unexpected JSON type from {path}.")
        return payload

    def _get_json(self, path: str) -> dict[str, Any]:
        assert_allowed_path(path)
        url = f"{self.origin}{path}"
        logger.info("live GET %s", path)
        try:
            with httpx.Client(timeout=self.timeout, follow_redirects=False) as client:
                response = client.get(url, headers=self._headers)
        except httpx.TimeoutException as exc:
            raise LiveAccessError(f"Timeout calling {path}") from exc
        logger.info("live GET %s status=%s", path, response.status_code)
        if response.status_code in {401, 403}:
            raise LiveAccessError(f"Access denied for {path} (HTTP {response.status_code}).")
        if response.status_code >= 400:
            raise LiveAccessError(f"Upstream error for {path}: HTTP {response.status_code}.")
        try:
            payload = response.json()
        except ValueError as exc:
            raise LiveAccessError(f"Malformed JSON from {path}.") from exc
        if not isinstance(payload, dict):
            raise LiveAccessError(f"Unexpected JSON type from {path}.")
        return payload

    def train_composition(self, train_no: str, journey_date: str, boarding_station: str) -> FetchResult:
        payload = self._post_json(
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
        payload = self._post_json(
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
        payload = self._get_json(SCHEDULE.format(train_no=train_no))
        return FetchResult(payload=payload, retrieved_at=_now(), source="live")
