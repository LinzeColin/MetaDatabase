# ABD 开发交接

## 当前目标

在隔离 worktree `codex/abd-v0001-s10-p01` 按冻结 Task Pack 推进 ABD `v0.0.0.1` 的 S10。S10/P01「时间交叉验证与校准」已完成本地签名证据；下一轮只能推进 S10/P02，不能开始 S10/P03、S10/P04、S10 整体复审或 GitHub 阶段上传。

## 当前状态

- S09 已完成整体复审并合并到远端 `main`（合并提交 `c94064260f2f70d18971a7d5a9c65e7c81e1a74d`）。S10 worktree 从该远端基线建立；主工作树有无关改动，保持只读且未触碰。
- S10/P01 已签名通过：`machine/evidence/EVD-S10-P01.json`，验证合同 `AC-S10-P01`，下一状态 `S10/P02_READY_NOT_STARTED`。
- 实现包含至少 8 个冻结时间折叠的 isotonic、logistic 与多分类温度校准；三种方法均满足冻结合同斜率 `0.90–1.10`、截距绝对值不大于 `0.02` 与校准误差不大于 `0.025`。选择 logistic（二分类）和 temperature（多分类）仅表示可继续进入下游不确定性门，不构成推荐、下注、订单或收益承诺。
- 报告 `calibration_report.json` 的冻结重放 SHA-256 为 `acf155d7e1db64f4a342ee0c46e682bcfb616fcf60b4a349726feafae0a9eb3a`。它只使用冻结合成输入，且明确记录未访问网络、真实市场、账户、Gmail、OVH 或 Cloudflare。
- 为使新增任务包要求的根模块接受现有零付费依赖扫描，`abd_acceptance/budget.py` 仅将 `calibration` 与 `temporal_cv` 归类为本地源码；扫描仍对未分类第三方导入失败关闭。S08/P03、P04 的既有共享运行时合同已将该扫描器排除出历史 receipt 输入哈希；本轮未重跑任何历史全量 stage 回归。
- `financial_target_status` 仍为 `UNVERIFIED_NOT_GUARANTEED`；没有真实资金、账户、订单、生产部署或激活。

## 已验证

- 任务包基线文件与原始 Task Pack 逐一比对一致；Task Pack 静态校验 `49/49 PASS`。
- `tests/S10/P01_test.py` 定向测试：`18 passed`。其为本地 CPU 校验，无网络、无账户、无真实时间等待；未执行全量测试、完整回归或 real-time soak。
- `machine/tools/scan_paid_dependencies.py`：PASS，未发现付费或未知依赖。
- `AC-S10-P01` 候选预检：`30/30 PASS`；写入签名证据后的带报告验证：`34/34 PASS`；`--verify-existing AC-S10-P01`：PASS。

## 关键文件

- `calibration.py`
- `temporal_cv.py`
- `calibration_report.json`
- `abd_acceptance/temporal_calibration.py`
- `abd_acceptance/__main__.py`
- `abd_acceptance/budget.py`
- `machine/tests/fixtures/S10_P01.json`
- `tests/S10/P01_test.py`
- `machine/evidence/S10/P01/pytest.xml`
- `machine/evidence/S10/P01/paid_dependency_scan.txt`
- `machine/evidence/EVD-S10-P01.json`
- `machine/evidence/EVD-S10-P01_rollback.json`

## 未解决风险

- S10/P02--P04、S10 整体复审及 GitHub 阶段上传尚未开始，不能被本 phase 的 PASS 替代。
- 真实市场、真实账户、TAB/Gmail 证据归档、OVH、Cloudflare 与生产上线均未验证、未部署且不应据此推断完成。

## 下一步

下一次 run 严格只处理 S10/P02 的任务包输出、定向验收和连续证据。保持零新增现金、无真实时间 soak、无全量测试/完整回归；在四个 S10 phase 全部完成前不得上传 GitHub 或宣称上线。
