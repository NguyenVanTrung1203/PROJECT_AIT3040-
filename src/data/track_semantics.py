"""Shared TrackSnapshot identity/provenance rules; no source verification or I/O."""
from __future__ import annotations

import re
import unicodedata
import json
from functools import lru_cache
from pathlib import Path
from typing import Mapping, Any


def validate_track_semantics(track: Mapping[str, Any], *, profile: str = 'PRODUCTION_V1') -> None:
    """Raise ValueError on semantic mismatch; structural validation is a separate mandatory step.

    A matching MMSI only establishes internal consistency, not real-world ownership.
    LEGACY_MOCK accepts legacy identifiers; it never grants production validity.
    """
    if profile not in ('PRODUCTION_V1', 'LEGACY_MOCK'):
        raise ValueError('unknown validation profile')
    if not all(k in track for k in ('vessel_id', 'mmsi', 'source_type', 'is_simulated')):
        raise ValueError('identity and provenance fields are required')
    vessel, mmsi = track['vessel_id'], track['mmsi']
    source, simulated = track['source_type'], track['is_simulated']
    if not isinstance(vessel, str) or not vessel or not isinstance(simulated, bool):
        raise ValueError('invalid identity or simulation flag')
    if mmsi is not None and (not isinstance(mmsi, str) or re.fullmatch(r'[0-9]{9}', mmsi) is None):
        raise ValueError('MMSI must be null or nine ASCII digits')
    if source not in ('REAL_AIS', 'SYNTHETIC_AIS', 'YANG_LEI'):
        raise ValueError('unknown source type')
    if source == 'REAL_AIS':
        if simulated or mmsi is None or not vessel.startswith('physical_mmsi:'):
            raise ValueError('REAL_AIS requires physical MMSI and is_simulated=false')
    elif not simulated:
        raise ValueError('simulated source types require is_simulated=true')
    if vessel.startswith('physical_mmsi:'):
        if mmsi is None or vessel != f'physical_mmsi:{mmsi}':
            raise ValueError('physical vessel ID must match the MMSI field')
    elif vessel.startswith('simulated:') and mmsi is not None:
        raise ValueError('simulated identity cannot carry an unverified physical MMSI')
    if profile == 'PRODUCTION_V1':
        if vessel != unicodedata.normalize('NFC', vessel):
            raise ValueError('production vessel ID must be NFC')
        if vessel.startswith('physical_mmsi:'):
            pass  # Format and equality are already checked above.
        elif vessel.startswith('simulated:'):
            dataset, sep, stable_id = vessel[len('simulated:'):].partition(':')
            if not sep or not dataset or not stable_id:
                raise ValueError('simulated identity requires dataset and stable ID')
        else:
            raise ValueError('legacy or unknown identity is not production-valid')
        try:
            vessel.encode('utf-8')
        except UnicodeEncodeError as exc:
            raise ValueError('production identity must be valid UTF-8') from exc


@lru_cache(maxsize=1)
def _production_validator() -> Any:
    # Lazy imports keep the Pydantic mock's semantic path independent of the
    # optional jsonschema tooling; references resolve only against local files.
    from jsonschema import Draft202012Validator, FormatChecker
    from referencing import Registry, Resource
    root = Path(__file__).resolve().parents[2] / 'contracts'
    base = 'https://schemas.ait3040.invalid/contracts/'
    registry = Registry()
    for name in ('common', 'track_snapshot', 'replay'):
        doc = json.loads((root / f'{name}.schema.json').read_text(encoding='utf-8'))
        Draft202012Validator.check_schema(doc)
        doc['$id'] = base + name + '.schema.json'
        registry = registry.with_resource(doc['$id'], Resource.from_contents(doc))
    return Draft202012Validator({'$ref':base+'replay.schema.json#/$defs/production_track'},
                                registry=registry, format_checker=FormatChecker())


def validate_production_track_g11(track: Mapping[str, Any]) -> None:
    """Run the V1 production structural schema, then G11 identity/provenance rules.

    Validation errors propagate; no data is coerced or modified. G11 is only
    part of the contract: callers must still enforce temporal/history,
    session and other semantic invariants and verify upstream source identity.
    """
    _production_validator().validate(track)
    validate_track_semantics(track, profile='PRODUCTION_V1')
