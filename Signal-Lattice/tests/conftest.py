"""所有测试共用：SEC 客户端必须有 User-Agent（仓库不内置任何默认值），测试里统一用一个假的。
缺失 UA 的行为有专门的测试（tests/test_evidence_sec_client.py），那里会自己清掉这个环境变量。"""

import os

os.environ.setdefault("SIGNAL_LATTICE_SEC_UA", "SignalLatticeTest fake-contact@example.invalid")
