#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ACTION="${1:?plan|task|stage|all}"
shift
case "$ACTION" in
  plan)
    if [[ $# -eq 1 ]]; then
      exec python3 "$ROOT/scripts/run_task.py" --task "$1" --plan
    fi
    python3 - "$ROOT" <<'PY'
import json,sys
from pathlib import Path
root=Path(sys.argv[1]);dag=json.loads((root/'machine/facts/task_dag.json').read_text())
for task in dag['tasks']:
 print(f"{task['id']} [{task['stage']}] {task['title']}")
PY
    ;;
  task)
    [[ $# -eq 1 ]] || { echo 'usage: codex_last_mile.sh task T-001' >&2; exit 2; }
    exec python3 "$ROOT/scripts/run_task.py" --task "$1" --execute
    ;;
  stage)
    [[ $# -eq 1 ]] || { echo 'usage: codex_last_mile.sh stage S0' >&2; exit 2; }
    STAGE="$1"
    mapfile -t TASKS < <(python3 - "$ROOT" "$STAGE" <<'PY'
import json,sys
from pathlib import Path
root,stage=Path(sys.argv[1]),sys.argv[2]
for task in json.loads((root/'machine/facts/task_dag.json').read_text())['tasks']:
 if task['stage']==stage:print(task['id'])
PY
)
    [[ ${#TASKS[@]} -gt 0 ]] || { echo UNKNOWN_STAGE >&2; exit 2; }
    for task in "${TASKS[@]}"; do python3 "$ROOT/scripts/run_task.py" --task "$task" --execute; done
    ;;
  all)
    mapfile -t TASKS < <(python3 - "$ROOT" <<'PY'
import json,sys
from pathlib import Path
for task in json.loads((Path(sys.argv[1])/'machine/facts/task_dag.json').read_text())['tasks']:print(task['id'])
PY
)
    for task in "${TASKS[@]}"; do python3 "$ROOT/scripts/run_task.py" --task "$task" --execute; done
    ;;
  *) echo INVALID_ACTION >&2; exit 2 ;;
esac
