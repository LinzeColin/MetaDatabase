#!/usr/bin/env python3
"""Idempotently add a file-based external-project adapter to LinzeStatus collector."""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import shutil
import sys

VERSION = "0.0.0.1.7"
BEGIN = "# BEGIN WEREAD PORT EXTERNAL ADAPTERS"
END = "# END WEREAD PORT EXTERNAL ADAPTERS"
DEFAULT_DIR = "/srv/linze/apps/status/data/external-projects"
HELPER = f'''{BEGIN}
def external_project_adapters():
    """Load sanitized project descriptors written by independent operations planes."""
    root = os.environ.get("STATUS_EXTERNAL_PROJECTS_DIR", {DEFAULT_DIR!r})
    required = {{"name", "url", "parts", "host", "db", "store", "deploy", "backup", "agent", "notify"}}
    rows = []
    try:
        names = sorted(name for name in os.listdir(root) if name.endswith(".json"))
    except Exception:
        return rows
    for name in names[:100]:
        path = os.path.join(root, name)
        try:
            if os.path.islink(path) and not os.path.isfile(path):
                continue
            with open(path, encoding="utf-8") as handle:
                payload = json.load(handle)
            candidate = payload.get("project", payload) if isinstance(payload, dict) else None
            if not isinstance(candidate, dict) or not required.issubset(candidate):
                continue
            row = {{key: candidate[key] for key in required}}
            if not isinstance(row["name"], str) or not isinstance(row["url"], str):
                continue
            if row["url"] and not row["url"].startswith("https://"):
                continue
            rows.append(row)
        except Exception:
            continue
    return rows
{END}
'''


def patch_text(source: str) -> str:
    if BEGIN in source:
        return source
    anchor = "# ---------- 项目实时状态 ----------"
    if anchor not in source or "for p in PROJECTS:" not in source:
        raise RuntimeError("Collector shape is not the reviewed LinzeStatus contract")
    updated = source.replace(anchor, HELPER + anchor, 1)
    updated = updated.replace("for p in PROJECTS:", "for p in PROJECTS + external_project_adapters():", 1)
    compile(updated, "collect.py", "exec")
    return updated


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("collector", type=pathlib.Path)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    collector = args.collector.expanduser().resolve()
    source = collector.read_text(encoding="utf-8")
    updated = patch_text(source)
    changed = updated != source
    if changed and args.apply:
        backup = collector.with_name(f"{collector.name}.before-weread-port-{VERSION}")
        if not backup.exists():
            shutil.copy2(collector, backup)
        temporary = collector.with_suffix(collector.suffix + ".weread-port.tmp")
        temporary.write_text(updated, encoding="utf-8")
        os.replace(temporary, collector)
    result = {
        "status": "applied" if changed and args.apply else "planned" if changed else "already_present",
        "collector": str(collector),
        "changed": changed,
        "apply": bool(args.apply),
        "adapterDirectory": DEFAULT_DIR,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"状态适配器安装失败: {exc}", file=sys.stderr)
        raise SystemExit(2)
