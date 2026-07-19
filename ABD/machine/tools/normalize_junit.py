#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import xml.etree.ElementTree as ET
from pathlib import Path


FIXED_CLOCK = "2026-07-19T00:00:00+10:00"


def normalize(path: Path) -> None:
    tree = ET.parse(str(path))
    root = tree.getroot()
    for element in root.iter():
        if element.tag == "testsuite":
            element.attrib.pop("hostname", None)
            element.set("timestamp", FIXED_CLOCK)
            element.set("time", "0.000")
        elif element.tag == "testcase":
            element.set("time", "0.000")
    ET.indent(tree, space="  ")
    temporary = path.with_name(path.name + ".tmp")
    tree.write(str(temporary), encoding="utf-8", xml_declaration=True, short_empty_elements=True)
    temporary.write_bytes(temporary.read_bytes() + b"\n")
    temporary.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser(description="Normalize pytest JUnit evidence deterministically")
    parser.add_argument("paths", nargs="+", type=Path)
    args = parser.parse_args()
    for path in args.paths:
        normalize(path)
    print(
        json.dumps(
            {"status": "PASS", "normalized": [path.as_posix() for path in args.paths]},
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
