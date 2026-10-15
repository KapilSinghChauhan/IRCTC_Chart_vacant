from __future__ import annotations

import pytest

from app.route import normalize_schedule
from app.validation import InputError, parse_request, validate_route_interval


def test_valid_input_parses():
    req = parse_request(
        {
            "train_no": "18609",
            "boarding_station": "rnc",
            "destination_station": "ltt",
            "journey_date": "2026-10-14",
            "classes": ["sl", "3A"],
        }
    )
    assert req.boarding_station == "RNC"
    assert req.classes == ["SL", "3A"]


@pytest.mark.parametrize(
    "payload",
    [
        {"train_no": "AB", "boarding_station": "RNC", "destination_station": "LTT", "journey_date": "2026-10-14", "classes": ["SL"]},
        {"train_no": "18609", "boarding_station": "R", "destination_station": "LTT", "journey_date": "2026-10-14", "classes": ["SL"]},
        {"train_no": "18609", "boarding_station": "RNC", "destination_station": "LTT", "journey_date": "14-10-2026", "classes": ["SL"]},
        {"train_no": "18609", "boarding_station": "RNC", "destination_station": "LTT", "journey_date": "2026-10-14", "classes": []},
    ],
)
def test_invalid_input_rejected(payload):
    with pytest.raises(InputError):
        parse_request(payload)


def test_boarding_station_not_found():
    route = normalize_schedule(
        {"stationList": [{"stationCode": "RNC", "distance": "0"}, {"stationCode": "LTT", "distance": "10"}]}
    )
    with pytest.raises(InputError, match="Boarding station XYZ"):
        validate_route_interval(route, "XYZ", "LTT")


def test_destination_preceding_boarding():
    route = normalize_schedule(
        {
            "stationList": [
                {"stationCode": "RNC", "distance": "0"},
                {"stationCode": "GAYA", "distance": "200"},
                {"stationCode": "LTT", "distance": "2011"},
            ]
        }
    )
    with pytest.raises(InputError, match="precedes"):
        validate_route_interval(route, "LTT", "RNC")
