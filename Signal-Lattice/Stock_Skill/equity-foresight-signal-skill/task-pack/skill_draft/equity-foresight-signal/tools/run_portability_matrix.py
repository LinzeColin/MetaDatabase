from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

CHILD = r'''
import json
from pathlib import Path
from equity_foresight_signal import verify_golden_vector
root=Path(r"__ROOT__")
def load(name): return json.loads((root/"fixtures"/name).read_text(encoding="utf-8"))
report=verify_golden_vector(load("golden_vector.json"),bundle=load("bundle.json"),request=load("request.json"),pit_dataset=load("pit_dataset.json"),training_config=load("training_config.json"))
print(json.dumps(report,sort_keys=True,separators=(",",":")))
'''.replace("__ROOT__", str(ROOT))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--current-only", action="store_true")
    args = parser.parse_args()
    candidates = [sys.executable] if args.current_only else [f"python3.{minor}" for minor in range(9, 14)]
    rows = []
    seen = set()
    for candidate in candidates:
        executable = candidate if Path(candidate).is_absolute() else shutil.which(candidate)
        if not executable:
            rows.append({"requested": candidate, "status": "NOT_RUN_ENVIRONMENT", "reason": "INTERPRETER_NOT_FOUND"})
            continue
        real = str(Path(executable).resolve())
        if real in seen:
            continue
        seen.add(real)
        env = dict(os.environ)
        env["PYTHONPATH"] = str(ROOT)
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        completed = subprocess.run([real, "-B", "-c", CHILD], cwd=ROOT, env=env, capture_output=True, text=True, timeout=120)
        if completed.returncode == 0:
            payload = json.loads(completed.stdout)
            rows.append({
                "requested": candidate,
                "executable": real,
                "python": subprocess.check_output([real, "-B", "-c", "import platform;print(platform.python_version())"], env=env, text=True).strip(),
                "machine": platform.machine(),
                "status": payload["status"],
                "report_sha256": payload["report_sha256"],
            })
        else:
            rows.append({"requested": candidate, "executable": real, "status": "FAIL", "stderr": completed.stderr[-2000:]})
    result = {
        "schema": "efs.portability_matrix_execution.v1",
        "host_platform": platform.platform(),
        "host_machine": platform.machine(),
        "rows": rows,
        "cross_cpu_architecture_status": "NOT_RUN_SINGLE_HOST_ARCHITECTURE",
        "os_network_isolation_status": "NOT_PROVEN_BY_PORTABILITY_MATRIX",
    }
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
    return 0 if all(row["status"] in {"PASS", "NOT_RUN_ENVIRONMENT"} for row in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
