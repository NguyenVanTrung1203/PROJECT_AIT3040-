"""Read-only T13 index audit and reproducible data/API timing harness.

This script does not load a model, change locked data, or derive model metrics.
"""
from __future__ import annotations

import argparse
import json
import platform
import statistics
import sys
import time
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.data.dataset_loader import DatasetLoader
from src.data.tensor_verification import verify


def audit_indexes(dataset_root: str | Path | None = None) -> dict:
    loader = DatasetLoader(dataset_root)
    split_manifest = pd.read_csv(loader.root / "manifests/split_mapping.csv", dtype={"encounter_id": str})
    global_index = pd.read_parquet(loader.root / "manifests/global_encounter_index.parquet")
    required_split = {"encounter_id", "original_encounter_id", "data_source", "package_split", "high_risk_label"}
    required_global = {"encounter_id", "vessel", "vessel_id", "high_risk_label", "package_split"}
    if not required_split.issubset(split_manifest.columns) or not required_global.issubset(global_index.columns):
        raise ValueError("Official split/global index columns are missing")
    if split_manifest["encounter_id"].duplicated().any() or len(split_manifest) != loader.lock["encounters"]:
        raise ValueError("Split mapping contains duplicate or missing encounters")
    if global_index["encounter_id"].nunique() != loader.lock["encounters"]:
        raise ValueError("Global index encounter count differs from the lock")
    if global_index["vessel"].isna().any() or not set(global_index["vessel"].unique()).issubset({"A", "B"}):
        raise ValueError("Global encounter index has invalid vessel slot identifiers")

    result = {"lock_status": loader.lock["lock_status"], "dataset_version": loader.lock["dataset_version"],
              "encounters": {}, "official_ab_pairing": "PASS", "split_manifest_mapping": "PASS",
              "label_mapping": "PASS", "global_encounter_index": "PASS"}
    normalized_sources = {
        "yang_lei": {"yang_lei", "yanglei"},
        "real_ais": {"real_ais", "real_ais_kattegat_v3", "real_ais_denmark_oct2025"},
        "synthetic_ais": {"synthetic_ais", "augmented_real_ais_kattegat_v3", "synthetic_ais_denmark_oct2025"},
    }
    for split, cfg in loader.config["splits"].items():
        data = loader.load_split(split)
        mapping = split_manifest[split_manifest["package_split"] == split].copy()
        if len(data.encounters) != cfg["encounters"] or len(mapping) != cfg["encounters"]:
            raise ValueError(f"{split}: encounter count differs from config/manifest")
        ids = data.encounters["encounter_id"].astype(str).tolist()
        if set(ids) != set(mapping["encounter_id"].astype(str)):
            raise ValueError(f"{split}: tensor index and official split mapping differ")
        mapped = mapping.set_index("encounter_id").loc[ids]
        if not (mapped["high_risk_label"].to_numpy() == data.labels).all():
            raise ValueError(f"{split}: labels differ from official split mapping")
        meta = data.metadata.set_index(data.metadata["encounter_id"].astype(str))
        if not (meta.loc[ids, "high_risk_label"].to_numpy() == data.labels).all():
            raise ValueError(f"{split}: metadata labels differ from tensor labels")

        vessel_rows = data.vessels
        for encounter_index, encounter_id in enumerate(ids):
            pair_rows = data.pairs[encounter_index]
            pair = vessel_rows.set_index("X_row").loc[pair_rows]
            actual = dict(zip(pair["vessel"], pair["encounter_id"].astype(str)))
            if set(actual) != {"A", "B"} or any(value != encounter_id for value in actual.values()):
                raise ValueError(f"{split}: official A/B row mapping differs at {encounter_id}")
        global_split = global_index[global_index["package_split"] == split]
        if len(global_split) != cfg["encounters"] or global_split["encounter_id"].duplicated().any():
            raise ValueError(f"{split}: global encounter index should contain one row per encounter")
        global_by_id = global_split.set_index("encounter_id").loc[ids]
        if not (global_by_id["high_risk_label"].to_numpy() == data.labels).all():
            raise ValueError(f"{split}: global encounter labels differ from tensor labels")
        if not (global_by_id["package_split"].astype(str).to_numpy() == split).all():
            raise ValueError(f"{split}: global encounter index split mapping differs")

        actual_counts = mapping["data_source"].astype(str).value_counts().sort_index().to_dict()
        result["encounters"][split] = {
            "encounters": len(ids), "official_vessel_instances": len(data.vessels),
            "rows": data.records, "source_counts_manifest": actual_counts,
            "tensor_labels": {str(int(label)): int((data.labels == label).sum()) for label in sorted(set(data.labels.tolist()))},
            "official_A_B_pairing": "PASS", "split_and_label_mapping": "PASS",
        }

    result["source_aliases"] = {
        "validation_augmented_real_ais_kattegat_v3": "normalized by T03 lock/source audit as synthetic_ais",
        "scope": "No split or source field modified; aliases are reported exactly as present in the official split mapping.",
    }
    return result


def _percentile(values: list[float], percentile: float) -> float:
    ordered = sorted(values)
    return round(ordered[min(len(ordered) - 1, int((len(ordered) - 1) * percentile))], 3)


def benchmark_api(iterations: int, warmups: int) -> dict:
    from fastapi.testclient import TestClient
    from backend.app.main import app
    from backend.app.replay_api import build_default_replay_api, DEMO_SOURCE_ID

    original = getattr(app.state, "replay_api", None)
    app.state.replay_api = build_default_replay_api()
    try:
        client = TestClient(app)
        created = client.post("/api/v1/replay/sessions", json={"source_id": DEMO_SOURCE_ID,
                              "start_time": "2024-11-01T00:09:00Z"})
        created.raise_for_status()
        session_id = created.json()["session_id"]
        first = client.get(f"/api/v1/replay/sessions/{session_id}/tracks")
        first.raise_for_status()
        page = first.json()
        vessel_id = page["items"][0]["vessel_id"]

        listing, detail = [], []
        for index in range(warmups + iterations):
            started = time.perf_counter_ns()
            response = client.get(f"/api/v1/replay/sessions/{session_id}/tracks")
            response.raise_for_status()
            elapsed = (time.perf_counter_ns() - started) / 1_000_000
            if index >= warmups:
                listing.append(elapsed)

            started = time.perf_counter_ns()
            response = client.get(f"/api/v1/replay/sessions/{session_id}/tracks/{vessel_id}",
                                  params={"snapshot_id": page["snapshot_id"]})
            response.raise_for_status()
            elapsed = (time.perf_counter_ns() - started) / 1_000_000
            if index >= warmups:
                detail.append(elapsed)
        return {"scope": "in-process FastAPI TestClient; fixture-only; no network; no model inference",
                "iterations": iterations, "warmups": warmups,
                "fixture_event_count": 10, "snapshot_track_count": page["total"],
                "track_history_points": len(page["items"][0]["history"]),
                "list_tracks_ms": {"median": round(statistics.median(listing), 3), "p95": _percentile(listing, .95)},
                "get_track_ms": {"median": round(statistics.median(detail), 3), "p95": _percentile(detail, .95)}}
    finally:
        app.state.replay_api = original


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iterations", type=int, default=30)
    parser.add_argument("--warmups", type=int, default=3)
    parser.add_argument("--output", type=Path, default=Path("evaluation/s3_t13/t13_benchmark_results.json"))
    args = parser.parse_args()
    if args.iterations < 1 or args.warmups < 0:
        parser.error("iterations must be positive and warmups non-negative")
    started = time.perf_counter()
    integrity = verify()
    audit = audit_indexes()
    api = benchmark_api(args.iterations, args.warmups)
    result = {"status": "PASS", "python": platform.python_version(), "platform": platform.platform(),
              "integrity_verification": integrity, "index_audit": audit, "runtime_benchmark": api,
              "total_elapsed_seconds": round(time.perf_counter() - started, 3),
              "model_metrics": "NOT_RUN", "test_calibration": "NOT_RUN", "dataset_modified": False}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"status": result["status"], "output": str(args.output),
                      "checksums": integrity["checksum"], "splits": audit["encounters"],
                      "runtime_benchmark": api, "total_elapsed_seconds": result["total_elapsed_seconds"]},
                     indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
