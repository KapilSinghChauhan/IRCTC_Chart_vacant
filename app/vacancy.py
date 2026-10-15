"""Vacancy interpretation isolated from ranking and UI.

Evidence from authorized captures (2026-10-14, train 18609):
- occupancy is a boolean on each berth nested bsd[] record.
- occupancy True co-occurs with later occupied splits; occupancy False
  co-occurs with earlier vacant splits. Eligible means occupancy is False.
- enable was True on every captured berth; it is not used as vacancy.
- vacantBerths was 0 on every captured coach while some occupancy False
  segments existed, so it is not individual-berth status.
"""

from __future__ import annotations

from typing import Any


class OccupancyInterpretation:
    source = "coachComposition.bdd[].bsd[].occupancy"
    true_means = "occupied"
    false_means = "eligible_vacant"
    missing_means = "unknown"


def occupancy_status(raw: Any) -> tuple[str, bool | None, str]:
    """Return (status, occupancy_bool, reason).

    status is eligible | occupied | unknown.
    Missing or non-boolean values are unknown. Missing is never eligible.
    """
    if raw is None:
        return "unknown", None, "occupancy field missing"
    if isinstance(raw, bool):
        if raw is False:
            return "eligible", False, "occupancy is false (vacant)"
        return "occupied", True, "occupancy is true (occupied)"
    if isinstance(raw, str):
        lowered = raw.strip().lower()
        if lowered in {"false", "0", "n", "no"}:
            return "eligible", False, f"occupancy string {raw!r} treated as vacant"
        if lowered in {"true", "1", "y", "yes"}:
            return "occupied", True, f"occupancy string {raw!r} treated as occupied"
    return "unknown", None, f"occupancy value {raw!r} is not a verified boolean"


def is_eligible_segment(raw: Any) -> bool:
    status, _, _ = occupancy_status(raw)
    return status == "eligible"
