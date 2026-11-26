"""Extra C1-C5 gate for a full technical rerun, layered on T15 lock gate."""
from pathlib import Path
from src.evaluation.t15_authorization import AuthorizationError,_read_pinned_json
from src.release.offline_lock import digest


def validate_full_scope(record,protocol,evidence,inventory_sha):
    if record.get('full_approval')!='C1-C5' or record.get('full_scope')!='AUDITED_FULL_TECHNICAL_RERUN' or record.get('parent_r2_run')!='s4_t15_r2_20261125T152141Z_2cd800cd':raise AuthorizationError('full rerun approval/scope mismatch')
    if protocol.get('revision_classification')!='TECHNICAL_ACCESS_AUDIT_CORRECTION' or record.get('audit_inventory_sha256')!=inventory_sha or protocol.get('audit_inventory_sha256')!=inventory_sha:raise AuthorizationError('audit protocol/inventory mismatch')
    needed=('synthetic_end_to_end','synthetic_negative_audit_tests','audit_completeness_verifier','materialization_semantics','q1_no_test_deserialization','full_regression')
    if not all(evidence.get(x) is True for x in needed):raise AuthorizationError('full rerun preflight incomplete')


def validate_pins(*,record_path,record_sha,protocol_path,protocol_sha,evidence_path,evidence_sha,inventory_path,inventory_sha):
    record=_read_pinned_json(record_path,record_sha);protocol=_read_pinned_json(protocol_path,protocol_sha);evidence=_read_pinned_json(evidence_path,evidence_sha)
    if digest(Path(inventory_path))!=inventory_sha:raise AuthorizationError('audit inventory identity mismatch')
    validate_full_scope(record,protocol,evidence,inventory_sha)
    return record,protocol,evidence
