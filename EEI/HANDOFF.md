# HANDOFF

Updated: 2026-07-15 Australia/Sydney（接管重写版；此前 CodexProject 时代的完整交接历史见 git history 与 docs/governance/DEVELOPMENT_LEDGER.md）

## Current Goal

按 Owner 签认的 `docs/pursuing_goal/v5_0/V5_0_ROOT_LOCK.yaml` 完成 MVP v0.1 全部开发（S6→S11），HR1-HR6 硬约束不可违反。

## 阅读顺序（任何 agent 开工前）

1. `docs/pursuing_goal/CURRENT.yaml`
2. `docs/pursuing_goal/v5_0/V5_0_ROOT_LOCK.yaml`
3. `开发记录.md`（完整 Stage→Phase→Task roadmap，40 任务）
4. `docs/governance/roadmap.yaml` 与 `docs/governance/delivery_tasks.yaml`（legacy 验收矩阵）
5. 本文件

## 仓库与工作区

- GitHub source of truth：`LinzeColin/MetaDatabase`（私有），EEI 位于 `EEI/` 子目录（wave 3 迁入，PR #1，main `7bca2007`，source_tree_sha `fc83cf48982a00908fa658045b958f0a32b65e8c`，362 条历史保留）
- 本机主 checkout：`/Users/linzezhang/Documents/Codex/MetaDatabase`
- 开发 worktree：`/Users/linzezhang/Documents/Codex/main_worktree/MetaDatabase/eei`（分支 `codex/eei`）
- CI：`.github/workflows/eei-validation.yml`（MetaDatabase root，path-filter EEI/**，push[main,eei-**]+PR+dispatch）
- 旧 CodexProject 源树：删源由治理线 GOV-SPLIT-WAVE3 承载（删源 diff 需 Owner 过目）；**产品变更只允许发生在 MetaDatabase 侧**
- 治理框架：MetaDatabase 禁止复制框架，须从 `LinzeColin/Governance` 以 CI checkout 消费（接入工作在治理线待办）

## Current Status（2026-07-15）

- Stage `S6 接管·迁移·真相恢复` in_progress：S6PAT01 ✅（wave3 迁移）、S6PBT01 ✅（运行时恢复）、S6PBT02 ✅（基线全绿）、S6PAT02/S6PAT04 本批落库、S6PAT03（台账对账+决策落账）next。
- 开放 P0 验收：A202（T1301）、A204/A205（T1303）、A209（T1307，288/288 证据在、S11PBT01 关门前保持 IN_PROGRESS）、A026/A027（T904）、A108-A112（T802/T805）。A210 已按 Owner 决策 descope（"噪音"），validator 保留备商用。
- Owner 决策 D1-D9（2026-07-15，将在 S6PAT03 落 events）：立即迁移 / A210 descope / 金标方法授权接管人（来源引证式）/ 数据平台 2016+ 与长期运行 / Ask 栏跳转 ChatGPT / 云端 7×24 Cloudflare / home.linzezhang.com 入口 / 动效高级 bar / 全量持续执行授权。

## Verification Evidence（新家基线，2026-07-15）

- MetaDatabase CI：`EEI validation` run `29388694034`（PR）/ `29388679237`（push）均 SUCCESS（bootstrap、make verify×2、G2 PostgreSQL 集成、浏览器 E2E、live FastAPI/PostgreSQL E2E）。
- 本地：`make bootstrap PYTHON=python3` PASS；`make db-up`/`make health` PASS（Docker 29.6.1）；`make verify` PASS（含 196/196 单测）；`make test-integration` PASS（单实例）；`make test-e2e` 35/35 PASS；`make test-e2e-live` PASS。

## 环境已知坑（本机）

1. 本机 `python3` 是 3.9：bootstrap 必须 `make bootstrap PYTHON=python3`；`uv sync` 会用自管 CPython(3.13) 重建 `.venv` 并**清掉 pip 装进去的 uv 二进制**——修复：`python3 -m pip install --user uv==0.11.22 && cp "$(python3 -m site --user-base)/bin/uv" .venv/bin/uv`。Makefile 加固列入 S6PAT03。
2. 集成/E2E 套件**不可并发多实例**（worker 抢队列、端口冲突）；孤儿服务清理：`lsof -ti:8000,3000 | xargs kill`。
3. 后台 shell 起始 cwd 不继承，任何命令链先 `cd` 绝对路径。

## Next Steps

1. S6PAT03：74/130 vs 55/128 台账对账归零；D1-D9 决策落 `docs/governance/development_events.jsonl`；A209 事件/注册表一致化；Makefile bootstrap 加固。
2. S6 收口后进入 S7（真实数据主干与数据平台）：SEC live（golden-vertical CIK 白名单 + Owner 邮箱 UA）→ 双源核验 → 事实发布 → 金标 → 2016+ 历史回填 → 定时采集 → 数据保全 → 云发布通道。
3. 与治理线协同：复核其 GOV-SPLIT-WAVE3 改动集 → 删源 diff 交 Owner → 落地；治理框架 CI 接入 MetaDatabase 后补 check-render 机器校验。
