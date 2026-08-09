from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping

from abd_acceptance.canonical_facts import strict_json_load
from abd_acceptance.chinese_workbench import build_local_push_payload


def build_push_payload(ui_fixture: Mapping[str, Any], *, view_id: str | None = None) -> dict[str, Any]:
    """Build a local-only push payload; this phase never sends a notification."""

    return build_local_push_payload(ui_fixture, view_id=view_id)


def main() -> int:
    parser = argparse.ArgumentParser(description="ABD 本地中文工作台推送载荷生成器")
    parser.add_argument("--fixture", default="ui_fixtures.json", help="冻结工作台夹具路径")
    parser.add_argument("--view-id", help="要渲染的冻结视图标识")
    args = parser.parse_args()
    fixture = strict_json_load(Path(args.fixture))
    if not isinstance(fixture, Mapping):
        parser.error("fixture must be a JSON object")
    print(json.dumps(build_push_payload(fixture, view_id=args.view_id), ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
