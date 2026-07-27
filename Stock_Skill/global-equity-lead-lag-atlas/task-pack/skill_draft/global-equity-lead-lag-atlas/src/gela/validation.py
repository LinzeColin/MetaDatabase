from __future__ import annotations

import csv
import json
import re
from pathlib import Path
from typing import Any

from .render import REQUIRED_OUTPUTS

SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
EMBEDDED_DATA_PATTERN = re.compile(
    r'<script type="application/json" id="gela-data">(.*?)</script>', re.DOTALL
)


def _load_json(path: Path, errors: list[str]) -> Any | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        errors.append(f"{path.name} 无法解析: {exc}")
        return None


def _load_csv(path: Path, errors: list[str]) -> list[dict[str, str]]:
    try:
        with path.open("r", encoding="utf-8", newline="") as handle:
            return list(csv.DictReader(handle))
    except (OSError, UnicodeError, csv.Error) as exc:
        errors.append(f"{path.name} 无法解析: {exc}")
        return []


def _id_set(rows: list[dict[str, Any]], field: str, errors: list[str], label: str) -> set[str]:
    values: list[str] = []
    for row in rows:
        value = row.get(field)
        if not isinstance(value, str) or not value:
            errors.append(f"{label} 缺少 {field}")
            continue
        values.append(value)
    if len(values) != len(set(values)):
        errors.append(f"{label} 的 {field} 重复")
    return set(values)


def verify_output(path: Path) -> dict[str, object]:
    requested = Path(path)
    errors: list[str] = []
    if requested.is_symlink():
        return {
            "status": "FAIL",
            "path": str(requested),
            "missing": list(REQUIRED_OUTPUTS),
            "errors": ["输出目录不得是符号链接"],
        }
    output = requested.resolve()
    if not output.is_dir():
        return {"status": "FAIL", "path": str(output), "missing": list(REQUIRED_OUTPUTS), "errors": ["输出目录不存在"]}

    entries = list(output.rglob("*"))
    symlinks = [item.relative_to(output).as_posix() for item in entries if item.is_symlink()]
    if symlinks:
        errors.append("输出目录不得包含符号链接: " + ", ".join(symlinks))
    actual_files = {
        item.relative_to(output).as_posix()
        for item in entries
        if item.is_file() and not item.is_symlink()
    }
    nested_dirs = [item.relative_to(output).as_posix() for item in entries if item.is_dir() and not item.is_symlink()]
    missing = sorted(set(REQUIRED_OUTPUTS).difference(actual_files))
    unexpected = sorted(actual_files.difference(REQUIRED_OUTPUTS))
    if missing:
        errors.append("缺少输出: " + ", ".join(missing))
    if unexpected:
        errors.append("存在未声明输出: " + ", ".join(unexpected))
    if nested_dirs:
        errors.append("输出目录不得包含子目录: " + ", ".join(nested_dirs))
    for name in sorted(actual_files.intersection(REQUIRED_OUTPUTS)):
        if (output / name).stat().st_size == 0:
            errors.append(f"输出文件为空: {name}")

    analysis = _load_json(output / "analysis.json", errors) if (output / "analysis.json").is_file() else None
    quality = _load_json(output / "quality_report.json", errors) if (output / "quality_report.json").is_file() else None
    provenance = _load_json(output / "provenance.json", errors) if (output / "provenance.json").is_file() else None
    spec = _load_json(output / "visualization_spec.json", errors) if (output / "visualization_spec.json").is_file() else None

    co_movement: list[dict[str, Any]] = []
    confirmed_co: list[dict[str, Any]] = []
    hypotheses: list[dict[str, Any]] = []
    best: list[dict[str, Any]] = []
    confirmed_edges: list[dict[str, Any]] = []
    market_ids: list[str] = []
    horizons: set[int] = set()

    if not isinstance(analysis, dict):
        errors.append("analysis.json 根节点必须为 object")
    else:
        if analysis.get("schema_version") != "1.0":
            errors.append("analysis.json schema_version 不正确")
        skill = analysis.get("skill", {})
        if not isinstance(skill, dict) or skill.get("name") != "global-equity-lead-lag-atlas":
            errors.append("analysis.json Skill 身份不正确")
        boundary = analysis.get("claim_boundary", {})
        if not isinstance(boundary, dict) or boundary.get("causal_claims") is not False:
            errors.append("因果声明边界不正确")
        if isinstance(boundary, dict) and boundary.get("co_movement_alignment") != "same_session_date_trailing_return":
            errors.append("同期相关对齐声明缺失或不正确")

        markets = analysis.get("markets")
        if not isinstance(markets, list) or len(markets) < 2:
            errors.append("analysis.json 市场集合无效")
        else:
            market_ids = [str(item.get("market_id", "")) for item in markets if isinstance(item, dict)]
            if len(market_ids) != len(markets) or any(not value for value in market_ids) or len(set(market_ids)) != len(market_ids):
                errors.append("analysis.json 市场身份缺失或重复")
            for item in markets:
                if not isinstance(item, dict):
                    continue
                if item.get("instrument_type") != "cash_index":
                    errors.append("analysis.json 包含非 cash_index 市场")
                if item.get("return_type") not in {"price", "total_return", "net_total_return"}:
                    errors.append("analysis.json return_type 无效")
            if len({item.get("return_type") for item in markets if isinstance(item, dict)}) > 1:
                errors.append("analysis.json 混用了不同 return_type")

        collections = [
            analysis.get("co_movement"),
            analysis.get("confirmed_co_movements"),
            analysis.get("hypotheses"),
            analysis.get("best_candidates"),
            analysis.get("confirmed_edges"),
        ]
        if not all(isinstance(value, list) for value in collections):
            errors.append("analysis.json 关系集合类型不正确")
        else:
            co_movement, confirmed_co, hypotheses, best, confirmed_edges = collections  # type: ignore[assignment]
            co_ids = _id_set(co_movement, "pair_id", errors, "co_movement")
            confirmed_co_ids = _id_set(confirmed_co, "pair_id", errors, "confirmed_co_movements")
            hypothesis_ids = _id_set(hypotheses, "hypothesis_id", errors, "hypotheses")
            best_ids = _id_set(best, "hypothesis_id", errors, "best_candidates")
            edge_ids = _id_set(confirmed_edges, "hypothesis_id", errors, "confirmed_edges")
            if not confirmed_co_ids.issubset(co_ids):
                errors.append("confirmed_co_movements 不是 co_movement 子集")
            if not best_ids.issubset(hypothesis_ids):
                errors.append("best_candidates 不是 hypotheses 子集")
            if not edge_ids.issubset(best_ids):
                errors.append("confirmed_edges 不是 best_candidates 子集")
            if any(item.get("status") != "CONFIRMED" for item in confirmed_co):
                errors.append("confirmed_co_movements 含非确认结果")
            if any(item.get("status") != "CONFIRMED" for item in confirmed_edges):
                errors.append("confirmed_edges 含非确认结果")

            co_keys: set[tuple[str, str, int]] = set()
            for item in co_movement:
                try:
                    key = (str(item["market_a"]), str(item["market_b"]), int(item["horizon"]))
                    horizons.add(key[2])
                    if key[0] >= key[1]:
                        errors.append(f"同期相关市场顺序不规范: {key}")
                    if key in co_keys:
                        errors.append(f"同期相关重复: {key}")
                    co_keys.add(key)
                except (KeyError, TypeError, ValueError) as exc:
                    errors.append(f"同期相关字段不完整: {exc}")

            hypothesis_keys: set[tuple[str, str, int, int]] = set()
            best_keys: set[tuple[str, str, int]] = set()
            for item in hypotheses:
                try:
                    key = (
                        str(item["source_market"]), str(item["target_market"]),
                        int(item["horizon"]), int(item["source_lag"]),
                    )
                    if key[0] == key[1] or key in hypothesis_keys:
                        errors.append(f"时延假设身份无效或重复: {key}")
                    hypothesis_keys.add(key)
                except (KeyError, TypeError, ValueError) as exc:
                    errors.append(f"时延假设字段不完整: {exc}")
            for item in best:
                try:
                    key = (str(item["source_market"]), str(item["target_market"]), int(item["horizon"]))
                    if key in best_keys:
                        errors.append(f"最佳候选重复: {key}")
                    best_keys.add(key)
                except (KeyError, TypeError, ValueError) as exc:
                    errors.append(f"最佳候选字段不完整: {exc}")

            counts = analysis.get("counts", {})
            expected = {
                "markets": len(market_ids),
                "co_movement_hypotheses": len(co_movement),
                "confirmed_co_movements": len(confirmed_co),
                "hypotheses": len(hypotheses),
                "lead_lag_hypotheses": len(hypotheses),
                "confirmed_edges": len(confirmed_edges),
                "confirmed_lead_lag_edges": len(confirmed_edges),
            }
            if not isinstance(counts, dict):
                errors.append("analysis.json counts 类型不正确")
            else:
                for key, value in expected.items():
                    if counts.get(key) != value:
                        errors.append(f"计数不一致: {key}")

    analysis_id = analysis.get("analysis_id") if isinstance(analysis, dict) else None
    for label, item in (("quality_report.json", quality), ("provenance.json", provenance)):
        if isinstance(item, dict):
            if item.get("schema_version") != "1.0":
                errors.append(f"{label} schema_version 不正确")
            if item.get("analysis_id") != analysis_id:
                errors.append(f"{label} analysis_id 与 analysis.json 不一致")
    if isinstance(quality, dict):
        if quality.get("status") not in {"PASS", "PASS_WITH_WARNINGS"}:
            errors.append("quality_report.json 状态不允许")
        checks = quality.get("checks", {})
        required_checks = {
            "minimum_two_markets", "strict_utc_session_order", "unique_market_session",
            "positive_close", "cash_index_only", "single_return_type",
            "source_retrieval_not_before_close", "co_movement_alignment_declared",
            "causal_claims_disabled", "license_acknowledgement",
        }
        if not isinstance(checks, dict) or any(checks.get(key) is not True for key in required_checks):
            errors.append("quality_report.json 硬检查不完整")
    if isinstance(provenance, dict):
        for key in ("input_sha256", "config_sha256"):
            if not SHA256_PATTERN.fullmatch(str(provenance.get(key, ""))):
                errors.append(f"provenance 哈希不正确: {key}")
    if isinstance(spec, dict):
        if spec.get("schema_version") != "1.0":
            errors.append("visualization_spec.json schema_version 不正确")
        filters = set(spec.get("filters", []))
        if not {"mode", "horizon", "status"}.issubset(filters):
            errors.append("visualization_spec.json 缺少双视图过滤器")
        if spec.get("offline") is not True or spec.get("external_assets") != []:
            errors.append("visualization_spec.json 离线边界不正确")

    csv_specs = (
        ("co_movement.csv", "pair_id", {str(item.get("pair_id", "")) for item in co_movement}),
        ("hypotheses.csv", "hypothesis_id", {str(item.get("hypothesis_id", "")) for item in hypotheses}),
        ("matrix.csv", "hypothesis_id", {str(item.get("hypothesis_id", "")) for item in best}),
        ("edges.csv", "hypothesis_id", {str(item.get("hypothesis_id", "")) for item in confirmed_edges}),
    )
    for filename, id_field, expected_ids in csv_specs:
        if not (output / filename).is_file():
            continue
        rows = _load_csv(output / filename, errors)
        actual_ids = [row.get(id_field, "") for row in rows]
        if len(actual_ids) != len(set(actual_ids)) or set(actual_ids) != expected_ids:
            errors.append(f"{filename} 与 analysis.json 身份集合不一致")
        if filename == "edges.csv" and any(row.get("status") != "CONFIRMED" for row in rows):
            errors.append("edges.csv 含非确认结果")

    if (output / "correlation_matrix.csv").is_file():
        matrix_rows = _load_csv(output / "correlation_matrix.csv", errors)
        if matrix_rows:
            required_columns = {"horizon", "market_id", *market_ids}
            if not required_columns.issubset(matrix_rows[0]):
                errors.append("correlation_matrix.csv 字段不完整")
            if len(matrix_rows) != len(market_ids) * len(horizons):
                errors.append("correlation_matrix.csv 行数不正确")

    summary_path = output / "summary.md"
    if summary_path.is_file():
        try:
            summary = summary_path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            errors.append(f"summary.md 无法读取: {exc}")
        else:
            for fragment in ("同期相关", "时延", "不等于现实因果", "不构成投资建议"):
                if fragment not in summary:
                    errors.append(f"summary.md 缺少解释边界: {fragment}")

    html_path = output / "atlas.html"
    if html_path.is_file():
        try:
            text = html_path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            errors.append(f"atlas.html 无法读取: {exc}")
        else:
            required_fragments = (
                '<script type="application/json" id="gela-data">',
                'value="lead_lag"', 'value="co_movement"', "同期相关", "时延方向",
                "不代表现实因果",
            )
            for fragment in required_fragments:
                if fragment not in text:
                    errors.append(f"atlas.html 缺少片段: {fragment}")
            if any(token in text.lower() for token in ("https://", "http://", "cdn.")):
                errors.append("atlas.html 包含外部网络依赖")
            match = EMBEDDED_DATA_PATTERN.search(text)
            if match is None:
                errors.append("atlas.html 缺少嵌入数据")
            else:
                try:
                    embedded = json.loads(match.group(1))
                except json.JSONDecodeError as exc:
                    errors.append(f"atlas.html 嵌入数据无法解析: {exc}")
                else:
                    if embedded != analysis:
                        errors.append("atlas.html 嵌入数据与 analysis.json 不一致")

    return {
        "status": "PASS" if not errors else "FAIL",
        "path": str(output),
        "missing": missing,
        "errors": errors,
    }
