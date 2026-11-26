"""Exact source IDs, kept separate from geographic provenance."""
TEST_SOURCES = {
    'yang_lei': 'YANG_LEI',
    'real_ais_denmark_oct2025': 'REAL_AIS',
    'synthetic_ais_denmark_oct2025': 'SYNTHETIC_AIS',
}


def canonical_test_source(raw_source_id):
    try:
        return TEST_SOURCES[raw_source_id]
    except (KeyError, TypeError) as exc:
        raise ValueError('unknown Test source ID') from exc
