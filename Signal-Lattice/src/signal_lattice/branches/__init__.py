"""Stage 2 可复算分支与其只读汇总入口。"""

from .models import BranchVerdict
from .runtime import build_branch_report

__all__ = ["BranchVerdict", "build_branch_report"]
