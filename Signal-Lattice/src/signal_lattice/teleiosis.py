from __future__ import annotations
from dataclasses import dataclass
from typing import Callable, Any

@dataclass(frozen=True)
class Evaluation:
    score: float
    safety_pass: bool
    compatibility_pass: bool
    evidence: dict[str,Any]

def champion_challenger(champion:dict[str,Any],challenger:dict[str,Any],evaluator:Callable[[dict[str,Any]],Evaluation])->dict[str,Any]:
    base=evaluator(champion); cand=evaluator(challenger)
    if not cand.safety_pass or not cand.compatibility_pass:
        return {'verdict':'REVERT','winner':'champion','champion':base.evidence,'challenger':cand.evidence}
    if cand.score > base.score:
        return {'verdict':'KEEP_CANDIDATE','winner':'challenger','champion':base.evidence,'challenger':cand.evidence}
    return {'verdict':'KEEP_BASELINE','winner':'champion','champion':base.evidence,'challenger':cand.evidence}
