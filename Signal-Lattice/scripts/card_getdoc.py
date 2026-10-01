#!/usr/bin/env python3
"""起草证据卡用：下载一份一手文档（PDF 自动转文本；SEC 链接自动带合规 User-Agent 与限速），并按正则打印上下文，方便复制原句。

    PYTHONPATH=src python3 scripts/card_getdoc.py "<URL>" "<正则1>" "<正则2>" [--cache DIR]

文本缓存默认放在系统临时目录下的 signal-lattice-card-docs/（用完请删掉，不进仓库）。状态码不是 200 = 这个链接不能写进卡片。
PDF 需要 pypdf。只打印，不联网以外的任何写操作。
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import re
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("verify_evidence_cards", HERE / "verify_evidence_cards.py")
verify = importlib.util.module_from_spec(spec)
spec.loader.exec_module(verify)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("url")
    parser.add_argument("patterns", nargs="*")
    parser.add_argument("--cache", type=Path, default=Path(tempfile.gettempdir()) / "signal-lattice-card-docs")
    args = parser.parse_args()
    args.cache.mkdir(parents=True, exist_ok=True)
    path = args.cache / (hashlib.sha1(args.url.encode()).hexdigest()[:10] + ".txt")
    if not path.exists():
        status, body, content_type, _ = verify.fetch(args.url, verify.DEFAULT_SEC_UA)
        if status != 200:
            print("STATUS", status, content_type)
            return 1
        text, kind = verify.page_text(body, content_type, args.url)
        if text is None:
            print("NOTEXT", kind)
            return 1
        path.write_text(text, "utf-8")
    flat = re.sub(r"\s+", " ", path.read_text("utf-8"))
    print("OK", path, len(flat), "chars")
    for pattern in args.patterns:
        print("== ", pattern)
        for match in list(re.finditer(pattern, flat, re.I))[:6]:
            print("  ...", flat[max(0, match.start() - 300): match.end() + 400], "...\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
