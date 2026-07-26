#!/usr/bin/env python3
from __future__ import annotations

import sys
from collections import Counter, defaultdict, deque
from pathlib import Path

import yaml

REQUIRED = {
    'id', 'title', 'stage', 'phase', 'dependencies', 'inputs', 'outputs', 'actions',
    'verification', 'required_evidence', 'risks', 'rollback', 'stop_conditions',
    'acceptance_criteria', 'pass_gate', 'completion_rule', 'effort_points',
    'parallel_continuation', 'status_values'
}
REQUIRED_STATUSES = {'not_started', 'in_progress', 'activation_pending', 'hazard_blocked', 'failed', 'passed'}


def main() -> int:
    if len(sys.argv) != 2:
        print('usage: validate_task_dag.py <task-dag.yaml>', file=sys.stderr)
        return 2
    path = Path(sys.argv[1])
    data = yaml.safe_load(path.read_text(encoding='utf-8'))
    tasks = data.get('tasks') or []
    errors: list[str] = []

    for authority in data.get('authority_order') or []:
        target = path.parent / authority
        if not target.exists():
            errors.append(f'authority_missing:{authority}')

    facts = data.get('canonical_facts') or {}
    if facts.get('real_time_soak_gate') is not False:
        errors.append('real_time_soak_gate_not_false')
    if facts.get('credential_wait_blocks_development') is not False:
        errors.append('credential_wait_blocks_development_not_false')

    ids = [t.get('id') for t in tasks]
    for key, count in Counter(ids).items():
        if key is None or count != 1:
            errors.append(f'duplicate_or_missing_id:{key}:{count}')
    known = set(ids)

    stage_counts: Counter[str] = Counter()
    indegree: dict[str, int] = {x: 0 for x in known}
    outgoing: dict[str, list[str]] = defaultdict(list)

    for t in tasks:
        missing = REQUIRED - set(t)
        if missing:
            errors.append(f"{t.get('id')}:missing_fields:{sorted(missing)}")
        stage_counts[t.get('stage')] += 1
        if not t.get('acceptance_criteria'):
            errors.append(f"{t.get('id')}:no_acceptance_criteria")
        if not t.get('verification'):
            errors.append(f"{t.get('id')}:no_verification")
        if not t.get('required_evidence'):
            errors.append(f"{t.get('id')}:no_evidence")
        statuses = set(t.get('status_values') or [])
        if statuses != REQUIRED_STATUSES:
            errors.append(f"{t.get('id')}:status_values_mismatch:{sorted(statuses)}")
        if not isinstance(t.get('effort_points'), int) or t.get('effort_points') < 1:
            errors.append(f"{t.get('id')}:invalid_effort_points")
        for dep in t.get('dependencies') or []:
            if dep not in known:
                errors.append(f"{t.get('id')}:unknown_dependency:{dep}")
                continue
            indegree[t['id']] += 1
            outgoing[dep].append(t['id'])

    for stage, count in stage_counts.items():
        if count > 5:
            errors.append(f'stage_child_limit:{stage}:{count}>5')

    queue = deque(sorted(x for x, d in indegree.items() if d == 0))
    visited = []
    while queue:
        node = queue.popleft()
        visited.append(node)
        for nxt in outgoing[node]:
            indegree[nxt] -= 1
            if indegree[nxt] == 0:
                queue.append(nxt)
    if len(visited) != len(tasks):
        errors.append('dependency_cycle_detected')

    validation = data.get('dag_validation', {})
    if validation.get('real_time_soak_nodes') != 0:
        errors.append('real_time_soak_nodes_not_zero')
    if validation.get('credential_wait_nodes') != 0:
        errors.append('credential_wait_nodes_not_zero')
    if validation.get('fixed_elapsed_estimate_fields') != 0:
        errors.append('fixed_elapsed_estimate_fields_not_zero')

    declared = validation.get('task_count')
    if declared != len(tasks):
        errors.append(f'declared_task_count:{declared}!={len(tasks)}')

    if errors:
        for err in errors:
            print(f'ERROR={err}')
        print('DAG_VALIDATION=FAIL')
        return 1
    print(f'DAG_VALIDATION=PASS tasks={len(tasks)} stages={len(stage_counts)}')
    print('TOPOLOGICAL_ORDER=' + ','.join(visited))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
