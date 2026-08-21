from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class Candidate:
    provider_code: str
    public_code: str
    name: str
    market: str
    currency: str
    bucket_id: str
    bucket_name: str
    risk_tier: int
    platform_verified: bool = False
    price: float | None = None
    quote_time: str | None = None
    bars: list[dict[str, Any]] = field(default_factory=list)
    fundamentals: dict[str, Any] = field(default_factory=dict)
    events: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    liquidity_score: float = 0.0
    cost_bps: float = 10.0
    inverse: bool = False
    leveraged: bool = False
    path_dependency_verified: bool = False
    discovery_source: str = "fallback"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "Candidate":
        fields = {name for name in cls.__dataclass_fields__}
        return cls(**{key: value[key] for key in value if key in fields})


@dataclass
class Metrics:
    provider_code: str
    returns_pct: dict[str, float | None]
    volatility_pct: dict[str, float | None]
    max_drawdown_pct: dict[str, float | None]
    relative_returns_pct: dict[str, float | None] = field(default_factory=dict)
    relative_stress_lower_pct: dict[str, float | None] = field(default_factory=dict)
    data_points: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SkillResult:
    skill_id: str
    display_name: str
    applicable: bool
    run_mode: str
    abstention_reason: str
    family: str
    raw_weight: float
    family_weight_pct: float
    overall_weight_pct: float
    conclusion: str
    independence: str
    contribution: str
    source_state: str
    candidate_conclusions: dict[str, str] = field(default_factory=dict)
    candidate_contributions: dict[str, str] = field(default_factory=dict)
    method_version: str = "UNSPECIFIED"
    method_evidence: str = "UNSPECIFIED"

    def to_public_row(self) -> dict[str, Any]:
        detail = self.independence.rstrip("。")
        detail = f"{detail}；方法版本：{self.method_version}；方法证据：{self.method_evidence}"
        contribution = self.contribution.strip()
        if contribution:
            detail = f"{detail}；本轮贡献：{contribution}。"
        else:
            detail = f"{detail}。"
        return {
            "技能": self.display_name,
            "适用状态": "适用" if self.applicable else "不适用",
            "运行方式": self.run_mode,
            "弃权主原因": self.abstention_reason,
            "方法家族": self.family,
            "原始权重": self.raw_weight,
            "家族内权重": f"{self.family_weight_pct:.1f}%",
            "总体权重": f"{self.overall_weight_pct:.1f}%",
            "结论": self.conclusion,
            "独立性": detail,
        }

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
