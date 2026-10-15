from __future__ import annotations

import pytest

from app.forbidden import assert_allowed_path, is_forbidden_path
from app.logging_util import redact_mapping, redact_value


def test_secrets_are_redacted():
    redacted = redact_mapping({"cookie": "secret-session-value", "content-type": "application/json"})
    assert "secret-session-value" not in str(redacted)
    assert "redacted" in redacted["cookie"]
    assert redacted["content-type"] == "application/json"
    assert "Bearer abc" not in str(redact_value("authorization", "Bearer abc"))


def test_booking_paths_are_forbidden():
    assert is_forbidden_path("/eticketing/protected/mapps1/bookingInitPayment/abc")
    assert is_forbidden_path("/pg_router/v1/payments/x")
    with pytest.raises(RuntimeError, match="Refusing"):
        assert_allowed_path("/eticketing/protected/mapps1/bookingInitPayment/abc")
    assert_allowed_path("/online-charts/api/trainComposition")
    assert_allowed_path("/online-charts/api/coachComposition")
    assert_allowed_path("/eticketing/protected/mapps1/trnscheduleenquiry/18609")
