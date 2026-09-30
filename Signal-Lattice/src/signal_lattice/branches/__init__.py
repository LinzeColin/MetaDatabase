"""选股分支与它们共用的数据合同。分支通过 branch_entries 在独立子进程里运行，不在实时层运行。"""

from .models import BranchVerdict

__all__ = ["BranchVerdict"]
