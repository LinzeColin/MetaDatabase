"""把 10-K/10-Q 正文抽取（evidence/structure_text.py）接进瓶颈分支的因子，按 scoring_model.md 的 0-5 锚点。

规则（每一条都写在参数里或这里，不悄悄发生）：
- 只有「方向明确 + 原文带数字」的抽取才能把因子拉到 3 分及以上；方向 AMBIGUOUS 的抽取不计分、不计风险，只留在证据里；
- 公司依赖上游单一来源（UPSTREAM）是风险，不是瓶颈优势：它只会进入投资性维度的 technology_resilience（越低越差），
  绝不进入 supplier_concentration / expansion_lead_time / qualification_barrier 这些「约束真实」因子；
- 扫描过但没抽到 = NO_EVIDENCE，不记 0 分（申报正文没写数字不等于约束不存在，也不等于约束存在）；
- 每个入分的抽取都带 EvidenceRef：SEC 原文链接 + accession + 原句（放进 label）。
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from ..evidence.structure_text import (AMBIGUOUS, OWNER, RISK, UPSTREAM, Extraction, FilingExtraction)
from .scoring_support import (KIND_TEXT, EvidenceRef, FactorResult, dedupe_refs, no_evidence, table_rating)

Hit = Tuple[FilingExtraction, Extraction]


class StructureEvidence:
    """一家公司的结构性抽取：最新 10-K 与（更新的）10-Q，各一份 FilingExtraction。"""

    def __init__(self, filings: Sequence[FilingExtraction]) -> None:
        self.filings: Tuple[FilingExtraction, ...] = tuple(filings)

    @property
    def latest_filed(self) -> Optional[str]:
        return max((f.filed for f in self.filings), default=None)

    def hits(self, kind: str, direction: Optional[str] = None) -> List[Hit]:
        return [(f, i) for f in self.filings for i in f.items if i.kind == kind and (direction is None or i.direction == direction)]

    def counts(self) -> Dict[str, Dict[str, int]]:
        table: Dict[str, Dict[str, int]] = {}
        for filing in self.filings:
            for kind, by_dir in filing.counts().items():
                for direction, n in by_dir.items():
                    table.setdefault(kind, {})
                    table[kind][direction] = table[kind].get(direction, 0) + n
        return table

    def to_dict(self) -> dict:
        return {"filings": [{"accession": f.accession, "form": f.form, "filed": f.filed, "url": f.url,
                             "chars": f.chars, "version": f.version} for f in self.filings],
                "counts": self.counts()}


def ref_for(filing: FilingExtraction, item: Extraction, what: str) -> EvidenceRef:
    snippet = item.sentence if len(item.sentence) <= 200 else item.sentence[:200] + "..."
    return EvidenceRef(kind=KIND_TEXT, label="%s [%s] %s %s: %s" % (what, item.direction, filing.form, filing.filed, snippet),
                       value=item.value, accession=filing.accession, form=filing.form, filed=filing.filed,
                       period_end=filing.period_end, url=filing.url)


_YEAR = re.compile(r"\b(20\d\d)\b")


def _latest_year(sentence: str) -> int:
    years = [int(y) for y in _YEAR.findall(sentence)]
    return max(years) if years else 0


def _most_recent_then_largest(hits: Sequence[Hit]) -> Hit:
    """同一类披露常把好几年放在一起（「2023 年一家供应商占 27%……2025 年两家分别 12%、11%」）：先取句子里年份最新的，再取数值最大的，
    不拿过期的高值冒充当前状态。"""
    newest = max((_latest_year(h[1].sentence), h[0].filed) for h in hits)
    pool = [h for h in hits if (_latest_year(h[1].sentence), h[0].filed) == newest]
    return max(pool, key=lambda h: h[1].value or 0.0)


def _best_numeric(hits: Sequence[Hit]) -> Optional[Hit]:
    numeric = [h for h in hits if h[1].value is not None]
    return max(numeric, key=lambda h: (h[1].value, h[0].filed)) if numeric else None


def _ambiguous_note(structure: StructureEvidence, kind: str) -> str:
    amb = len(structure.hits(kind, AMBIGUOUS))
    up = len(structure.hits(kind, UPSTREAM))
    parts = []
    if amb:
        parts.append("%d 处方向不明（不计分）" % amb)
    if up:
        parts.append("%d 处判为上游依赖（进风险，不加分）" % up)
    return ("；" + "，".join(parts)) if parts else ""


# ---- 结构性约束维度 ---------------------------------------------------------------------
def expansion_lead_time(structure: StructureEvidence, p: dict) -> FactorResult:
    """交期（客户等多久）代理「扩产要多久」：只认 OWNER 方向且带数字（≥3 分必须有数字）。"""
    table = p["tables"]["expansion_lead_time_months"]
    best = _best_numeric(structure.hits("lead_time", OWNER))
    if best is None:
        return no_evidence("expansion_lead_time", "10-K/10-Q 正文没有方向明确、带数字的交期表述" + _ambiguous_note(structure, "lead_time"))
    filing, item = best
    return FactorResult("expansion_lead_time", table_rating(item.value, table),
                        "PROXY 自家产品交期约 %.1f 个月（原文：%s）" % (item.value, item.sentence[:160]),
                        (ref_for(filing, item, "lead_time"),), "PROXY", item.value)


def supplier_concentration(structure: StructureEvidence, p: dict) -> FactorResult:
    """供给集中度：公司自己是唯一/少数供应商（OWNER）才算；上游单一来源是风险，不在这里。"""
    cfg = p["structure_text"]
    owner = structure.hits("sole_source", OWNER)
    if not owner:
        return no_evidence("supplier_concentration", "正文没有「我们是唯一/少数供应商」的明确自称" + _ambiguous_note(structure, "sole_source"))
    filing, item = owner[0]
    return FactorResult("supplier_concentration", float(cfg["owner_sole_source_rating"]),
                        "公司自述为唯一/少数供应商（只是自述，最高 %d）：%s" % (cfg["owner_sole_source_rating"], item.sentence[:160]),
                        (ref_for(filing, item, "sole_source"),), "OBSERVED", None)


def qualification_barrier(structure: StructureEvidence, p: dict) -> FactorResult:
    """认证/资格周期：OWNER 方向（客户换供应商要 N 个月）且带数字才计分。"""
    table = p["tables"]["qualification_months"]
    best = _best_numeric(structure.hits("qualification", OWNER))
    if best is None:
        return no_evidence("qualification_barrier", "正文没有方向明确、带数字的认证周期表述" + _ambiguous_note(structure, "qualification"))
    filing, item = best
    return FactorResult("qualification_barrier", table_rating(item.value, table),
                        "认证/资格周期约 %.1f 个月（原文：%s）" % (item.value, item.sentence[:160]),
                        (ref_for(filing, item, "qualification"),), "OBSERVED", item.value)


def owner_tightness(structure: StructureEvidence, p: dict) -> Optional[Tuple[str, float, str, Tuple[EvidenceRef, ...]]]:
    """current_tightness 的原文佐证（只认 OWNER）：返回 (证据类型, 文字上限, 说明, refs)。
    带利用率数字且 ≥ utilization_min_pct：文字上限 3；其余方向明确的产能受限表述：上限 marker_cap_rating。"""
    cfg = p["structure_text"]
    hits = structure.hits("capacity_constraint", OWNER)
    if not hits:
        return None
    numeric = [h for h in hits if h[1].value is not None and h[1].value >= cfg["utilization_min_pct"]]
    if numeric:
        filing, item = max(numeric, key=lambda h: h[1].value)
        return ("utilization", float(cfg["utilization_text_only_rating"]),
                "原文产能利用率 %.0f%%：%s" % (item.value, item.sentence[:140]), (ref_for(filing, item, "capacity_constraint"),))
    filing, item = hits[0]
    return ("marker", float(p["text_markers"]["marker_cap_rating"]),
            "原文自称产能受限（无数字，只作标记）：%s" % item.sentence[:140], (ref_for(filing, item, "capacity_constraint"),))


def backlog_demand(structure: StructureEvidence, f: Any, p: dict) -> Optional[Tuple[float, str, Tuple[EvidenceRef, ...], float]]:
    """没有 XBRL RPO 时，用正文里的积压订单金额补 funded_demand：覆盖月数（积压 / 月均营收）定档，
    带对比期数值时用同比走 RPO 同比表。基数微小（覆盖不足 rpo.min_months）的不作证据。"""
    if not f.revenue_ttm.ok or f.revenue_ttm.value <= 0:
        return None
    hits = [h for h in structure.hits("backlog", OWNER) if h[1].value]
    if not hits:
        return None
    filing, item = max(hits, key=lambda h: (h[0].filed, h[1].value))
    months = item.value / (f.revenue_ttm.value / 12.0)
    if months < p["rpo"]["min_months_as_demand_evidence"]:
        return None
    if item.value_low and item.value_low > 0:
        yoy = item.value / item.value_low - 1.0
        rating = min(table_rating(yoy, p["tables"]["funded_demand_rpo_yoy"]), float(p["structure_text"]["backlog_yoy_cap_rating"]))
        basis = "原文积压 $%.1fM，对比期 $%.1fM，同比 %+.1f%%（覆盖 %.1f 个月营收）" % (item.value / 1e6, item.value_low / 1e6, yoy * 100, months)
    else:
        rating = table_rating(months, p["tables"]["funded_demand_backlog_months"])
        basis = "原文积压 $%.1fM，覆盖 %.1f 个月营收（无对比期，最高 3）" % (item.value / 1e6, months)
    return rating, basis, (ref_for(filing, item, "backlog"),), item.value


# ---- 投资性维度（风险方向）--------------------------------------------------------------
def customer_diversification(structure: StructureEvidence, p: dict) -> FactorResult:
    """客户集中度：单一客户占营收的最大百分比。「没有客户 ≥10%」的原文自述记为 0（对应最高档 4）。"""
    table = p["tables"]["customer_top_share_pct"]
    hits = [h for h in structure.hits("customer_concentration", RISK) if h[1].detail.get("scope") in ("single", "none_over_10pct")]
    if not hits:
        tops = [h for h in structure.hits("customer_concentration", RISK) if h[1].detail.get("scope") in ("top_n", "multi")]
        note = "；有多个客户合计占比但没有单一客户占比（不计分）" if tops else ""
        return no_evidence("customer_diversification", "正文没有单一客户占营收比例的披露" + note)
    concentrated = [h for h in hits if h[1].detail.get("scope") == "single"]
    filing, item = (_most_recent_then_largest(concentrated) if concentrated else max(hits, key=lambda h: h[0].filed))
    return FactorResult("customer_diversification", table_rating(item.value, table),
                        ("最大单一客户占营收 %.1f%%：%s" % (item.value, item.sentence[:160])) if concentrated
                        else ("原文称没有单一客户占营收 ≥10%%：%s" % item.sentence[:160]),
                        (ref_for(filing, item, "customer_concentration"),), "OBSERVED", item.value)


def upstream_dependency_risk(structure: StructureEvidence, p: dict) -> FactorResult:
    """公司依赖上游单一来源 / 单一供应商采购占比高：这是风险。只有出现具体的风险信号才给偏低评分；
    没有信号（含「某供应商只占采购 11%」这种低占比披露）= NO_EVIDENCE：没写风险不等于没有风险，也不给「抗风险」加分。"""
    cfg = p["structure_text"]
    sole = structure.hits("sole_source", UPSTREAM)
    shares = [h for h in structure.hits("purchase_share", UPSTREAM) if h[1].value is not None]
    # 上游「供应链中断」「component shortages」是几乎每家都有的风险因素套话，不算具体披露；只认带数字的上游交期
    supply_only = [h for h in structure.hits("lead_time", UPSTREAM) if h[1].value is not None]
    refs: List[EvidenceRef] = []
    candidates: List[float] = []
    notes: List[str] = []
    if supply_only:
        filing, item = supply_only[0]
        candidates.append(float(cfg["upstream_supply_only_rating"]))
        notes.append("上游交期 %.1f 个月：%s" % (item.value, item.sentence[:140]))
        refs.append(ref_for(filing, item, "lead_time"))
    if sole:
        filing, item = sole[0]
        candidates.append(float(cfg["upstream_sole_source_rating"]))
        notes.append("依赖上游单一来源 %d 处：%s" % (len(sole), item.sentence[:140]))
        refs.append(ref_for(filing, item, "sole_source"))
    firm = [h for h in shares if not h[1].detail.get("lower_bound")]
    if firm:
        filing, item = _most_recent_then_largest(firm)
        if item.value >= cfg["upstream_share_high_pct"]:
            candidates.append(float(cfg["upstream_share_high_rating"]))
        elif item.value >= cfg["upstream_share_mid_pct"]:
            candidates.append(float(cfg["upstream_share_mid_rating"]))
        notes.append("单一供应商占采购 %.0f%%：%s" % (item.value, item.sentence[:140]))
        refs.append(ref_for(filing, item, "purchase_share"))
    if not candidates:
        return no_evidence("technology_resilience", "正文没有上游单一来源、高占比采购或上游交期数字的披露（不给抗风险加分）"
                           + ("；只披露了低占比供应商：" + notes[0] if notes else ""))
    return FactorResult("technology_resilience", min(candidates), "PROXY 供应链单点依赖（风险，越低越差）：" + "；".join(notes),
                        dedupe_refs(refs), "PROXY", None)


def structural_risks(structure: StructureEvidence) -> List[dict]:
    """给收据用：上游依赖风险清单（原句 + 链接），不进任何加分因子。"""
    out = []
    for kind in ("sole_source", "purchase_share", "lead_time", "capacity_constraint"):
        for filing, item in structure.hits(kind, UPSTREAM)[:2]:
            out.append({"kind": kind, "value": item.value, "sentence": item.sentence, "accession": filing.accession,
                        "url": filing.url, "filed": filing.filed})
    return out


def summary(structure: StructureEvidence) -> dict:
    payload = structure.to_dict()
    payload["risks"] = structural_risks(structure)
    return payload
