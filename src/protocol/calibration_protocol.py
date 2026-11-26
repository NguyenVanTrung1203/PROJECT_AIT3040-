"""Validate the approved offline protocol; this module does not calibrate models."""
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import yaml


class ProtocolError(ValueError):
    """Protocol is malformed or differs from the approved specification."""


class UniqueLoader(yaml.SafeLoader):
    pass


def _unique_mapping(loader, node, deep=False):
    result = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in result:
            raise ProtocolError(f'duplicate YAML key: {key}')
        result[key] = loader.construct_object(value_node, deep=deep)
    return result


UniqueLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _unique_mapping)


def semantic_sha256(config):
    encoded = json.dumps(config, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode('utf-8')
    return hashlib.sha256(encoded).hexdigest()


# Pinned after independent transcription of the approved D1–D7 protocol.
APPROVED_SEMANTIC_SHA256 = '23d427ea6416104efbc9e988aaaa6c774118a517aea528b1ecb0c8350de4bf0b'


def validate_protocol(config):
    if not isinstance(config, dict):
        raise ProtocolError('protocol must be a mapping')
    try:
        actual = semantic_sha256(config)
    except (TypeError, ValueError) as exc:
        raise ProtocolError('invalid protocol values') from exc
    if actual != APPROVED_SEMANTIC_SHA256:
        raise ProtocolError('protocol differs from approved D1–D7 specification')
    return config


def load_protocol(path):
    try:
        config = yaml.load(Path(path).read_text(encoding='utf-8-sig'), Loader=UniqueLoader)
        return validate_protocol(config)
    except (OSError, yaml.YAMLError) as exc:
        raise ProtocolError(str(exc)) from exc


def threshold_grid(config):
    """Return exact Decimal grid, without performing threshold selection."""
    validate_protocol(config)
    grid = config['calibration']['grid']
    return tuple(Decimal(i) / Decimal(grid['denominator']) for i in range(grid['start_index'], grid['end_index_inclusive'] + 1))


def validate_group_assignment(groups, folds):
    """Check group isolation on caller-provided assignments; does not construct folds."""
    if len(groups) != len(folds) or not groups:
        raise ProtocolError('group and fold assignments must be nonempty and aligned')
    assigned = {}
    for group, fold in zip(groups, folds):
        if group is None or fold is None:
            raise ProtocolError('missing group or fold')
        if group in assigned and assigned[group] != fold:
            raise ProtocolError('dependency group split between folds')
        assigned[group] = fold
    return True
