"""分支卡片上的「一句话说明」：全部取自研究层产物（收据里的原因、逐股结论里的原因、分支自己报的元数据），

不按分支写死结论。同一份代码对任何一轮产物都成立：本轮换了结果，这句话跟着换。
只做「翻译」：把机器码翻成人话；翻不出来的原样保留，不猜。
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Any, Dict, List, Mapping, Optional

# 机器码 -> 人话。只放研究层真的会产出的码；没收录的原样显示。
REASON_TEXT = {
    "DECISION_SCORE_BELOW_REJECT": "综合分低于淘汰线",
    "DECISION_SCORE_BELOW_SCREEN_FLAG": "综合分不到筛选线",
    "MATURITY_BELOW_E4": "证据成熟度没到 E4（催化剂只是估计、没有已确认的）",
    "BASE_REQUIRED_DIMENSION_NO_EVIDENCE": "必需的基础维度拿不到证据",
    "BASE_COVERAGE_BELOW_FLOOR": "基础维度的证据覆盖率不够",
    "CONFIDENCE_BELOW_MIN": "置信度不够",
    "HARD_FLAG:no_material_revenue_bridge": "拿不到营收/现金流证据，说不清这条瓶颈对收入有多大影响",
    "HARD_FLAG:no_primary_evidence": "缺少一手证据",
    "HARD_FLAG:unfunded_financing_gap": "有没落实的融资缺口",
    "DIMENSION_UNVERIFIABLE:constraint": "「约束是否真实」这一维没有足够证据",
    "DIMENSION_UNVERIFIABLE:capture": "「股东能否分到钱」这一维没有足够证据",
    "DIMENSION_UNVERIFIABLE:mispricing": "「市场是否还没定价」这一维没有足够证据",
    "DIMENSION_UNVERIFIABLE:investability": "「是否可投资」这一维没有足够证据",
    "EVIDENCE_BELOW_MIN": "证据总量不够",
    "GATE_C_CAPTURE_BELOW_MIN": "「股东能分到钱」这道门没过",
    "GATE_D_MISPRICING_BELOW_MIN": "「市场还没定价」这道门没过",
    "INVESTABILITY_BELOW_MIN": "可投资性不够",
}
FACTOR_TEXT = {
    "funded_demand": "有资金支撑的需求", "architectural_necessity": "架构必需性", "current_tightness": "当前紧缺程度",
    "supplier_concentration": "供应商集中度", "expansion_lead_time": "扩产交期", "qualification_barrier": "认证壁垒",
    "substitution_difficulty": "替代难度", "policy_resilience": "政策韧性",
}
NO_EVIDENCE_RATE_FLOOR = 0.90


def _reason_key(reason: str) -> str:
    """把一条原因归到一个可计数的键：机器码取前缀（保留 HARD_FLAG/DIMENSION 的子类），中文原因取第一句。"""
    text = str(reason).strip()
    if re.match(r"MATURITY_E\d_BELOW_E4", text):
        return "MATURITY_BELOW_E4"
    if text.startswith(("HARD_FLAG:", "DIMENSION_UNVERIFIABLE:")):
        head, _, rest = text.partition(":")
        return "%s:%s" % (head, re.split(r"[:(<>=]", rest)[0])
    if re.match(r"^[A-Z0-9_]+([:(<>=]|$)", text):
        return re.split(r"[:(<>=]", text)[0]
    return re.split(r"[。：:]", text)[0][:40]


def _top_reasons(verdicts: Mapping[str, Mapping], limit: int = 2) -> List[str]:
    counts: Counter = Counter()
    for record in verdicts.values():
        if record.get("verdict") == "PASS":
            continue
        keys = {_reason_key(r) for r in (record.get("reasons") or [])}
        keys.discard("STATUS")
        keys.discard("BRANCH_ABSTAIN")
        counts.update(keys)
    return ["%s，%d 家" % (REASON_TEXT.get(key, key), n) for key, n in counts.most_common(limit)]


def _receipt_reason_text(reason: str) -> str:
    matched = re.match(r"OOS_BRIER_NOT_BETTER_THAN_BASE_RATE:full_model=([\d.]+)>=const=([\d.]+)", reason or "")
    if matched:
        return "样本外预测力不如常数基准（预测误差 Brier：模型 %.3f，常数基准 %.3f，越低越好），整分支弃权" % (float(matched.group(1)), float(matched.group(2)))
    return "整分支弃权：%s" % reason


def _constraint_gap(meta: Mapping[str, Any]) -> Optional[str]:
    rates = ((meta or {}).get("factor_no_evidence") or {}).get("constraint") or {}
    missing = sorted(((name, rate) for name, rate in rates.items() if isinstance(rate, (int, float)) and rate >= NO_EVIDENCE_RATE_FLOOR),
                     key=lambda item: -item[1])
    if len(missing) < 3:
        return None
    floor = min(rate for _, rate in missing)
    names = "、".join(FACTOR_TEXT.get(name, name) for name, _ in missing[:6])
    return ("「约束是否真实」这道门要看的 %d 个因子里有 %d 个（%s）在 %d%% 以上的公司申报里拿不到证据——行业交期、产能这类数据免费申报里几乎没有" % (
        len(rates), len(missing), names, int(floor * 100)))


def describe(branch_id: str, receipt: Mapping[str, Any], verdicts: Mapping[str, Mapping], meta: Optional[Mapping[str, Any]] = None) -> str:
    """一句话：这个分支本轮为什么是这个样子。"""
    status = receipt.get("status")
    if receipt.get("reason") and status != "PASS":
        return _receipt_reason_text(receipt["reason"])
    if branch_id == "global-equity-lead-lag-atlas":
        note = (meta or {}).get("note") or "只作市场环境输入，不选股"
        return "%s（本轮环境：%s）" % (note, (meta or {}).get("regime") or "—")
    counts = receipt.get("verdict_counts") or {}
    passed = int(counts.get("PASS") or 0)
    if passed == 0:
        gap = _constraint_gap(meta or {})
        if gap:
            return "本轮 0 家通过：%s。" % gap
        top = _top_reasons(verdicts)
        return "本轮 0 家通过。最常见的卡点：%s。" % "；".join(top) if top else "本轮 0 家通过。"
    top = _top_reasons(verdicts)
    return ("本轮 %d 家通过。其余最常见的原因：%s。" % (passed, "；".join(top))) if top else "本轮 %d 家通过。" % passed
