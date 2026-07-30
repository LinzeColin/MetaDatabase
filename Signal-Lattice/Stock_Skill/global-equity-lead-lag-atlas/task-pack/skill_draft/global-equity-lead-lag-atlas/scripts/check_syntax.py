#!/usr/bin/env python3
from __future__ import annotations

import ast
import json
import re
import sys
from pathlib import Path

try:
    import tomllib  # Python 3.11+
except ModuleNotFoundError:  # pragma: no cover - exercised on Python 3.10 hosts
    tomllib = None  # type: ignore[assignment]


def check_toml(text: str) -> None:
    if tomllib is not None:
        tomllib.loads(text)
        return
    section = re.compile(r"^\[[A-Za-z0-9_.-]+\]$")
    assignment = re.compile(r"^[A-Za-z0-9_.-]+\s*=\s*.+$")
    for line_number, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if section.fullmatch(line) or assignment.fullmatch(line):
            continue
        raise ValueError(f"Python 3.10 TOML fallback 无法识别第 {line_number} 行")
    for required in ("[build-system]", "[project]", "name =", "version ="):
        if required not in text:
            raise ValueError(f"TOML 缺少关键片段: {required}")


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    errors: list[str] = []
    checked = 0
    for path in sorted(root.rglob("*")):
        if not path.is_file() or any(part in {"__pycache__", ".git"} for part in path.parts):
            continue
        rel = path.relative_to(root).as_posix()
        try:
            if path.suffix == ".py":
                ast.parse(path.read_text(encoding="utf-8"), filename=rel, feature_version=(3, 10))
                checked += 1
            elif path.suffix == ".json":
                json.loads(path.read_text(encoding="utf-8"))
                checked += 1
            elif path.suffix == ".toml":
                check_toml(path.read_text(encoding="utf-8"))
                checked += 1
        except Exception as exc:
            errors.append(f"{rel}: {exc}")
    print(json.dumps({
        "status": "PASS" if not errors else "FAIL",
        "checked": checked,
        "python": sys.version.split()[0],
        "python_310_grammar": True,
        "errors": errors,
    }, ensure_ascii=False, indent=2))
    return 0 if not errors else 2


if __name__ == "__main__":
    raise SystemExit(main())
