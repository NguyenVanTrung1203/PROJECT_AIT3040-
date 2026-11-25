"""Exact nanosecond UTC parsing for replay clocks and selected AIS timestamps."""
from __future__ import annotations

from datetime import datetime, timezone
import re


_ISO_UTC = re.compile(
    r"^(\d{4}-\d{2}-\d{2})T(\d{2}:\d{2}:\d{2})(?:\.(\d{1,9}))?(Z|\+00:00)$"
)
_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


class ReplayTimeError(ValueError):
    """Timestamp is not an explicit, known UTC instant."""


def parse_utc_ns(value: str | datetime, *, field: str = "timestamp") -> int:
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() != timezone.utc.utcoffset(value):
            raise ReplayTimeError(f"{field} must carry an explicit UTC offset")
        value = value.astimezone(timezone.utc)
        delta = value - _EPOCH
        return ((delta.days * 86400 + delta.seconds) * 1_000_000 + delta.microseconds) * 1000
    if not isinstance(value, str):
        raise ReplayTimeError(f"{field} must be an ISO-8601 UTC string")
    match = _ISO_UTC.fullmatch(value)
    if not match:
        raise ReplayTimeError(f"{field} must be ISO-8601 with a known UTC Z or +00:00 offset")
    day, clock, fraction, _zone = match.groups()
    try:
        whole = datetime.strptime(f"{day}T{clock}", "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)
    except ValueError as exc:
        raise ReplayTimeError(f"{field} is not a valid UTC timestamp") from exc
    delta = whole - _EPOCH
    whole_ns = (delta.days * 86400 + delta.seconds) * 1_000_000_000
    fraction_ns = int((fraction or "").ljust(9, "0")) if fraction else 0
    return whole_ns + fraction_ns


def utc_iso_ns(value: int) -> str:
    seconds, nanos = divmod(int(value), 1_000_000_000)
    whole = datetime.fromtimestamp(seconds, timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    fraction = f".{nanos:09d}".rstrip("0") if nanos else ""
    return f"{whole}{fraction}Z"
