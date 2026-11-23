"""D-06 test reference, not an identity registry or Encounter runtime."""
import hashlib
import json
import re
import unicodedata
from datetime import datetime, timezone
from uuid import UUID

PAIR = re.compile(r'pair:v1:[0-9a-f]{64}\Z')
PHYSICAL = re.compile(r'[0-9]{9}\Z')


def canonical_vessel_id(value, allowed_namespaces):
    if not isinstance(value, str):
        raise ValueError('vessel ID must be a string')
    value = unicodedata.normalize('NFC', value)
    namespace, sep, source_id = value.partition(':')
    if not sep or namespace not in {'physical_mmsi', 'simulated'} or namespace not in allowed_namespaces or not source_id:
        raise ValueError('unknown namespace or empty source ID')
    if namespace == 'physical_mmsi' and not PHYSICAL.fullmatch(source_id):
        raise ValueError('physical MMSI must contain nine ASCII digits')
    if namespace == 'simulated':
        dataset, delimiter, stable_id = source_id.partition(':')
        if not delimiter or not dataset or not stable_id:
            raise ValueError('simulated IDs require a dataset and stable source ID')
    try:
        value.encode('utf-8')
    except UnicodeEncodeError as exc:
        raise ValueError('ID must be valid UTF-8') from exc
    return value


def pair_and_online_roles(first, second, allowed_namespaces):
    ids = [canonical_vessel_id(x, allowed_namespaces) for x in (first, second)]
    if ids[0] == ids[1]:
        raise ValueError('vessel IDs must differ after NFC')
    ids.sort(key=lambda value: value.encode('utf-8'))
    payload = json.dumps(ids, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
    return 'pair:v1:' + hashlib.sha256(payload).hexdigest(), tuple(ids)


def encounter_id(session_id, pair_id, anchor):
    # UUID is required in canonical lowercase spelling for V1.
    if not isinstance(session_id, str):
        raise ValueError('session must be a UUID string')
    try:
        parsed = UUID(session_id)
    except (ValueError, AttributeError) as exc:
        raise ValueError('invalid session UUID') from exc
    if str(parsed) != session_id:
        raise ValueError('reference accepts canonical lowercase UUID only')
    if not isinstance(pair_id, str) or not PAIR.fullmatch(pair_id):
        raise ValueError('invalid pair ID')
    if not isinstance(anchor, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:Z|\+00:00)', anchor):
        raise ValueError('anchor must be UTC with seconds precision')
    try:
        dt = datetime.fromisoformat(anchor.replace('Z', '+00:00'))
    except ValueError as exc:
        raise ValueError('invalid anchor') from exc
    normalized = dt.astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    payload = json.dumps([session_id, pair_id, normalized], ensure_ascii=False, separators=(',', ':')).encode('utf-8')
    return 'enc:v1:' + hashlib.sha256(payload).hexdigest()
