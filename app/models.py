from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class DataSourceKind(str, Enum):
    fixture = "fixture"
    live = "live"
    cached = "cached"


class VacancyClass(str, Enum):
    confirmed_eligible = "confirmed_eligible"
    occupied = "occupied"
    unknown = "unknown"
    partial = "partial"
    uncertain = "uncertain"


class Confidence(str, Enum):
    high = "high"
    medium = "medium"
    low = "low"
    none = "none"


class RankingMode(str, Enum):
    kilometres = "kilometres"
    segments = "segments"


class AnalysisRequest(BaseModel):
    train_no: str = Field(..., min_length=3, max_length=6)
    boarding_station: str = Field(..., min_length=2, max_length=6)
    destination_station: str = Field(..., min_length=2, max_length=6)
    journey_date: str
    classes: list[str] = Field(..., min_length=1)

    @field_validator("train_no")
    @classmethod
    def train_digits(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned.isdigit() or not (3 <= len(cleaned) <= 5):
            raise ValueError("Train number must be 3 to 5 digits.")
        return cleaned

    @field_validator("boarding_station", "destination_station")
    @classmethod
    def station_code(cls, value: str) -> str:
        cleaned = value.strip().upper()
        if not cleaned.isalpha() or not (2 <= len(cleaned) <= 5):
            raise ValueError("Station codes must be 2 to 5 letters.")
        return cleaned

    @field_validator("journey_date")
    @classmethod
    def iso_date(cls, value: str) -> str:
        cleaned = value.strip()
        parts = cleaned.split("-")
        if len(parts) != 3 or not all(p.isdigit() for p in parts):
            raise ValueError("Journey date must be YYYY-MM-DD.")
        year, month, day = (int(p) for p in parts)
        if month < 1 or month > 12 or day < 1 or day > 31 or year < 2000:
            raise ValueError("Journey date is out of range.")
        return f"{year:04d}-{month:02d}-{day:02d}"

    @field_validator("classes")
    @classmethod
    def class_codes(cls, value: list[str]) -> list[str]:
        cleaned: list[str] = []
        for item in value:
            code = item.strip().upper()
            if not code or len(code) > 4:
                raise ValueError(f"Invalid class code: {item!r}")
            if code not in cleaned:
                cleaned.append(code)
        if not cleaned:
            raise ValueError("Select at least one travel class.")
        return cleaned


class StationPoint(BaseModel):
    code: str
    name: str | None = None
    index: int
    distance_km: float | None = None
    serial: int | None = None


class SegmentRecord(BaseModel):
    split_no: int | None = None
    from_station: str
    to_station: str
    quota: str | None = None
    occupancy_raw: Any = None
    occupancy_bool: bool | None = None
    from_index: int | None = None
    to_index: int | None = None
    eligible: bool | None = None
    status: Literal["eligible", "occupied", "unknown"] = "unknown"
    clipped_from: str | None = None
    clipped_to: str | None = None
    reason: str | None = None


class CoachMeta(BaseModel):
    coach_name: str
    class_code: str
    position_from_engine: int | None = None
    vacant_berths_raw: Any = None


class BerthLayoutCell(BaseModel):
    berth_no: int
    berth_code: str | None = None
    cabin: str | None = None
    vacancy_class: VacancyClass
    enable: bool | None = None


class RankedBerth(BaseModel):
    rank: int
    train_no: str
    train_name: str | None = None
    journey_date: str
    boarding_station: str
    destination_station: str
    class_code: str
    coach_name: str
    coach_position: int | None = None
    berth_no: int
    berth_code: str | None = None
    cabin: str | None = None
    enable: bool | None = None
    run_from: str | None = None
    run_to: str | None = None
    distance_km: float | None = None
    consecutive_segments: int = 0
    coverage_percent: float | None = None
    covers_full_journey: bool = False
    vacancy_class: VacancyClass
    confidence: Confidence
    ranking_mode: RankingMode
    ranking_rationale: str
    distance_source: str
    warnings: list[str] = Field(default_factory=list)
    missing_data_reasons: list[str] = Field(default_factory=list)
    segments: list[SegmentRecord] = Field(default_factory=list)
    retrieved_at: str


class CoachLayout(BaseModel):
    coach_name: str
    class_code: str
    position_from_engine: int | None = None
    vacant_berths_raw: Any = None
    vacant_berths_trusted: bool = False
    berths: list[BerthLayoutCell]
    fetch_ok: bool = True
    error: str | None = None


class AnalysisResponse(BaseModel):
    ok: bool
    data_source: DataSourceKind
    freshness_label: str
    retrieved_at: str | None = None
    stale: bool = False
    ranking_mode: RankingMode
    train_no: str | None = None
    train_name: str | None = None
    journey_date: str | None = None
    boarding_station: str | None = None
    destination_station: str | None = None
    discovered_classes: list[str] = Field(default_factory=list)
    coaches: list[CoachLayout] = Field(default_factory=list)
    results: list[RankedBerth] = Field(default_factory=list)
    route: list[StationPoint] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    chart_status: dict[str, Any] | None = None
