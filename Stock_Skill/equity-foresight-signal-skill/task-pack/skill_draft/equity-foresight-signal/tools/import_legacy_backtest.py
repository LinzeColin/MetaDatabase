from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from equity_foresight_signal.legacy_evidence import build_legacy_backtest_receipt


def read_regular_file(path: Path, limit: int) -> bytes:
    stat_result = path.lstat()
    if path.is_symlink() or not path.is_file() or stat_result.st_size > limit:
        raise ValueError(f"unsafe or oversized input: {path.name}")
    data = path.read_bytes()
    if not data or len(data) > limit:
        raise ValueError(f"unsafe or oversized input: {path.name}")
    return data


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a truth-preserving legacy backtest receipt")
    parser.add_argument("--metrics", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source-label", required=True)
    args = parser.parse_args()
    receipt = build_legacy_backtest_receipt(
        model_metrics_csv=read_regular_file(args.metrics, 2_000_000),
        run_manifest_json=read_regular_file(args.manifest, 512_000),
        report_markdown=read_regular_file(args.report, 2_000_000),
        source_label=args.source_label,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(receipt, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "PASS", "output": args.output.name, "receipt_sha256": receipt["receipt_sha256"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
