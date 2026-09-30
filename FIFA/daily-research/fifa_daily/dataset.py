"""把抓到的原始比赛整理成模型输入：球队键归一、所属联赛、去重。"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field

from . import config
from .model import OTHER_GROUP, TrainMatch
from .teams import Registry

DISPLAY_OVERRIDE = {"athen": "AEK Athens", "bayern munchen": "Bayern Munich", "internazionale milano": "Inter Milan",
                    "psv": "PSV Eindhoven", "racing lens": "Lens", "lille osc": "Lille"}


@dataclass
class Dataset:
    registry: Registry
    matches: list[dict]                 # 全部（含 hk/ak 球队键），已去重
    played: list[TrainMatch]
    team_group: dict[str, str]
    team_leagues: dict[str, dict[str, str]] = field(default_factory=dict)  # 球队 -> {赛季: 联赛}

    def name(self, k: str) -> str:
        return DISPLAY_OVERRIDE.get(k) or self.registry.display(k)

    def zh(self, k: str) -> str | None:
        return self.registry.zh(k)


def team_groups(matches: list[dict], before: str | None = None) -> tuple[dict[str, str], dict[str, dict[str, str]]]:
    """球队 -> 所属联赛（取最近一个有国内联赛记录的赛季）。before 用于回测：只看该日期之前的比赛。"""
    per_team: dict[str, dict[str, Counter]] = defaultdict(lambda: defaultdict(Counter))
    for m in matches:
        if m["comp"] == "uefa.cl" or (before and m["date"] >= before):
            continue
        for k in (m["hk"], m["ak"]):
            per_team[k][m["season"]][m["comp"]] += 1
    groups: dict[str, str] = {}
    leagues: dict[str, dict[str, str]] = {}
    for k, by_season in per_team.items():
        leagues[k] = {s: c.most_common(1)[0][0] for s, c in by_season.items()}
        groups[k] = by_season[max(by_season)].most_common(1)[0][0]
    return groups, leagues


def prepare(raw: list[dict]) -> Dataset:
    reg = Registry()
    seen: set[tuple] = set()
    matches: list[dict] = []
    for m in raw:
        hk, ak = reg.add(m["home"]), reg.add(m["away"])
        sig = (m["comp"], m["date"], hk, ak)
        if sig in seen:
            continue
        seen.add(sig)
        matches.append({**m, "hk": hk, "ak": ak})

    team_group, team_leagues = team_groups(matches)

    played = [TrainMatch(date=m["date"], comp=m["comp"], home=m["hk"], away=m["ak"], hg=m["hg"], ag=m["ag"])
              for m in matches if m["hg"] is not None]
    for m in matches:
        for k in (m["hk"], m["ak"]):
            team_group.setdefault(k, OTHER_GROUP)
    return Dataset(reg, matches, played, team_group, team_leagues)
