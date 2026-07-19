#!/usr/bin/env python3
from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[2]
source = json.loads((ROOT / "machine/facts/human_docs_source.json").read_text(encoding="utf-8"))
out_dir = ROOT / "文档"
out_dir.mkdir(parents=True, exist_ok=True)
header = "<!-- GENERATED FROM machine/facts/human_docs_source.json; DO NOT EDIT DIRECTLY -->\n\n"
for name, content in source["documents"].items():
    (out_dir / name).write_text(header + content.strip() + "\n", encoding="utf-8")
print(f"rendered {len(source['documents'])} documents")
