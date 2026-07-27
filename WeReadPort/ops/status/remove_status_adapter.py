#!/usr/bin/env python3
"""仅移除微信读书笔记迁移状态适配区块及循环扩展。"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import re
import sys

BEGIN = "# BEGIN WEREAD PORT EXTERNAL ADAPTERS"
END = "# END WEREAD PORT EXTERNAL ADAPTERS"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("collector", type=pathlib.Path)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    collector = args.collector.expanduser().resolve()
    source = collector.read_text(encoding="utf-8")
    pattern = re.compile(rf"{re.escape(BEGIN)}.*?{re.escape(END)}\n?", re.DOTALL)
    updated = pattern.sub("", source, count=1)
    updated = updated.replace("for p in PROJECTS + external_project_adapters():", "for p in PROJECTS:", 1)
    compile(updated, str(collector), "exec")
    changed = updated != source
    if changed and args.apply:
        temporary = collector.with_suffix(collector.suffix + ".weread-port-remove.tmp")
        temporary.write_text(updated, encoding="utf-8", newline="\n")
        os.replace(temporary, collector)
    print(json.dumps({"status": "removed" if changed and args.apply else "planned" if changed else "absent", "collector": str(collector), "changed": changed}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"状态适配器移除失败: {exc}", file=sys.stderr)
        raise SystemExit(2)
