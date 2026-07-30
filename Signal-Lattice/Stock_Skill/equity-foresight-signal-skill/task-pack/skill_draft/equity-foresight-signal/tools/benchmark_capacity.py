from __future__ import annotations

import argparse
import json
import platform
import statistics
import time
import tracemalloc
from pathlib import Path

from equity_foresight_signal import evaluate, evaluate_prepared, prepare_bundle

ROOT = Path(__file__).resolve().parents[1]


def load(name: str) -> dict:
    return json.loads((ROOT / "fixtures" / name).read_text(encoding="utf-8"))


def measure(callable_, iterations: int, repeats: int) -> dict:
    throughputs = []
    peaks = []
    for _ in range(repeats):
        tracemalloc.start()
        start = time.perf_counter()
        for _index in range(iterations):
            callable_()
        elapsed = time.perf_counter() - start
        _current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        throughputs.append(iterations / elapsed)
        peaks.append(peak)
    return {
        "iterations_per_repeat": iterations,
        "repeats": repeats,
        "throughput_per_second_p50": statistics.median(throughputs),
        "throughput_per_second_min": min(throughputs),
        "peak_bytes_max": max(peaks),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--iterations", type=int, default=1000)
    parser.add_argument("--repeats", type=int, default=3)
    args = parser.parse_args()
    if not 10 <= args.iterations <= 100_000 or not 1 <= args.repeats <= 20:
        parser.error("bounded iterations/repeats required")
    bundle = load("bundle.json")
    request = load("request.json")
    prepared = prepare_bundle(bundle)
    result = {
        "schema": "efs.internal_capacity_observation.v1",
        "environment": {
            "python": platform.python_version(),
            "implementation": platform.python_implementation(),
            "machine": platform.machine(),
            "platform": platform.platform(),
        },
        "regular": measure(lambda: evaluate(request, bundle), args.iterations, args.repeats),
        "prepared": measure(lambda: evaluate_prepared(request, prepared), args.iterations, args.repeats),
        "claim_boundary": {
            "observed_environment_only": True,
            "not_a_production_slo": True,
            "not_7x24_evidence": True,
            "no_real_time_soak": True,
        },
    }
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
