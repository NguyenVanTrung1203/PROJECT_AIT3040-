"""Command line interface for deterministic cleaned-AIS replay events."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
from typing import Any

from src.data.ais_replay import ReplayInputError, run_replay


def _outside(path: Path, protected: list[Path]) -> Path:
    result = path.expanduser().resolve()
    for root in protected:
        root = root.resolve()
        if result == root or root in result.parents:
            raise ReplayInputError(f"output/temp path must not be inside protected source/data root: {root.name}")
    return result


def _utc_arg(value: str) -> str:
    # parse_utc performs the explicit UTC/offset validation in run_replay.
    return value


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Stream and QC cleaned AIS Parquet into ordered JSONL replay events.")
    parser.add_argument("--source-root", default=os.environ.get("AIS_REPLAY_ROOT"),
                        help="ais_cleaned root (or set AIS_REPLAY_ROOT)")
    parser.add_argument("--start", required=True, type=_utc_arg, help="inclusive ISO-8601 UTC start")
    parser.add_argument("--end", required=True, type=_utc_arg, help="exclusive ISO-8601 UTC end")
    parser.add_argument("--mmsi", action="append", help="nine-digit MMSI filter; repeat for multiple MMSIs")
    parser.add_argument("--max-events", type=int, default=10_000,
                        help="maximum valid ordered events written (the selected window is fully scanned)")
    parser.add_argument("--batch-size", type=int, default=8_192, help="bounded Parquet/sort batch size")
    parser.add_argument("--temp-root", help="temporary sort parent outside the source tree")
    parser.add_argument("--output", default="-", help="JSONL destination; default stdout, existing files are not overwritten")
    parser.add_argument("--summary-file", help="write QC summary JSON to a new file")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.source_root:
        parser.error("--source-root or AIS_REPLAY_ROOT is required")
    source_root = Path(args.source_root).expanduser().resolve(strict=True)
    repository_root = Path(__file__).resolve().parents[2]
    protected = [source_root, repository_root / "DATASET_FINAL"]
    output_path: Path | None = None
    summary_path: Path | None = None
    output_stream = sys.stdout
    try:
        if args.output != "-":
            output_path = _outside(Path(args.output), protected)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_stream = output_path.open("x", encoding="utf-8", newline="\n")
        if args.summary_file:
            summary_path = _outside(Path(args.summary_file), protected)
            summary_path.parent.mkdir(parents=True, exist_ok=True)
        temp_root = _outside(Path(args.temp_root), protected) if args.temp_root else None

        def emit(event: dict[str, Any]) -> None:
            output_stream.write(json.dumps(event, sort_keys=True, separators=(",", ":"), allow_nan=False))
            output_stream.write("\n")

        report = run_replay(source_root=source_root, start=args.start, end=args.end,
                            emit=emit, mmsi_filter=args.mmsi, max_events=args.max_events,
                            batch_size=args.batch_size, temp_root=temp_root)
        if output_path is not None:
            output_stream.close()
        rendered = json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False) + "\n"
        if summary_path is not None:
            with summary_path.open("x", encoding="utf-8", newline="\n") as stream:
                stream.write(rendered)
        sys.stderr.write(rendered)
        return 2 if not report["complete_window"] else 0
    except (ReplayInputError, OSError) as exc:
        if output_path is not None and not output_stream.closed:
            output_stream.close()
        parser.exit(2, f"replay error: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())
