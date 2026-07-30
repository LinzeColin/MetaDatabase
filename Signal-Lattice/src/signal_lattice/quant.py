from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from math import sqrt
from statistics import mean, pstdev
from typing import Iterable

@dataclass(frozen=True)
class PointInTimeRecord:
    effective_at: datetime
    available_at: datetime
    ingested_at: datetime
    value: float


def visible_at(records:Iterable[PointInTimeRecord], decision_as_of:datetime)->list[PointInTimeRecord]:
    out=[]
    for r in records:
        if r.available_at <= decision_as_of and r.ingested_at <= decision_as_of and r.ingested_at >= r.available_at:
            out.append(r)
    return out

def net_expected_return(win_probability:float,avg_win:float,avg_loss:float,fees:float,half_spread:float,slippage:float,borrow:float=0.0,tax:float=0.0)->float:
    gross=win_probability*avg_win-(1-win_probability)*abs(avg_loss)
    return gross-fees-2*half_spread-slippage-borrow-tax

def max_drawdown(returns:Iterable[float])->float:
    equity=1.0; peak=1.0; mdd=0.0
    for r in returns:
        equity*=1+r; peak=max(peak,equity); mdd=min(mdd,equity/peak-1)
    return mdd

def annualized_sharpe(returns:Iterable[float],periods:int=252)->float:
    vals=list(returns)
    if len(vals)<2 or pstdev(vals)==0:return 0.0
    return mean(vals)/pstdev(vals)*sqrt(periods)

def pbo(in_sample:list[list[float]],out_sample:list[list[float]])->float:
    if not in_sample or len(in_sample)!=len(out_sample):raise ValueError('matched paths required')
    failures=0
    for ins,outs in zip(in_sample,out_sample):
        if not ins or not outs:raise ValueError('non-empty strategy scores required')
        best=max(range(len(ins)),key=lambda i:ins[i])
        median=sorted(outs)[len(outs)//2]
        failures += outs[best] < median
    return failures/len(in_sample)

def deflated_sharpe_gate(observed:float,trials:int,skew:float=0.0,kurtosis:float=3.0)->float:
    # Conservative deterministic proxy gate. Production calibration remains disabled without sealed PIT data.
    penalty=sqrt(max(0.0,2.0*__import__('math').log(max(1,trials))))
    non_normal=1.0+abs(skew)+max(0.0,kurtosis-3.0)/4.0
    return observed-penalty*non_normal
