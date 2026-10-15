"""Hard stop-list of booking/payment operations. The live adapter must never call these."""

from __future__ import annotations

FORBIDDEN_PATH_FRAGMENTS = (
    "/bookingInitPayment",
    "/bookPassenger",
    "/avlFarebooking",
    "/confirmBooking",
    "/paymentRedirect",
    "/PaymentRedirect",
    "/pg_router",
    "/captcha",
    "/otp",
    "/makePayment",
    "/initPayment",
    "/bookingData/",
    "/altAvlEnq",
    "/allLapAvlFareEnq",
)

ALLOWED_LIVE_PATHS = (
    "/online-charts/api/trainComposition",
    "/online-charts/api/coachComposition",
    "/eticketing/protected/mapps1/trnscheduleenquiry/",
)


def is_forbidden_path(path: str) -> bool:
    lowered = path.lower()
    return any(fragment.lower() in lowered for fragment in FORBIDDEN_PATH_FRAGMENTS)


def assert_allowed_path(path: str) -> None:
    if is_forbidden_path(path):
        raise RuntimeError(f"Refusing booking/payment path: {path}")
    if not any(path.startswith(allowed) or allowed in path for allowed in ALLOWED_LIVE_PATHS):
        raise RuntimeError(f"Refusing unverified path: {path}")
