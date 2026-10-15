from __future__ import annotations

from pydantic import ValidationError

from app.models import AnalysisRequest, StationPoint


class InputError(ValueError):
    pass


def parse_request(payload: dict) -> AnalysisRequest:
    try:
        return AnalysisRequest.model_validate(payload)
    except ValidationError as exc:
        messages = []
        for err in exc.errors():
            loc = ".".join(str(part) for part in err.get("loc", ()))
            messages.append(f"{loc}: {err.get('msg')}" if loc else str(err.get("msg")))
        raise InputError("; ".join(messages)) from exc


def validate_route_interval(
    route: list[StationPoint],
    boarding: str,
    destination: str,
) -> tuple[StationPoint, StationPoint]:
    if not route:
        raise InputError("Train route is empty; boarding and destination cannot be checked.")
    by_code = {station.code: station for station in route}
    if boarding not in by_code:
        raise InputError(f"Boarding station {boarding} is not on this train's verified route.")
    if destination not in by_code:
        raise InputError(f"Destination station {destination} is not on this train's verified route.")
    start = by_code[boarding]
    end = by_code[destination]
    if end.index <= start.index:
        raise InputError(
            f"Destination {destination} precedes or equals boarding {boarding} on this train."
        )
    return start, end
