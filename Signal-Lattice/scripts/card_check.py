#!/usr/bin/env python3
"""校验证据卡目录：结构（cards.parse_card）+ 核验印章（verification.json）。默认校验随包发布的目录。

    PYTHONPATH=src python3 scripts/card_check.py [DIR] [--as-of YYYY-MM-DD]

退出码 0 = 全部卡片结构合格、每条来源（含公司申报）都有 200 且摘录找到的印章。
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from signal_lattice.evidence import cards as C  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("directory", nargs="?", type=Path, default=C.CARDS_DIR)
    parser.add_argument("--as-of", default=date.today().isoformat())
    args = parser.parse_args()
    stamp_file = args.directory / C.VERIFICATION_FILE
    stamps = json.loads(stamp_file.read_text("utf-8")).get("entries", {}) if stamp_file.is_file() else {}
    bad = 0
    for path in sorted(args.directory.glob("*.yaml")):
        try:
            raw = C.parse_simple_yaml(path.read_text("utf-8"))
        except C.CardParseError as exc:
            print(path.name, "PARSE", exc)
            bad += 1
            continue
        card, problems = C.parse_card(raw, expected_id=path.stem)
        if card is None:
            print(path.name, "INVALID")
            for item in problems:
                print("  -", item)
            bad += 1
            continue
        sources = [(name, s) for name, f in card.factors.items() for s in f.sources] + [("company:" + c.symbol, c.source) for c in card.companies]
        card_bad = 0
        for where, source in sources:
            ok, why = C.source_verified(source, stamps, card.retrieved, args.as_of)
            if not ok:
                print("  ", where, source.url, why)
                card_bad += 1
        bad += card_bad
        print(path.name, "OK" if not card_bad else "PROBLEMS", "factors=", sorted(card.factors), "companies=", [c.symbol for c in card.companies])
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
