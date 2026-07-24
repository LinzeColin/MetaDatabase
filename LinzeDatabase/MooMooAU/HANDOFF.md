# MooMooAU 当前交接

更新时间：2026-07-24（Australia/Sydney）

## 当前目标与状态

- 本轮只处理 Stage 7，不进入其他 stage。
- T0702/S7AC-002 protected Raw-only Beta 已在历史 exact-main attempt 1 通过：
  Alpha PASS、Raw 远端恢复 100%、identity cleanup PASS、GitHub rerun 0。
- 当前控制包为 `MMAU-ARCHIVE-TP-2026-07-24-V1.0.7`，直接前序
  `PACKAGE_MANIFEST.v1.0.6.json` 字节不变。
- 唯一状态权威是 `machine/status/latest.json`：
  `PROTECTED_BETA_PASS_STAGE7_INCOMPLETE`；受保护 Oracle 2/43 PASS，最终 Acceptance
  0/34，production readiness `BLOCKED`，publication
  `CONTROLLED_BETA_DELIVERY_NOT_FINAL`。
- Owner 报告 MooMooAU GitHub App 已安装且已链接 private 数据仓；本轮未读取 Secret、未调用
  Gmail/private repo、未执行 M3，也未独立把该报告提升为 protected Oracle 证据。
- 当前 `machine/stages/S7/contracts/run_contract.json` 仍是
  `m3_authorized=false`。因此新 M3 Workflow 默认关闭，并在任何 M3 Secret 读取前停止。

## 本轮完成

- 新增 `src/moomooau_archive/protected_m3.py`：
  - 单 verified candidate、mutation budget 精确为 1；
  - verified Raw 与 Processed complete/safe-deferred；
  - Raw + Processed 同一私有仓远端解密/摘要恢复；
  - 第二次 sender verification；
  - 恢复通过后才允许唯一 exact `users.messages.trash`；
  - Timeline、schedule、Blue-Green、GA 不可达；
  - 临时 age identity 与 credential cleanup。
- 新增 `src/moomooau_archive/protected_m3_entrypoint.py`：
  - 绑定 owner/repository numeric identity、main、exact SHA、GitHub-hosted、attempt 1；
  - 绑定 T0702 PASS receipt 与同树 M3 gate；
  - 只允许八个精确 Secret 名；
  - 未授权路径返回 contract-only 零效果结果；
  - protected 输出固定为 aggregate-only。
- 新增 root `.github/workflows/moomooau-m3.yml`：
  manual `workflow_dispatch` only、`contents: read`、single writer、无 cache/artifact/self-hosted/
  schedule/git push；首个无 Secret job 在当前 Run Contract 下确定性停止。
- 扩展 T0703 合成端到端与 Workflow policy 测试；证明 Processed recovery 先于 exact Trash、
  age ciphertext-only、零附带 Gmail mutation 与 cleanup。
- 任务包演进到 v1.0.7，新增 read-me、roadmap、provenance、manifest、changelog；保持 34 RQ、
  34 AC、58-task DAG、Kill Criteria 与十条不变量不变。
- 更新唯一状态、T0703/Stage 7 evidence、34 份 Acceptance 控制面、Governance facts 和七份派生文档。

## 验证结果

- CI 对齐测试：`334 passed`。
- RMD-05/RMD-06 回归：`50 passed`。
- Stage 7 scoped preflight：9/9 checks PASS；
  `LOCAL_MECHANISMS_READY`，protected integration 仍为 false。
- Package v1.0.7：PASS，604 个文件逐字节验证。
- Workflow matrix：4 个 cumulative PASS + 4 个 historical expected-BLOCKED，tree unchanged。
- Ruff：110 个 CI scope 文件 format PASS，lint PASS。
- strict mypy：63 个 source files PASS。
- Governance pinned commit
  `ebc6c2e4884edc959118cfc56d0e18a86c49460f`：render drift 0，中文预算门和 blocker 门 PASS。
- Publication scan：606 files、0 findings。
- Stage 6 structured Secret scan：0 findings；Stage 7 exact `detect-secrets`：0 findings。
- `pip-audit`：0 known vulnerabilities。
- Acceptance evidence builder：34 records valid，外部效果 0；最终 34 项均诚实保持 BLOCKED。

## 未完成

- T0703 protected M3 first attempt 及真实 Processed/Trash 证据。
- T0704 Blue-Green/单一 Timeline、T0705 真实 04:30 Sydney GA、T0706 passive Codex
  Automation、T0707 Recovery Key drill、T0708 protected patch lifecycle。
- 34 项最终 Acceptance、整体复审、复审修复和最终一次性 GitHub 上传。

## Git 与下一步

- worktree：当前隔离开发 worktree（不得在主工作树继续修改）
- branch：`codex/moomooau-t0703-protected-entrypoint`
- base：`56449b3916a7db086130414146727277b24fd9ee`
- 本轮已保存为一个本地验证提交；未 push、未建 PR、未 merge、未 dispatch。
- 下一 run 仍只处理 Stage 7。只有明确覆盖此前“不得进入 M3”的 Owner 指令后，才可生成
  `m3_authorized=true` 的唯一 T0703 Run Contract、配置八项 M3 Secret 并执行一次 Budget-1
  exact-main first attempt；任何失败都 fail closed，禁止 GitHub rerun。
