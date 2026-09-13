"""Stage 4 回测、滚动前推与样本外 Alpha 度量。"""

from .runner import ContributionSample, run_backtest

__all__ = ["ContributionSample", "run_backtest"]
