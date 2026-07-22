# bottleneck-serenity-skill Run Contract

本文件是 `bottleneck-serenity-skill` pursuing goal 的执行入口。任何实现动作必须先绑定到
`03_STAGE_PHASE_TASKS.md` 中唯一一个 Task；一次 run 最多完成一个 Task。

## 当前状态

- Project：`Stock_Skill/bottleneck-serenity-skill/`
- Stable ID：`bottleneck-serenity-skill`
- 机器版本：`0.0.0.1`
- 展示与 release 版本：`v0.0.0.1`
- 分发模式：`SOURCE_ONLY`
- 本机安装策略：`PROHIBITED`
- 当前 Stage：`S0 — Governance baseline`
- 最近完成 Task：`BSS-S0-P2-T011 — Stage 0 第五轮整体重审`
- 下一许可 Task：`BSS-S0-P3-T001 — Stage 0 Publish`
- 状态：`STAGE_REVIEW_PASSED_READY_TO_PUBLISH`

## 真源优先级

冲突时按以下顺序停止并解决，不得自行拼接答案：

1. 用户在当前 pursuing goal 中的明确决定；
2. 仓库根 `AGENTS.md` 与工作间六条铁律；
3. `Stock_Skill/AGENTS.md` 与 `Stock_Skill/REGISTRY.json`；
4. 本 Task Pack；
5. 输入源包及其研究报告；
6. 推断、历史对话或外部实现。

## Task Pack 身份与完整性

- Task Pack 机器版本读取 `VERSION`，当前必须为 `0.0.0.1`。
- `MANIFEST.sha256` 覆盖本目录除自身外的全部文件，路径必须是规范 POSIX 相对路径。
- 任一 Task 修改本目录时，必须在同一 Task 最后重算 manifest；manifest 不一致时该 Task 不得完成。
- Stage Review 必须绑定评审前的规范化文件树 digest；Stage Publish 必须绑定 manifest 与 Git commit。
- 复审 finding、等级、subject digest、整改状态和关闭证据统一记录在 `CHANGELOG.md` 的 review ledger。

### Review subject digest：`taskpack-tree-sha256-v1`

- Root 是仓根相对路径 `Stock_Skill/bottleneck-serenity-skill/task-pack/`。
- Root 必须存在、是非 symlink 目录且 subject 非空；`MANIFEST.sha256` 必须存在并为普通文件，否则 fail closed。
- Subject 包含 Root 下递归的全部普通文件，**包括** `MANIFEST.sha256`；目录本身不进入字节流。
- symlink、socket、device、FIFO、非普通文件、绝对路径、空路径段、`.`、`..`、非 NFC 路径或规范化后
  重复路径均 fail closed。
- 每个 POSIX 相对路径必须已是 Unicode NFC；按其 UTF-8 字节升序排列，不含 `./` 前缀。
- 对每个排序后文件依次写入：`relative_path_utf8`、单字节 NUL (`0x00`)、原始文件 bytes、单字节 NUL。
- 对完整字节流计算 SHA-256，输出 64 位小写十六进制。Review 必须在改动任何 subject 文件前计算并记录。

以下标准库参考实现是该协议的规范可执行定义：

```python
from hashlib import sha256
from pathlib import Path, PurePosixPath
import stat
import unicodedata

root = Path("Stock_Skill/bottleneck-serenity-skill/task-pack")
entries = []
seen = set()

if not root.exists() or root.is_symlink() or not root.is_dir():
    raise SystemExit(f"invalid task-pack root: {root}")
manifest_path = root / "MANIFEST.sha256"
if (
    not manifest_path.exists()
    or manifest_path.is_symlink()
    or not stat.S_ISREG(manifest_path.lstat().st_mode)
):
    raise SystemExit(f"missing or invalid manifest: {manifest_path}")

for path in root.rglob("*"):
    if path.is_symlink():
        raise SystemExit(f"invalid symlink: {path}")
    mode = path.lstat().st_mode
    if stat.S_ISDIR(mode):
        continue
    if not stat.S_ISREG(mode):
        raise SystemExit(f"invalid non-regular file: {path}")
    relative = path.relative_to(root).as_posix()
    if relative != unicodedata.normalize("NFC", relative):
        raise SystemExit(f"non-NFC path: {relative}")
    parts = PurePosixPath(relative).parts
    if not relative or relative.startswith("/") or any(part in {"", ".", ".."} for part in parts):
        raise SystemExit(f"invalid relative path: {relative}")
    relative_bytes = relative.encode("utf-8")
    if relative_bytes in seen:
        raise SystemExit(f"duplicate canonical path: {relative}")
    seen.add(relative_bytes)
    entries.append((relative_bytes, path))

if not entries or b"MANIFEST.sha256" not in seen:
    raise SystemExit("empty task-pack subject or manifest not included")

digest = sha256()
for relative_bytes, path in sorted(entries, key=lambda item: item[0]):
    digest.update(relative_bytes)
    digest.update(b"\0")
    digest.update(path.read_bytes())
    digest.update(b"\0")
print(digest.hexdigest())
```

## 无环制品 DAG 与 Stage Publish 封印

以下所有权和顺序不可互换；任何反向引用或 seal 后 source 改写均 fail closed：

1. `task-pack/MANIFEST.sha256` 只列 `task-pack/` 内除自身外的普通文件，使用仓库 manifest 的
   `SHA256  ./relative/path` 行格式；不得列 outer release、registry 或 backup manifest。
2. release ZIP 是已封印 `task-pack/`（包括其 manifest）的确定性函数；release ZIP 不含 outer
   project、release 自身、registry、`SHA256SUMS` 或 `BACKUP_MANIFEST.sha256`。
3. release 实算 SHA 只写入 `releases/SHA256SUMS`、`REGISTRY.json` 对应条目和
   `BACKUP_MANIFEST.sha256` 的 release entry；三者必须相等。
4. `BACKUP_MANIFEST.sha256` 只覆盖 outer project 内除自身外的普通文件，因此包含 release、
   `SHA256SUMS`、task manifest 与 Task Pack 内容；它在所有 project 文件稳定后最后生成。
   Stage 2 首次登记时，Registry Prep 只能验证未激活 fixture；必须由后续 Release/Activate Task 在真实
   release SHA 已产生后，原子写入 release、sums、registry、backup manifest 并跑 validator。
5. Stage 内的 Release/Readiness Task 只生成并验证候选制品。Stage Review PASS 后，Stage Publish
   先完成本 Stage 所有 tracked source/status 变更并刷新 task manifest，再冻结 subject；有 release 的
   Stage 必须从该 frozen subject 双构建、更新 sums/registry、最后更新 backup manifest。
6. commit/push 前必须从 staged tree 或等价 proposed commit 的全新 checkout 重放 build/verify，得到
   相同 release SHA、manifest 集合与 registry PASS；seal 后不得再修改 release 输入或其他 project source。
7. commit、push、PR/CI/merge 与最终 worktree/branch/PR 清理证据是 DAG 的终端外部叶子，不写回已封印
   Task Pack/release。seal 时不得把尚未发生的外部动作预写为 `DONE`；非终态 Stage 由下一 Stage 首个
   本地 Task 按外部证据回填上一 Publish 状态，Stage 4 Publish/Cleanup 则只由 GitHub 与清理命令实证。
   任一步失败时同一 Publish Task 仍未完成：禁止进入下一 Task，修改后必须从第 5 步重新封印。

## 全局不可变约束

1. 所有最终身份使用 `bottleneck-serenity-skill`；代码标识符需要下划线时使用
   `bottleneck_serenity_skill`。
2. `VERSION` 和 registry 使用 `0.0.0.1`；人类展示、tag-like 文本和 release 文件名使用
   `v0.0.0.1`。机器值不含 `v`、空格、正号或前导零。
3. 不安装到 `~/.agents/skills`、`~/.codex/skills` 或其他运行时目录。
4. 不接入券商、凭据、交易执行、自动下单或保证收益能力。
5. 不提交账户、真实组合、客户、付费数据、MNPI、凭据、会话或本机绝对路径。
6. 保留四道硬门、三个时钟、每股收益捕获桥、负向搜索、因果聚类和不可改写历史快照。
7. 原输入 ZIP 只作迁移证据；current release 必须从改名后的 canonical source 确定性重建。
8. 任一版本、路径、哈希、身份或 UI metadata 冲突时状态为 `UNKNOWN`，不得猜测。
9. 一个 run 只执行一个 Task；同一 Task 内可以修复其自身验证失败，但不得顺带完成下一 Task。
10. Phase 结束不上传；Stage 必须先整体复审、整改、复审通过，再统一 commit/push。
11. 本次迁移不得静默改变硬门、三个时钟、几何/门控评分、证据标准、历史快照或无交易边界；
    任何核心逻辑变化必须先提交影响分析、版本影响和用户决定，另开 Task。
12. 需求、验收、Task、测试/Oracle、证据与交付物必须通过稳定 ID 可追溯；缺行不得判完成。

## 每次 Run 必填合同

开始任何 Task 前，在 commentary 中声明：

1. Task ID 与目标；
2. 最小相关范围；
3. non-goals；
4. 将检查的文件；
5. 可能修改的文件；
6. 验证命令和证据；
7. 风险、回滚；
8. 停止条件。

结束时必须报告：变更文件、命令与结果、残余风险、Stage/整体进度、预计剩余 run。

## 已完成 Task 合同：BSS-S0-P1-T001

- 目标：创建 `task-pack/` 下 compact `5+1` 合同文件并完成内部一致性自检。
- 最小范围：仅本目录六个 Markdown 文件。
- Non-goals：不导入源包；不修改 registry/validator；不生成正式 Skill；不提交或上传。
- 输入：仓库规则、现有 registry、源 ZIP 清单和用户确认的身份/版本/发布约束。
- 输出：`00`–`04` 与 `CHANGELOG.md`。
- 验证：文件计数、相对链接、Task ID 唯一性、状态唯一性、阶段门与关键约束搜索。
- 风险：Task Pack 与现有 validator 能力不一致；通过显式 Stage 1 兼容任务处理。
- 回滚：删除尚未提交的 `Stock_Skill/bottleneck-serenity-skill/`。
- 完成证据：六文件存在；Task ID、状态、阶段门、身份、版本、公开安全和 registry 回归自检通过。
- 停止条件：已满足；本 run 不进入 Stage 0 全量复审。

## 已完成 Task 合同：BSS-S0-P2-T002

- 目标：修复 Stage 0 review `S0-R001`–`S0-R007`，不跨入实现。
- 最小范围：Task Pack 合同、`VERSION`、`MANIFEST.sha256`。
- Non-goals：不改 registry/validator/CI；不导入源包；不实现 Skill；不提交或上传。
- 完成证据：REQ/CAP/NG→ACC→Task→Test/Evidence 追溯、完整性门、finding ledger、CI Task、
  deterministic release/restore、许可/核心逻辑门、假设生命周期和 numeric-quad grammar 已补齐。
- Builder 状态：全部 finding 为 `FIXED_PENDING_REREVIEW`，不得由本 Task 自行关闭。
- 停止条件：manifest 与自检通过后停止；只允许后续整体重审。

## 已完成 Task 合同：BSS-S0-P2-T003

- 目标：在锁定整改后 subject 上逐项复验 Stage 0 gate 与 `S0-R001`–`S0-R007`。
- Reviewed subject：`d2794667d739d30012faf8f28889e27574772d53a6b70eca62308acef28883e4`。
- Verdict：`FAIL`。
- 已关闭：`S0-R002`、`S0-R004`、`S0-R005`、`S0-R006`、`S0-R007`。
- 未关闭：`S0-R001`、`S0-R003`；新增 `S0-R008`–`S0-R010`。
- Non-goals：未修合同语义、未进入 Stage 1、未提交或上传。

## 已完成 Task 合同：BSS-S0-P2-T004

- 目标：只整改 `S0-R001`、`S0-R003`、`S0-R008`、`S0-R009`、`S0-R010`。
- 整改基线：`02a874f2e9146329aa0b53754b1380e42df29cc558e5726512e30b7fc8c521e7`。
- `S0-R001`：追溯改为 44 个 ACC 逐行映射唯一 Producer、明确 Verifier、Oracle 与 Evidence；
  23 REQ/9 CAP/7 NG 全覆盖，引用 Task 必须存在。
- `S0-R003`：ledger 增加 Remediation Task、Remediation evidence 与 Closure evidence，关闭证据只由后续复审写入。
- `S0-R008`：Stage 0 pre-publish 允许且仅允许本项目 scoped changes，Publish commit 后才要求 worktree 干净。
- `S0-R009`：增加 `SOURCE_MANDATED`/`DERIVED`，将 `REQ-022/REQ-023` 降到与实际证据相符的等级。
- `S0-R010`：冻结 Review 失败时优先启用条件 Task、否则按最大 suffix+1/+2 追加且循环到 PASS 的规则。
- Builder 状态：五个 finding 均为 `FIXED_PENDING_REREVIEW`，不得由本 Task 自行关闭。
- Non-goals：未执行整体重审、未进入 Stage 1、未提交或上传。

## 已完成 Task 合同：BSS-S0-P2-T005

- 目标：在锁定整改后 subject 上复验完整 Stage 0、既有 finding 与七个 Stage 0 ACC。
- Reviewed subject：`b97ef4030e9bb23581ca22dc89560a738c583dff6eeb4e5ce037ce670528edcd`。
- Verdict：`FAIL`。
- 已关闭：`S0-R003`、`S0-R008`、`S0-R009`；`S0-R002/R004/R005/R006/R007` 回归 PASS。
- 未关闭：`S0-R001`（Producer 与产物历史不符）、`S0-R010`（Stage 4 `Deliver` 未纳入通用
  `Publish` 路由）；新增 `S0-R011`（subject digest 无持久化规范算法）。
- Gate：`ACC-S0-001`–`ACC-S0-004` PASS；`ACC-S0-005`、`ACC-S0-006`、`ACC-S0-007` FAIL。
- Non-goals：未整改任何 finding、未进入 Stage 1、未提交或上传。

## 已完成 Task 合同：BSS-S0-P2-T006

- 目标：只整改 `S0-R001`、`S0-R010`、`S0-R011`。
- 整改基线：`6b83a60ef3b09b7f616a2536bf331c7623b630a94e0e7cad315335c162c4dbf0`。
- `S0-R001`：Producer 定义为“首次使该 ACC 全部条件同时成立”的 Task；`ACC-S0-002` 修正为实际完成
  VERSION/manifest 封印的 `BSS-S0-P2-T002`。
- `S0-R010`：Stage 4 终态 Phase 统一为 `Publish`，其语义包含 commit/push、PR ready、CI、merge/close，
  随后才进入 Cleanup；通用 PASS/FAIL 路由适用于全部五个 Stage。
- `S0-R011`：冻结 `taskpack-tree-sha256-v1` 的文件集合、拒绝条件、排序、字节帧、SHA-256 输出与
  标准库参考实现。
- Builder 状态：三个 finding 均为 `FIXED_PENDING_REREVIEW`，不得由本 Task 自行关闭。
- Non-goals：未执行整体重审、未进入 Stage 1、未提交或上传。

## 已完成 Task 合同：BSS-S0-P2-T007

- 目标：在锁定整改后 subject 上复验完整 Stage 0、既有 finding 与七个 Stage 0 ACC。
- Reviewed subject：`849caf740442f5450db016462b030f9c22b15507c3c805571960b4b6da5ac5d5`。
- Verdict：`FAIL`。
- 已关闭：`S0-R010`；`S0-R002`–`S0-R009` 的既有关闭项回归 PASS。
- 未关闭：`S0-R001`（“首次成立”与“后续重建转移”两条 Producer 规则冲突）、`S0-R011`
  （缺 Root/错误 cwd 时参考实现以退出码 0 返回空树 SHA-256，未 fail closed）。
- Gate：`ACC-S0-001`–`ACC-S0-004` PASS；`ACC-S0-005`、`ACC-S0-006`、`ACC-S0-007` FAIL。
- Non-goals：未整改任何 finding、未进入 Stage 1、未提交或上传。

## 已完成 Task 合同：BSS-S0-P2-T008

- 目标：只整改 `S0-R001`、`S0-R011`。
- 整改基线：`a639f70646e8b441281a99e18a627b3501de57acb0caf1f39720c2fc54d19b03`。
- `S0-R001`：Producer 固定为首次建立完整验收能力与主制品集合的 Owner；同协议下例行刷新派生
  hash/manifest 不转移，只有改变验收定义、协议或主制品集合并接管责任时才转移。
- `S0-R011`：参考实现显式拒绝缺失/非目录/symlink Root、缺失/非法 manifest、空 subject、条目
  symlink 与其他非普通文件；happy path 和六类负例已执行。
- Builder 状态：两个 finding 均为 `FIXED_PENDING_REREVIEW`，不得由本 Task 自行关闭。
- Non-goals：未执行整体重审、未进入 Stage 1、未提交或上传。

## 已完成 Task 合同：BSS-S0-P2-T009

- 目标：在锁定整改后 subject 上复验完整 Stage 0、既有 finding、七个 Stage 0 ACC 与未来验收可执行性。
- Reviewed subject：`1fbfff05462e03b514edb6bf9ba434cc50b645ec02a45291a393953485ca2315`。
- Verdict：`FAIL`。
- 已关闭：`S0-R001`、`S0-R011`；`S0-R002`–`S0-R010` 的既有关闭项回归 PASS。
- 新增：`S0-R012`（P1）。`ACC-S2-007` 要求 task manifest 保存位于其受控根之外的 release SHA；同时
  release 打包完整、仍会被后续 Review 改写的 Task Pack，现有 Stage 顺序无法保证最终 clean checkout
  重建相同 release SHA。该 hash/封印图不可执行且违反 `REQ-021`。
- 正向证据：Python 规范实现与独立 Ruby 实现得到相同 subject digest；manifest 文件/哈希集合为 `7/7`；
  44 个 ACC、23/9/7 Source 集合、50 个 Task 与全部引用机械校验通过。
- 负向证据：缺 Root、Root 为普通文件、Root symlink、缺 manifest、manifest symlink、entry symlink、
  FIFO 与非 NFC entry 共八类均 fail closed。
- Gate：`ACC-S0-001` pre-publish 条件、`ACC-S0-002`–`ACC-S0-004`、`ACC-S0-006` PASS；
  `ACC-S0-001` post-commit 条件留给 Publish；`ACC-S0-005` 因不可执行 Oracle FAIL；`ACC-S0-007`
  因 ledger 新增 OPEN finding FAIL。
- Non-goals：未整改 `S0-R012`、未进入 Stage 1、未提交或上传。

## 已完成 Task 合同：BSS-S0-P2-T010

- 目标：只整改 `S0-R012`，建立无环、可重建的 release/manifest 所有权和最终封印顺序。
- 整改基线：`ba02b3fe38760464fa5e88ea9bfdec9bd4949341865ddb7f2fec5e6b5aabdf6e`。
- Hash DAG：task files → task manifest → release → release SHA → `SHA256SUMS`/registry；outer project
  稳定后最后生成 backup manifest。task manifest 不再承担其 Root 外的 release SHA。
- 首次登记：Registry Prep 不写入无法验证的 active 条目；Release/Activate 在真实 SHA 产生后原子落盘
  registry 与三个 hash 消费面，避免任何已完成 Task 声称不存在的 release 已通过验证。
- 封印协议：Release/Readiness 仅产候选；各 Stage Publish 在 Review PASS 后先冻结全部 tracked source，
  再渲染 derived artifacts，并在上传前从 staged tree/拟提交树 clean replay；seal 后禁止改 source。
- 终态证据：commit/push/PR/CI/merge/cleanup 是外部叶子，不反写 release，也不得在发生前预写 `DONE`；
  失败时停留在同一 Publish Task 并重新封印，不得进入下一 Task。
- Builder 状态：`S0-R012` 为 `FIXED_PENDING_REREVIEW`，不得由本 Task 自行关闭。
- Non-goals：未执行 T011 整体重审、未实现 builder/registry、未进入 Stage 1、未提交或上传。

## 已完成 Task 合同：BSS-S0-P2-T011

- 目标：在锁定整改后 subject 上复验完整 Stage 0、`S0-R012`、全部历史 finding 与七个 Stage 0 ACC。
- Reviewed subject：`f17ad7dfaa2088f645e37a88ce415ee3d0e672ebe07361b1f69d9a810a7636ad`。
- Verdict：`PASS`。
- 已关闭：`S0-R012`；`S0-R001`–`S0-R011` 回归 PASS；ledger 状态集合精确为 `CLOSED`。
- 完整性：仓库 validator 对 manifest `7/7` PASS；Task Graph 为 52 个唯一 Task、`ACTIVE=0`；
  44 个 ACC、23/9/7 Source 覆盖、Producer/Verifier 顺序与全部 Oracle/Evidence PASS。
- Digest：Python 规范实现与独立 Ruby 实现同为 reviewed subject；缺 Root、Root file、Root symlink、
  缺/非法 manifest、entry symlink、FIFO、非 NFC entry 八类负例全部 fail closed。
- `S0-R012`：DAG cycle check、外部证据反向边负例、双 ZIP build、file set、release SHA 三消费面、
  backup-last、registry 真实 SHA 激活与 proposed-tree replay 全部 PASS。
- Gate：`ACC-S0-001` pre-publish 条件与 `ACC-S0-002`–`ACC-S0-007` Stage Review 条件 PASS；
  `ACC-S0-001` post-commit 与 `ACC-S0-007` Publish 前置复验仍由 `BSS-S0-P3-T001` 完成。
- 动态基线：`origin/main` 比当前 task branch 前进 3 个仅涉及 `arxiv-daily-push/` 的提交；Publish 必须
  在 seal 前 fetch 并把任务分支安全更新到最新 `origin/main`，重新核对 scoped diff 与 proposed merge tree。
- Non-goals：未执行 Stage 0 Publish、未进入 Stage 1、未提交或上传。

## 下一个许可动作

唯一允许的下一 Task 是 `BSS-S0-P3-T001 — Stage 0 Publish`。它必须先同步最新 `origin/main` 并确认上游
3 个提交与本项目无路径冲突，再按 seal 协议刷新评审证据/manifest、物化并重放拟提交树、创建唯一 Stage 0
commit、push 并创建 draft PR；远端 diff、PR 状态或 post-commit clean 任一失败时不得进入 Stage 1。
