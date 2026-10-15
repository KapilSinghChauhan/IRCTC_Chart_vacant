from __future__ import annotations

from app.vacancy import is_eligible_segment, occupancy_status


def test_confirmed_eligible_is_occupancy_false():
    status, flag, _ = occupancy_status(False)
    assert status == "eligible"
    assert flag is False
    assert is_eligible_segment(False) is True


def test_confirmed_occupied_is_occupancy_true():
    status, flag, _ = occupancy_status(True)
    assert status == "occupied"
    assert is_eligible_segment(True) is False


def test_missing_occupancy_is_unknown_not_eligible():
    status, flag, reason = occupancy_status(None)
    assert status == "unknown"
    assert flag is None
    assert is_eligible_segment(None) is False
    assert "missing" in reason


def test_contradictory_occupancy_is_unknown():
    status, _, _ = occupancy_status("maybe")
    assert status == "unknown"
    assert is_eligible_segment("maybe") is False
