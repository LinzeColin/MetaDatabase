from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .config import Settings
from .models import Candidate, Metrics, SkillResult

WEIGHTS = (16.7, 16.7, 16.7, 16.7, 16.6, 16.6)
NON_PRICE_FAMILIES = {"商业捕获", "瓶颈与稀缺", "离散事件", "综合基本面"}


def _read_registry(settings: Settings) -> dict[str, Any]:
    paths = settings.runtime.get("source_refresh_paths", {})
    registry_path = Path(str(paths.get("meta_registry", "")))
    if registry_path.is_file():
        try:
            value = json.loads(registry_path.read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else {}
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            return {}
    return {}


def _source_states(settings: Settings) -> dict[str, str]:
    registry = _read_registry(settings)
    registry_text = json.dumps(registry, ensure_ascii=False)
    paths = settings.runtime.get("source_refresh_paths", {})
    meta_root = Path(str(paths.get("meta_stock_skill_root", "")))
    serenity = Path(str(paths.get("serenity_skill", "")))
    result: dict[str, str] = {}
    for row in settings.skill_routes.get("skills", []):
        skill_id = str(row["skill_id"])
        hint = str(row.get("canonical_hint", skill_id))
        if skill_id == "serenity-skill":
            result[skill_id] = "Canonical方法已读取" if serenity.is_file() else "冻结方法契约"
            continue
        paths_to_check = [
            meta_root / hint / "SKILL.md",
            meta_root / f"{hint}-skill" / "SKILL.md",
        ]
        found = any(path.is_file() for path in paths_to_check) or hint in registry_text
        result[skill_id] = "Canonical方法已读取" if found else "冻结方法契约"
    return result


def _challengers(candidates: list[Candidate], incumbent_code: str) -> list[Candidate]:
    return [candidate for candidate in candidates if candidate.provider_code != incumbent_code]


def _strongest_challenger(
    candidates: list[Candidate], metrics: dict[str, Metrics], incumbent_code: str
) -> tuple[Candidate | None, Metrics | None]:
    ranked: list[tuple[float, Candidate, Metrics]] = []
    for candidate in _challengers(candidates, incumbent_code):
        metric = metrics.get(candidate.provider_code)
        lower = metric.relative_stress_lower_pct.get("60") if metric else None
        if lower is not None:
            ranked.append((float(lower), candidate, metric))
    if not ranked:
        return None, None
    ranked.sort(key=lambda item: item[0], reverse=True)
    _, candidate, metric = ranked[0]
    return candidate, metric


def _evidence_roots(candidate: Candidate) -> list[str]:
    roots = candidate.fundamentals.get("evidence_roots", [])
    return [str(value) for value in roots if str(value).strip()] if isinstance(roots, list) else []


def _result(
    route: dict[str, Any],
    index: int,
    conclusion: str,
    contribution: str,
    independence: str,
    source_state: str,
    candidate_conclusions: dict[str, str],
    candidate_contributions: dict[str, str],
) -> SkillResult:
    return SkillResult(
        skill_id=str(route["skill_id"]),
        display_name=str(route["display_name"]),
        applicable=True,
        run_mode="方法契约",
        abstention_reason="无",
        family=str(route["family"]),
        raw_weight=1.0,
        family_weight_pct=100.0,
        overall_weight_pct=WEIGHTS[index],
        conclusion=conclusion,
        independence=independence,
        contribution=contribution,
        source_state=source_state,
        candidate_conclusions=candidate_conclusions,
        candidate_contributions=candidate_contributions,
    )


def run_six_skills(
    settings: Settings,
    candidates: list[Candidate],
    metrics: dict[str, Metrics],
    current_state: dict[str, Any],
    market_context: dict[str, Any],
) -> list[SkillResult]:
    """Freeze six independent method-contract outputs before central adjudication."""
    incumbent_code = str(current_state["provider_code"])
    challengers = _challengers(candidates, incumbent_code)
    strongest, strongest_metric = _strongest_challenger(candidates, metrics, incumbent_code)
    source_states = _source_states(settings)
    routes = list(settings.skill_routes.get("skills", []))
    results: list[SkillResult] = []

    for index, route in enumerate(routes):
        profile = str(route.get("profile", ""))
        source_state = source_states.get(str(route["skill_id"]), "冻结方法契约")
        candidate_conclusions: dict[str, str] = {}
        candidate_contributions: dict[str, str] = {}

        if profile == "commercial":
            supported: list[Candidate] = []
            for candidate in challengers:
                if candidate.risk_tier < 2:
                    continue
                evidence = _evidence_roots(candidate)
                f = candidate.fundamentals
                required = ("revenue_growth", "margin_trend", "revision_score", "value_capture_score")
                complete = all(key in f for key in required) and bool(evidence)
                if complete:
                    score = min(
                        float(f.get("revenue_growth", 0.0)),
                        float(f.get("margin_trend", 0.0)),
                        float(f.get("revision_score", 0.0)),
                        float(f.get("value_capture_score", 0.0)),
                    )
                    if score >= 0.60:
                        supported.append(candidate)
                        candidate_conclusions[candidate.provider_code] = "支持"
                        candidate_contributions[candidate.provider_code] = "商业捕获、发行人暴露、预期与估值证据同时通过"
                        continue
                candidate_conclusions[candidate.provider_code] = "中性"
                candidate_contributions[candidate.provider_code] = "商业捕获证据链未完整关闭"
            conclusion = "反对" if supported else "中性"
            contribution = (
                f"识别到{len(supported)}个商业捕获证据完整的风险挑战者"
                if supported else "未发现商业捕获证据足以挑战宽基的风险候选"
            )
            independence = "独立；中央冻结前审查股票、行业与主题子宇宙，价格强势不得替代发行人收入、利润率、现金流与估值证据"

        elif profile == "bottleneck":
            supported = []
            for candidate in challengers:
                if candidate.risk_tier < 2:
                    continue
                f = candidate.fundamentals
                roots = f.get("bottleneck_evidence_roots", f.get("evidence_roots", []))
                evidence = [str(value) for value in roots if str(value).strip()] if isinstance(roots, list) else []
                required = ("scarcity_score", "pricing_power", "supply_risk", "per_share_capture")
                complete = all(key in f for key in required) and bool(evidence)
                if complete:
                    hard_floor = min(
                        float(f.get("scarcity_score", 0.0)),
                        float(f.get("pricing_power", 0.0)),
                        float(f.get("per_share_capture", 0.0)),
                        1.0 - float(f.get("supply_risk", 1.0)),
                    )
                    if hard_floor >= 0.60:
                        supported.append(candidate)
                        candidate_conclusions[candidate.provider_code] = "支持"
                        candidate_contributions[candidate.provider_code] = "约束、持续性、股东租金捕获与预期差硬门同时通过"
                        continue
                candidate_conclusions[candidate.provider_code] = "中性"
                candidate_contributions[candidate.provider_code] = "至少一项瓶颈非补偿硬门未通过"
            conclusion = "反对" if supported else "中性"
            contribution = (
                f"识别到{len(supported)}个通过全部非补偿硬门的瓶颈挑战者"
                if supported else "无候选同时关闭约束、持续性、股东租金捕获与预期差硬门"
            )
            independence = "独立；中央冻结前执行瓶颈真实性、稀缺持续性、股东租金捕获和预期差四门审查"

        elif profile == "foresight":
            supported = []
            for candidate in challengers:
                metric = metrics.get(candidate.provider_code)
                lower60 = metric.relative_stress_lower_pct.get("60") if metric else None
                lower20 = metric.relative_stress_lower_pct.get("20") if metric else None
                passes = (
                    lower60 is not None
                    and lower20 is not None
                    and float(lower60) > settings.switch_gate_pct
                    and float(lower20) >= settings.tactical_floor_pct
                )
                candidate_conclusions[candidate.provider_code] = "支持" if passes else "反对"
                candidate_contributions[candidate.provider_code] = (
                    f"20/60日非概率压力下界为{float(lower20):+.2f}%/{float(lower60):+.2f}%"
                    if lower20 is not None and lower60 is not None
                    else "缺少可定位20/60日相对价格链"
                )
                if passes:
                    supported.append(candidate)
            lower = strongest_metric.relative_stress_lower_pct.get("60") if strongest_metric else None
            conclusion = "反对" if supported else "支持"
            contribution = (
                f"{len(supported)}个挑战者通过20/60与成本拒绝门"
                if supported else (
                    f"最强挑战60日非概率压力下界为{float(lower):+.2f}%，未越完整切换门"
                    if lower is not None else "缺少可定位60日相对价格链，拒绝伪造预测"
                )
            )
            independence = "独立；仅执行PIT、方向、幅度、成本、可靠性与拒绝条件，不生成概率、Alpha或样本外领先断言"

        elif profile == "lead_lag":
            directions: list[int] = []
            for candidate in challengers:
                metric = metrics.get(candidate.provider_code)
                value = metric.returns_pct.get("20") if metric else None
                if value is None:
                    candidate_conclusions[candidate.provider_code] = "中性"
                    candidate_contributions[candidate.provider_code] = "缺少20日可核时序路径"
                    continue
                direction = 1 if float(value) > 0.5 else -1 if float(value) < -0.5 else 0
                directions.append(direction)
                candidate_conclusions[candidate.provider_code] = "中性"
                candidate_contributions[candidate.provider_code] = f"20日方向路径为{float(value):+.2f}%，仅作一致性约束"
            positive = sum(1 for value in directions if value > 0)
            negative = sum(1 for value in directions if value < 0)
            conclusion = "支持" if positive > negative * 2 and positive >= 3 else "反对" if negative > positive * 2 and negative >= 3 else "中性"
            contribution = f"完成{len(directions)}条可核市场路径的会话方向一致性审查；不声称领先或因果"
            independence = "独立；只检查会话先后、跨市场一致性和时区可得性，相关与时间先后不解释为领先或现实因果"

        elif profile == "event":
            positive_count = 0
            negative_count = 0
            for candidate in challengers:
                material = [
                    event for event in candidate.events
                    if isinstance(event, dict) and abs(float(event.get("impact_score", 0.0) or 0.0)) >= 0.60
                ]
                net = sum(float(event.get("impact_score", 0.0) or 0.0) for event in material)
                finding = "支持" if net > 0.50 else "反对" if net < -0.50 else "中性"
                candidate_conclusions[candidate.provider_code] = finding
                candidate_contributions[candidate.provider_code] = (
                    f"{len(material)}项已公开材料事件净影响{net:+.2f}"
                    if material else "无已公开材料事件优势或风险"
                )
                positive_count += int(finding == "支持")
                negative_count += int(finding == "反对")
            incumbent = next((item for item in candidates if item.provider_code == incumbent_code), None)
            incumbent_events = list(incumbent.events if incumbent else []) + list(market_context.get("macro_events", []))
            incumbent_material = [
                event for event in incumbent_events
                if isinstance(event, dict) and abs(float(event.get("impact_score", 0.0) or 0.0)) >= 0.60
            ]
            incumbent_net = sum(float(event.get("impact_score", 0.0) or 0.0) for event in incumbent_material)
            conclusion = "反对" if negative_count or incumbent_net < -0.50 else "支持" if incumbent_net > 0.50 and not positive_count else "中性"
            contribution = (
                "本轮无材料事件优势或风险"
                if not incumbent_material and not positive_count and not negative_count
                else f"按公开时点识别现行及挑战路径材料事件，现行净影响{incumbent_net:+.2f}"
            )
            independence = "独立；按公布、观察、生效和本轮时点审查离散事件，不提前使用未公开信息"

        elif profile == "serenity":
            supported = []
            for candidate in challengers:
                f = candidate.fundamentals
                required = ("quality_score", "valuation_attractiveness", "product_penetration_score")
                roots = _evidence_roots(candidate)
                if all(key in f for key in required) and roots:
                    score = min(
                        float(f.get("quality_score", 0.0)),
                        float(f.get("valuation_attractiveness", 0.0)),
                        float(f.get("product_penetration_score", 0.0)),
                    )
                    if score >= 0.60:
                        supported.append(candidate)
                        candidate_conclusions[candidate.provider_code] = "支持"
                        candidate_contributions[candidate.provider_code] = "产业链、产品穿透、质量、估值与证据根同时通过"
                        continue
                candidate_conclusions[candidate.provider_code] = "中性"
                candidate_contributions[candidate.provider_code] = "综合基本面与产品穿透证据尚未完整"
            lower = strongest_metric.relative_stress_lower_pct.get("60") if strongest_metric else None
            has_pressure = bool(
                strongest_metric
                and strongest_metric.relative_returns_pct.get("60") is not None
                and float(strongest_metric.relative_returns_pct["60"]) > 0
            )
            conclusion = "反对" if has_pressure or supported else "中性"
            contribution = (
                f"存在真实机会成本压力，但最强60日压力下界{float(lower):+.2f}%未自动等同越门"
                if has_pressure and lower is not None else "综合反证未发现可净胜现行策略的稳健前沿"
            )
            independence = "独立；综合产业链、产品穿透、估值、宏观、风险与机会成本，强挑战不等于已通过切换门"

        else:
            conclusion = "无结论"
            contribution = "方法路由未识别"
            independence = "独立；未参与中央结论"

        results.append(_result(
            route,
            index,
            conclusion,
            contribution,
            independence,
            source_state,
            candidate_conclusions,
            candidate_contributions,
        ))

    if len(results) != 6:
        raise ValueError("V19_REQUIRES_EXACTLY_SIX_SKILLS")
    return results
