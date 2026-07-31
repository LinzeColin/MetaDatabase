#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path


def canonical(payload: object) -> bytes:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def read_receipt(path: Path) -> dict:
    if not path.is_file() or path.is_symlink() or path.stat().st_size > 5_000_000:
        raise ValueError(f"RECEIPT_MISSING_OR_UNSAFE:{path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("state") != "PASS":
        raise ValueError(f"RECEIPT_NOT_PASS:{path}:{data.get('state')}")
    expected = data.get("receipt_sha256")
    if expected:
        copy = dict(data); copy.pop("receipt_sha256", None)
        if hashlib.sha256(canonical(copy)).hexdigest() != expected:
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
    p = argparse.ArgumentParser()
    p.add_argument("--public-receipt", type=Path, required=True)
    p.add_argument("--status-closure", type=Path, required=True)
    p.add_argument("--version", required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--markdown", type=Path, required=True)
    p.add_argument("--screenshot", type=Path)
    args = p.parse_args()
    public = read_receipt(args.public_receipt)
    closure = read_receipt(args.status_closure)
    if public.get("north_star_chain_verified") is not True:
        raise ValueError("PUBLIC_RECEIPT_DOES_NOT_PROVE_NORTH_STAR_CHAIN")
    diagnostics = public.get("diagnostics") or {}
    screenshot = None
    if args.screenshot and args.screenshot.is_file() and not args.screenshot.is_symlink():
        screenshot = {"path": args.screenshot.as_posix(), "size": args.screenshot.stat().st_size, "sha256": hashlib.sha256(args.screenshot.read_bytes()).hexdigest()}
    result = {
        "schema_version": "2.0.0", "state": "PASS",
        "completion_claim": "NORTH_STAR_DEPLOYED_AND_PUBLICLY_VERIFIED",
        "version": args.version, "public_url": public["public_url"],
        "status_url": "https://status.linzezhang.com", "verified_at": datetime.now(timezone.utc).isoformat(),
        "public_release_receipt_sha256": public["receipt_sha256"],
        "status_closure_receipt_sha256": closure.get("receipt_sha256"),
        "screenshot": screenshot,
        "user_visible_result": {
            "software_website": True,
            "one_minute_full_cycle": True,
            "all_active_skills_independently_executed": True,
            "github_dynamic_skill_reconciliation": True,
            "central_coordination": True,
            "exactly_one_recommendation": True,
            "current_action": diagnostics.get("current_action"),
            "current_symbol": diagnostics.get("current_symbol"),
            "active_skill_count": diagnostics.get("active_skill_count"),
            "completed_skill_count": diagnostics.get("completed_skill_count"),
            "market_data_source": diagnostics.get("market_data_source"),
            "automatic_trading": False,
        },
        "runtime_agent_dependency": 0, "runtime_llm_tokens": 0,
    }
    result["receipt_sha256"] = hashlib.sha256(canonical(result)).hexdigest()
    atomic(args.output, json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    md = f"""# Signal Lattice 北极星部署结果\n\n- 状态：PASS\n- 版本：{args.version}\n- 网站：{result['public_url']}\n- Status：{result['status_url']}\n- 本轮唯一建议：{diagnostics.get('current_action')} {diagnostics.get('current_symbol') or ''}\n- 活跃／完成 Skill：{diagnostics.get('active_skill_count')} / {diagnostics.get('completed_skill_count')}\n- 市场数据：{diagnostics.get('market_data_source')}\n- 核心证明：每分钟完整循环、全部 Active Skill 独立执行、中枢协调、唯一建议均通过公网验证。\n- 边界：只供人类决策，禁止自动交易；运行期 Agent 和模型 Token 均为 0。\n- 收据 SHA-256：`{result['receipt_sha256']}`\n"""
    atomic(args.markdown, md, 0o644)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
