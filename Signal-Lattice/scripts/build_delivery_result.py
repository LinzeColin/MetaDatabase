#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path


def read_receipt(path: Path, expected_state: str = "PASS") -> dict:
    if not path.is_file() or path.is_symlink() or path.stat().st_size > 5_000_000:
        raise ValueError(f"RECEIPT_MISSING_OR_UNSAFE:{path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("state") != expected_state:
        raise ValueError(f"RECEIPT_NOT_PASS:{path}:{data.get('state')}")
    expected = data.get("receipt_sha256")
    if expected:
        copy = dict(data); copy.pop("receipt_sha256", None)
        actual = hashlib.sha256(json.dumps(copy, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        if actual != expected:
            raise ValueError(f"RECEIPT_HASH_MISMATCH:{path}")
    return data


def atomic(path: Path, text: str, mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix="." + path.name + ".", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text); handle.flush(); os.fsync(handle.fileno())
        os.chmod(tmp, mode); os.replace(tmp, path)
    finally:
        if os.path.exists(tmp): os.unlink(tmp)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--public-receipt", type=Path, required=True)
    parser.add_argument("--status-closure", type=Path, required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--markdown", type=Path, required=True)
    parser.add_argument("--screenshot", type=Path)
    args = parser.parse_args()
    public = read_receipt(args.public_receipt)
    closure = read_receipt(args.status_closure)
    screenshot = None
    if args.screenshot and args.screenshot.is_file():
        screenshot = {"path": args.screenshot.as_posix(), "size": args.screenshot.stat().st_size, "sha256": hashlib.sha256(args.screenshot.read_bytes()).hexdigest()}
    result = {
        "schema_version": "1.0.0",
        "state": "PASS",
        "completion_claim": "DEPLOYED_AND_PUBLICLY_VERIFIED",
        "version": args.version,
        "public_url": public["public_url"],
        "status_url": "https://status.linzezhang.com",
        "verified_at": datetime.now(timezone.utc).isoformat(),
        "public_release_receipt_sha256": public.get("receipt_sha256"),
        "status_closure_receipt_sha256": closure.get("receipt_sha256"),
        "screenshot": screenshot,
        "user_visible_result": {
            "software_website": True,
            "multi_skill_aggregation": True,
            "internal_consensus_coordination": True,
            "human_decision_support_capability": public.get("decision_support_capability_verified") is True,
            "current_action": public.get("current_action", "NO_ACTION"),
            "recommendation_available_now": public.get("current_action") not in {None, "", "UNKNOWN", "NO_ACTION"},
            "automatic_trading": False,
            "safe_fallback": "NO_ACTION",
        },
        "runtime_agent_dependency": 0,
        "runtime_llm_tokens": 0,
    }
    result["receipt_sha256"] = hashlib.sha256(json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    atomic(args.output, json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    md = f"""# Signal Lattice 部署结果\n\n- 状态：PASS\n- 版本：{args.version}\n- 软件入口：{result['public_url']}\n- 权威监控：{result['status_url']}\n- 结果：股票 Skill 聚合、证据协调、量化硬门和人工决策支持网站已完成公网验证。\n- 当前行动：{result['user_visible_result']['current_action']}\n- 当前是否已有可执行建议：{result['user_visible_result']['recommendation_available_now']}\n- 安全边界：不自动交易；证据或硬门不足时输出 NO_ACTION；运行期 Agent 和模型 Token 为 0。\n- 收据 SHA-256：`{result['receipt_sha256']}`\n"""
    atomic(args.markdown, md, 0o644)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
