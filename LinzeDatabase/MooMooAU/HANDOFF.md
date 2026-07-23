# MooMooAU 当前交接

## 当前目标与状态

- 当前唯一 Run Contract 是 `RMD-06` 的 GitHub-hosted 非生产预检；不得进入真实 Gmail、私有数据仓、
  protected Oracle、生产运行、部署、最终 Acceptance 或最终发布。
- 当前控制包为 `MMAU-ARCHIVE-TP-2026-07-23-V1.0.6`。它原样继承 v1.0.1 的 34 RQ、34 AC、
  58-task DAG、Kill Criteria 与十条不变量，并将 v1.0.5 作为不可变直接前序。
- 唯一当前状态权威是 `machine/status/latest.json`：本地机制证据完整，受保护 Oracle 0/43，
  最终 Acceptance 0/34，生产 Workflow 0，发布状态 `LOCAL_ONLY_NOT_PUBLISHED`。
- Governance 固定为私有 `LinzeColin/Governance` 的提交
  `ebc6c2e4884edc959118cfc56d0e18a86c49460f`。

## RMD-06 已完成

1. 四个 Workflow 的 `runner.temp` 已从 job-level `env` 移至 runner 上的首个配置步骤，消除零 Job
   expression 解析失败。
2. 八个依赖 Governance 的 Workflow 只允许通过
   `MOOMOOAU_GOVERNANCE_DEPLOY_KEY` 注入 pinned `actions/checkout` 的 `with.ssh-key`；
   凭据不得进入 env、shell、项目 Python 或生产运行时。
3. fork pull request 在受保护依赖 checkout 前显式 fail closed；禁止 `pull_request_target`；
   `persist-credentials` 与 Deploy Key 写权限均为 false。
4. 单仓只读 Deploy Key 与 MetaDatabase Actions Secret 已配置；精确固定提交可由该凭据读取。
   本机一次性私钥、探测仓与临时 known_hosts 已删除。
5. v1.0.6 package、delivery status、Governance facts/render、publication、Secret scan、生产 composition、
   Workflow matrix、Stage 1、Stage 2 与 Stage 7 preflight 全部通过本地确定性验证。
6. 项目全量测试为 `257 passed`；Ruff 变更范围零问题；strict mypy 为 `70 source files` 零问题。
7. Workflow matrix 为四个 cumulative PASS、四个 historical expected-BLOCKED，且外部写入、远端运行、
   生产运行、发布均为 0，验证前后树不变。
8. 已从最新 `origin/main` 建立无旧开发谱系的 `codex/moomooau-rmd06-cloud-preflight` 快照分支；
   项目目录与全部十个 MooMooAU Workflow 已按 Git tree/blob 逐字节核对。
9. 34 个最终 Acceptance 记录已确定性重建到该干净主线父提交，仍保持 34/34 `BLOCKED`、0 `PASS`、
   0 invalid；未把谱系迁移解释为 protected 或生产成功。

## 关键边界

- 依赖 Deploy Key 不等于生产 Secret；普通 CI 的 Gmail、数据仓和生产 Secret 读取仍为 0。
- GitHub-hosted 非生产预检不等于 protected Oracle、生产健康、部署、发布或最终 Acceptance。
- 旧开发分支与最新 `origin/main` 历史分叉，继续禁止直接 push；远端预检只允许使用已从最新主线
  建立的干净临时快照分支。
- 预检任一 Workflow syntax、Governance checkout、Secret 边界、package、publication 或累计门失败，
  必须停止，不得扩大权限或读取生产 Secret。

## 下一步

1. 重建干净谱系变更后的 v1.0.6 Manifest，并复跑 package、acceptance、publication、Secret、累计矩阵
   与全量测试。
2. 仅 push 受控 RMD-06 候选分支并观察全部 GitHub-hosted 非生产 Workflow。
3. 全绿后删除远端候选分支；RMD-06 后续仍按 Beta → M3 → Timeline Blue-Green → GA → Recovery →
   最终 AC 顺序推进，任何未知或失败结果立即停止。
