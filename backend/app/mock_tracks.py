"""Deterministic, explicitly simulated TrackSnapshot fixtures for map development."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from enum import Enum
from math import cos, radians, sin
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


UTC = timezone.utc
ANCHOR = datetime(2025, 10, 1, 12, 0, tzinfo=UTC)


class SourceType(str, Enum):
    YANG_LEI = "YANG_LEI"
    REAL_AIS = "REAL_AIS"
    SYNTHETIC_AIS = "SYNTHETIC_AIS"


class DataStatus(str, Enum):
    VALID = "VALID"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    STALE = "STALE"
    INVALID_DATA = "INVALID_DATA"


class HistoryPoint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nominal_timestamp: datetime
    source_timestamp: datetime | None
    original_source_timestamp: datetime | None
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    sog_kn: float = Field(ge=0, le=50)
    cog_deg: float = Field(ge=0, lt=360)
    source_age_seconds: float | None = Field(default=None, ge=0)

    @field_validator("nominal_timestamp", "source_timestamp", "original_source_timestamp")
    @classmethod
    def require_utc(cls, value: datetime | None) -> datetime | None:
        if value is not None and (value.tzinfo is None or value.utcoffset() != timedelta(0)):
            raise ValueError("timestamps must be timezone-aware UTC")
        return value


class TrackSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0.0"] = "1.0.0"
    vessel_id: str = Field(min_length=1)
    mmsi: str | None = Field(default=None, pattern=r"^[0-9]{9}$")
    source_type: SourceType
    is_simulated: bool
    anchor_timestamp: datetime
    current_state: HistoryPoint | None
    history: list[HistoryPoint] = Field(max_length=10)
    data_status: DataStatus

    @field_validator("anchor_timestamp")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() != timedelta(0):
            raise ValueError("anchor_timestamp must be timezone-aware UTC")
        return value

    @model_validator(mode="after")
    def enforce_snapshot_semantics(self) -> "TrackSnapshot":
        if self.source_type == SourceType.REAL_AIS and (self.is_simulated or self.mmsi is None):
            raise ValueError("REAL_AIS requires a real MMSI and is_simulated=false")
        if self.source_type != SourceType.REAL_AIS and not self.is_simulated:
            raise ValueError("simulated source types require is_simulated=true")
        nominal_times = [point.nominal_timestamp for point in self.history]
        if nominal_times != sorted(nominal_times) or len(set(nominal_times)) != len(nominal_times):
            raise ValueError("history nominal timestamps must be strictly increasing")
        for point in self.history:
            if point.nominal_timestamp > self.anchor_timestamp:
                raise ValueError("history cannot include a nominal timestamp after the anchor")
            if point.source_timestamp is not None and point.source_timestamp > point.nominal_timestamp:
                raise ValueError("a history source timestamp cannot be later than its nominal timestamp")
        if self.history and self.current_state != self.history[-1]:
            raise ValueError("current_state must be the latest history point")
        if self.data_status == DataStatus.VALID:
            if len(self.history) != 10 or self.current_state is None:
                raise ValueError("VALID snapshots require ten history points and current_state")
            expected = [self.anchor_timestamp + timedelta(minutes=offset) for offset in range(-9, 1)]
            if [point.nominal_timestamp for point in self.history] != expected:
                raise ValueError("history nominal timestamps must cover anchor -9 through anchor")
            if self.source_type in (SourceType.REAL_AIS, SourceType.SYNTHETIC_AIS):
                for point in self.history:
                    if point.source_timestamp is None or point.source_age_seconds is None:
                        raise ValueError("AIS histories require a source timestamp and age")
                    age = (point.nominal_timestamp - point.source_timestamp).total_seconds()
                    if age < 0 or age > 60 or abs(age - point.source_age_seconds) > 1e-6:
                        raise ValueError("valid AIS source age must be between 0 and 60 seconds")
        if self.data_status == DataStatus.STALE and not any(
            point.source_age_seconds is not None and point.source_age_seconds > 60
            for point in self.history
        ):
            raise ValueError("STALE snapshots require a history point older than 60 seconds")
        return self


class TrackListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[TrackSnapshot]
    total: int = Field(ge=0)


class ErrorResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0.0"] = "1.0.0"
    error_code: str = Field(min_length=1)
    message: str = Field(min_length=1)
    request_id: str | None = None
    details: dict[str, object] | None = None


def _history(
    latitude: float,
    longitude: float,
    sog_kn: float,
    cog_deg: float,
    *,
    stale_seconds: int = 0,
) -> list[HistoryPoint]:
    """Create ten one-minute samples from a constant-speed local motion model."""
    points: list[HistoryPoint] = []
    for offset in range(-9, 1):
        nominal = ANCHOR + timedelta(minutes=offset)
        minutes_from_anchor = offset
        distance_nm = sog_kn * minutes_from_anchor / 60
        north_nm = distance_nm * cos(radians(cog_deg))
        east_nm = distance_nm * sin(radians(cog_deg))
        lat = latitude + north_nm / 60
        lon = longitude + east_nm / (60 * cos(radians(latitude)))
        source_time = nominal
        age = 0.0
        if stale_seconds and offset == 0:
            source_time -= timedelta(seconds=stale_seconds)
            age = float(stale_seconds)
        points.append(
            HistoryPoint(
                nominal_timestamp=nominal,
                source_timestamp=source_time,
                original_source_timestamp=None,
                latitude=lat,
                longitude=lon,
                sog_kn=sog_kn,
                cog_deg=cog_deg,
                source_age_seconds=age,
            )
        )
    return points


def _make_track(
    vessel_id: str,
    latitude: float,
    longitude: float,
    sog_kn: float,
    cog_deg: float,
    *,
    stale_seconds: int = 0,
) -> TrackSnapshot:
    history = _history(latitude, longitude, sog_kn, cog_deg, stale_seconds=stale_seconds)
    return TrackSnapshot(
        vessel_id=vessel_id,
        mmsi=None,
        source_type=SourceType.SYNTHETIC_AIS,
        is_simulated=True,
        anchor_timestamp=ANCHOR,
        current_state=history[-1],
        history=history,
        data_status=DataStatus.STALE if stale_seconds else DataStatus.VALID,
    )


MOCK_TRACKS: tuple[TrackSnapshot, ...] = (
    _make_track("mock-vessel-001", 55.6800, 12.5600, 12.0, 48.0),
    _make_track("mock-vessel-002", 55.7200, 12.6500, 8.5, 222.0),
    _make_track("mock-vessel-003", 55.6400, 12.7200, 6.0, 5.0),
    _make_track("mock-vessel-004", 55.7550, 12.4700, 10.0, 302.0, stale_seconds=180),
)


def list_tracks(source_type: SourceType | None = None) -> list[TrackSnapshot]:
    if source_type is None:
        return list(MOCK_TRACKS)
    return [track for track in MOCK_TRACKS if track.source_type == source_type]


def get_track(vessel_id: str) -> TrackSnapshot | None:
    return next((track for track in MOCK_TRACKS if track.vessel_id == vessel_id), None)
