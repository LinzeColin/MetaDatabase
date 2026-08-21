#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from zoneinfo import ZoneInfo

TOP_KEYS = [
    "运行时间", "提示词版本", "运行状态", "市场覆盖", "数据截止",
    "状态连续性", "裁决完整性", "技能适用覆盖率", "第一板块", "第二板块",
]
FIRST_KEYS = [
    "唯一操作", "唯一平台", "唯一标的", "代码", "唯一方向", "可观察回撤",
    "风险调整回撤", "剩余回撤预算", "预期研究窗口", "相对宽基", "相对现金",
    "现在怎么做", "核心依据", "最大反证", "失效条件", "下一正式复核",
]
SECOND_KEYS = [
    "矩阵", "适用技能", "实际参与", "适用覆盖率", "原生参与", "原生覆盖率",
    "中央定量审查", "权重说明",
]
SKILLS = [
    "股票商业机会拆解", "瓶颈宁静技能", "股势前瞻",
    "全球股市时序联动图谱", "股票事件航图", "宁静投研技能",
]
MATRIX_KEYS = [
    "技能", "适用状态", "运行方式", "弃权主原因", "方法家族",
    "原始权重", "家族内权重", "总体权重", "结论", "独立性",
]
SYDNEY = ZoneInfo("Australia/Sydney")
FIXTURE_SCOPE = "STRUCTURAL_FIXTURE_ONLY"
LIVE_SCOPE = "LIVE_PROVIDER_REVIEW_ONLY"
FIXTURE_PROVENANCE = "FIXTURE_DATA"
LIVE_PROVENANCE = "LIVE_MOOMOO_QUOTE"


def request(base: str, path: str, method: str = "GET", timeout: float = 12.0):
    req = urllib.request.Request(
        base.rstrip("/") + path,
        method=method,
        headers={"Accept": "application/json", "User-Agent": "Signal-Lattice-V19-Acceptance"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            body = response.read()
            return response.status, dict(response.headers), body
    except urllib.error.HTTPError as exc:
        return exc.code, dict(exc.headers), exc.read()


def json_get(base: str, path: str):
    status, _, body = request(base, path)
    if status != 200:
        raise AssertionError(f"{path} HTTP {status}: {body[:300]!r}")
    return json.loads(body.decode("utf-8"))


def parse_run_time(report: dict) -> datetime:
    return datetime.strptime(report["运行时间"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=SYDNEY)


def check_report(report: dict) -> None:
    assert list(report) == TOP_KEYS, f"REPORT_FIELD_ORDER:{list(report)}"
    assert report["提示词版本"] == "v0.0.0.19"
    assert report["运行状态"] in {"正常", "降级持有", "策略失效", "基线重试", "阻断"}
    assert report["市场覆盖"] in {"平台精确", "公共广泛", "最低可行", "阻断"}
    assert report["状态连续性"] in {"完整状态", "部分状态", "冲突状态", "首次建基线"}
    assert report["裁决完整性"] in {"原生完整", "方法完整", "降级裁决", "最低可行", "阻断"}
    first = report["第一板块"]
    second = report["第二板块"]
    assert list(first) == FIRST_KEYS, f"FIRST_FIELD_ORDER:{list(first)}"
    assert list(second) == SECOND_KEYS, f"SECOND_FIELD_ORDER:{list(second)}"
    assert first["唯一操作"] in {"买入", "持有", "切换至", "退出"}
    assert first["唯一平台"] in {"MooMooAU", "支付宝基金", "无"}
    assert first["唯一方向"] in {"看涨", "看跌", "防御", "退出"}
    if first["唯一操作"] != "退出":
        assert first["唯一标的"] not in {"", "无"}
        assert first["代码"] not in {"", "无"}
        assert not any(char in str(first["代码"]) for char in ",;/| "), "MULTIPLE_PUBLIC_CODES"
    rows = second["矩阵"]
    assert isinstance(rows, list) and len(rows) == 6
    assert [row.get("技能") for row in rows] == SKILLS
    for row in rows:
        assert list(row) == MATRIX_KEYS, f"MATRIX_FIELD_ORDER:{list(row)}"
        assert row["适用状态"] in {"适用", "不适用"}
        assert row["运行方式"] in {"原生运行", "方法契约", "弃权", "不适用"}
        assert row["结论"] in {"支持", "反对", "中性", "无结论"}
        if row["运行方式"] in {"方法契约", "原生运行"}:
            assert "本轮贡献" in str(row["独立性"]), f"NO_VISIBLE_CONTRIBUTION:{row['技能']}"
    rendered = json.dumps(report, ensure_ascii=False)
    assert "v0.0.0." + "20" not in rendered
    assert "V" + "20" not in rendered and "v" + "20" not in rendered
    assert "自动交易" not in first["现在怎么做"]
    parse_run_time(report)


def check_structural_oracle(report: dict) -> None:
    failures: list[str] = []
    if report["运行状态"] in {"阻断", "策略失效"}:
        failures.append(f"RUN_STATE:{report['运行状态']}")
    if report["市场覆盖"] in {"最低可行", "阻断"}:
        failures.append(f"MARKET_COVERAGE:{report['市场覆盖']}")
    if report["裁决完整性"] in {"最低可行", "阻断"}:
        failures.append(f"ADJUDICATION:{report['裁决完整性']}")
    if failures:
        raise AssertionError("STRUCTURAL_ORACLE_FAILED:" + ",".join(failures))


def check_input_provenance(metadata: dict, heartbeat: dict, require_live_provider: bool) -> str:
    fields = ("market_provider", "provider_state", "input_provenance", "acceptance_scope")
    for field in fields:
        assert field in metadata, f"METADATA_MISSING_{field.upper()}"
        assert field in heartbeat, f"HEARTBEAT_MISSING_{field.upper()}"
        assert metadata[field] == heartbeat[field], f"PROVENANCE_MISMATCH_{field.upper()}"

    provenance = metadata["input_provenance"]
    scope = metadata["acceptance_scope"]
    provider = metadata["market_provider"]
    provider_state = metadata["provider_state"]
    if provider == "fixture" and provider_state == "fixture" and provenance == FIXTURE_PROVENANCE and scope == FIXTURE_SCOPE:
        mode = "STRUCTURAL"
    elif provider == "moomoo" and provider_state == "live" and provenance == LIVE_PROVENANCE and scope == LIVE_SCOPE:
        mode = "LIVE_PROVIDER"
    else:
        raise AssertionError(
            "INPUT_PROVENANCE_UNACCEPTABLE:"
            f"provider={provider};state={provider_state};provenance={provenance};scope={scope}"
        )
    if require_live_provider and mode != "LIVE_PROVIDER":
        raise AssertionError(
            "LIVE_PROVIDER_REQUIRED:"
            f"provider={provider};state={provider_state};provenance={provenance};scope={scope}"
        )
    return mode


def check_stream(base: str) -> None:
    req = urllib.request.Request(
        base.rstrip("/") + "/api/v1/stream",
        headers={"Accept": "text/event-stream", "User-Agent": "Signal-Lattice-V19-Acceptance"},
    )
    with urllib.request.urlopen(req, timeout=8) as response:
        assert response.status == 200
        seen_event = False
        seen_data = False
        deadline = time.monotonic() + 6
        while time.monotonic() < deadline:
            line = response.readline().decode("utf-8", errors="replace").strip()
            if line == "event: report":
                seen_event = True
            if line.startswith("data: "):
                payload = json.loads(line[6:])
                check_report(payload)
                seen_data = True
                break
        assert seen_event and seen_data, "SSE_REPORT_NOT_RECEIVED"


def run(base: str, verify_cadence: bool, skip_stream: bool, require_live_provider: bool = False) -> dict:
    metadata = json_get(base, "/api/v1/metadata")
    assert metadata["version"] == "0.0.0.1.44"
    assert metadata["prompt_version"] == "v0.0.0.19"
    assert metadata["refresh_seconds"] == 15
    assert metadata["ui_heartbeat_seconds"] == 1
    assert metadata["automatic_trading"] is False
    assert metadata["shadow_only"] is True
    age = metadata.get("report_age_seconds")
    assert age is not None and float(age) <= 45.0, f"REPORT_STALE:{age}"

    heartbeat = json_get(base, "/api/v1/heartbeat")
    assert heartbeat["application_version"] == "0.0.0.1.44"
    assert heartbeat["decision_contract_version"] == "v0.0.0.19"
    assert heartbeat["ui_heartbeat_seconds"] == 1
    assert heartbeat["quote_observation_seconds"] == 15
    assert heartbeat["automatic_trading"] is False
    assert heartbeat["shadow_only"] is True
    assert heartbeat["profitability_status"] == "NOT_ISSUED"
    assert heartbeat["business_release_status"] == "NOT_ISSUED"
    assert heartbeat["decision_count"] >= 1
    assert heartbeat["observation_count"] >= heartbeat["decision_count"]

    whitebox = json_get(base, "/api/v1/whitebox/summary")
    assert whitebox["weight_mode"] == "SHADOW_ONLY"
    assert whitebox["profitability_status"] == "NOT_ISSUED"
    skills = json_get(base, "/api/v1/whitebox/skills")
    assert skills["mode"] == "SHADOW_ONLY"
    assert len(skills["items"]) == 6

    report1 = json_get(base, "/api/v1/report/latest")
    check_report(report1)
    check_structural_oracle(report1)
    acceptance_mode = check_input_provenance(metadata, heartbeat, require_live_provider)
    status, _, body = request(base, "/api/v1/report/latest.txt")
    assert status == 200 and "# 第一板块：唯一影子操作" in body.decode("utf-8")
    post_status, _, _ = request(base, "/api/v1/report/latest", method="POST")
    assert post_status == 405, f"WRITE_ENDPOINT_NOT_REJECTED:{post_status}"
    if not skip_stream:
        check_stream(base)

    cadence_seconds = None
    if verify_cadence:
        previous = report1
        previous_time = parse_run_time(previous)
        observed: list[float] = []
        changes = 0
        deadline = time.monotonic() + 55
        while time.monotonic() < deadline:
            time.sleep(2)
            current = json_get(base, "/api/v1/report/latest")
            if current["运行时间"] == previous["运行时间"]:
                continue
            check_report(current)
            current_time = parse_run_time(current)
            delta = (current_time - previous_time).total_seconds()
            observed.append(delta)
            previous = current
            previous_time = current_time
            changes += 1
            if changes < 2:
                continue
            if 12 <= delta <= 20:
                cadence_seconds = delta
                break
        assert cadence_seconds is not None, f"CADENCE_OUT_OF_RANGE:{observed}"

    state = "LIVE_PROVIDER_PASS_NOT_BUSINESS_RELEASE" if acceptance_mode == "LIVE_PROVIDER" else "STRUCTURAL_PASS"
    return {
        "state": state,
        "base_url": base,
        "version": metadata["version"],
        "prompt_version": metadata["prompt_version"],
        "refresh_seconds": metadata["refresh_seconds"],
        "current_code": report1["第一板块"]["代码"],
        "skill_rows": len(report1["第二板块"]["矩阵"]),
        "report_age_seconds": age,
        "decision_id": heartbeat["last_decision_id"],
        "observation_count": heartbeat["observation_count"],
        "decision_count": heartbeat["decision_count"],
        "observed_cadence_seconds": cadence_seconds,
        "market_provider": metadata["market_provider"],
        "provider_state": metadata["provider_state"],
        "input_provenance": metadata["input_provenance"],
        "acceptance_scope": metadata["acceptance_scope"],
        "business_release_status": "NOT_ISSUED",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--verify-cadence", action="store_true")
    parser.add_argument("--skip-stream", action="store_true")
    parser.add_argument("--require-live-provider", action="store_true")
    parser.add_argument("--output")
    args = parser.parse_args()
    try:
        result = run(args.base_url, args.verify_cadence, args.skip_stream, args.require_live_provider)
    except Exception as exc:
        result = {
            "state": "FAIL",
            "base_url": args.base_url,
            "error_type": type(exc).__name__,
            "error": str(exc),
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if args.output:
            with open(args.output, "w", encoding="utf-8") as handle:
                json.dump(result, handle, ensure_ascii=False, indent=2)
                handle.write("\n")
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if args.output:
        with open(args.output, "w", encoding="utf-8") as handle:
            json.dump(result, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
