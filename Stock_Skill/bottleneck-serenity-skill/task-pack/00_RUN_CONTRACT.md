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
- 当前 Stage：`S1 — Registry version-model capability`
- 最近完成 Task：`BSS-S1-P3-T009 — Whole Stage 1 re-review 4`
- 下一许可 Task：`BSS-S1-P4-T001 — Stage 1 Publish`
- 状态：`STAGE_1_REVIEW_PASSED_READY_TO_PUBLISH`

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
- Stage Review 必须绑定评审前的 Task Pack 与完整 Stage source 两个规范 digest；Stage Publish 必须绑定
  manifest 与 Git commit。Stage 0 历史 Review 只适用当时已封印的 Task Pack 协议；Stage 1 起两者缺一即失败。
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

### 完整 Stage source digest：`stage-worktree-source-sha256-v1`

从 Stage 1 起，每次 Review/Re-review 在修改任何 subject 文件前，还必须从仓根运行：

```bash
python3 -B Stock_Skill/scripts/digest_stage_source.py
```

`Stock_Skill/scripts/digest_stage_source.py` 是本协议的规范可执行定义，合同如下：

- 仓根必须精确等于 Git top-level，base 必须是完整 `HEAD^{commit}` OID；Git index 相对 HEAD 必须为空且
  不得有 unmerged entry，避免 reviewed worktree 与 staged proposal 分叉。
- Subject path 集合精确等于 `git -c core.fileMode=true diff --no-renames --name-only HEAD` 的 tracked
  变化与 `git ls-files --others --exclude-standard` 的未跟踪文件之并集；使用 NUL 分隔。集合为空即失败，
  因而 registry、validator、tests、docs、workflow、Task Pack 或其他 Stage 改动都不能静默漏出 subject。
- 路径必须是唯一、UTF-8、Unicode NFC、规范 POSIX 仓根相对路径；现存项必须是仓内非 symlink 普通文件。
  tracked 删除项必须在 base 中是 blob；目录、submodule、symlink、socket、device、FIFO、越界或歧义均失败。
- 先写 base frame：`BASE + NUL + base_oid_ascii + NUL`。按 path UTF-8 bytes 升序，对现存文件写
  `F + NUL + path + NUL + git_mode + NUL + bytes + NUL`，其中 mode 只能为 `100644/100755`，且仅当
  POSIX owner execute bit（`stat.S_IXUSR`）存在时才映射为 `100755`，与 Git staged-tree 语义一致；删除写
  `D + NUL + path + NUL`。对完整字节流计算 SHA-256。
- Review ledger 必须同时记录 `BASE_HEAD`、`SUBJECT_PATHS`、本 digest 与 `taskpack-tree-sha256-v1`；另用
  独立实现复算相同结果。byte/mode/delete/untracked 任一变化都必须改变 digest；index dirty（包括
  intent-to-add）、空 subject、symlink 或非法路径必须非零退出。

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

## 已完成 Task 合同：BSS-S0-P3-T001

- 目标：从 Stage Review PASS 的 frozen subject 封印并上传完整 Stage 0，不在 Publish 后反写外部叶子证据。
- Commit：`287488a303d2da06fbfbe8d9f7195e603855ca70`；parent 与当时最新 `origin/main`
  `0704f48b26364067842def6d35ef11db4f08982b` 相等，commit 后 worktree 干净。
- Seal：8 个 Task Pack 文件、manifest `7/7`、review ledger `12/12 CLOSED`；Python 与独立 Ruby
  `taskpack-tree-sha256-v1` 均为
  `8ace45d47d365aab21f2aec46c6db5b5a1c092232645f9397b9564c5b61bdeb3`；proposed-tree replay PASS。
- Remote：branch `bottleneck-serenity-skill` 的 SHA 与本地相等；draft PR
  `https://github.com/LinzeColin/MetaDatabase/pull/76` 为 `OPEN`、base=`main`、head 正确、8-file diff
  与本地逐项相等，`dual-plane` check `SUCCESS`。
- 回填依据：以上外部证据由下一 Stage 首个本地 Task `BSS-S1-P1-T001` 重新查询后确认，因此现在才把
  `BSS-S0-P3-T001` 更新为 `DONE`；未改写已上传的 Stage 0 commit。

## 已完成 Task 合同：BSS-S1-P1-T001

- 目标：冻结 registry schema `1.1` 的显式版本模型与迁移兼容边界，不提前实施下一 Task。
- Schema：每个 Skill entry 必须显式声明大小写敏感的 `version_scheme`，唯一允许值为 `semver` 或
  `numeric-quad`；缺失、未知、错误类型与跨 scheme 比较全部 fail closed。
- 语法：`semver` 保持现 validator 的 canonical 三段数字子集；`numeric-quad` 使用四段非负整数，除单个
  `0` 外禁止前导零；机器字段无 `v`，展示/release 加 `v`，`A-001` 由本 Task 锁定。
- 兼容：下一 Task 必须原子升级 schema/validator 并只给现有 entry 新增
  `"version_scheme": "semver"`；去掉该新增字段后的 canonical JSON SHA-256 必须仍为
  `41232c50c051ebc4b5d2e9503bba6c938b8b6e83f81f69bd322ccfdaeeaf98a0`。
- Archive：`superseded_archives` 仍为必需数组但允许为空；archive 继承父 entry 的 scheme，只能在同
  scheme 内解析和按整数 tuple 比较，必须唯一且严格早于 latest。
- Non-goals：未修改 active registry、validator、tests、文档或 CI，未登记新 Skill，未 commit/push。

## 已完成 Task 合同：BSS-S1-P1-T002

- 目标：按冻结设计原子升级 active registry 与 validator，不跨入隔离测试、文档或 CI Task。
- Registry：`schema_version` 从 `1.0` 升为 `1.1`，`updated_at` 更新为 `2026-07-22`，现有唯一 entry
  只新增 `"version_scheme": "semver"`；没有登记 `bottleneck-serenity-skill` 或占位制品。
- Validator：实现 `parse_version`、`compare_versions` 与 `validate_version_model` 纯函数；严格支持
  canonical 三段 `semver` 和四段 `numeric-quad`，拒绝未知/跨 scheme、非字符串、错误 arity、前导零、
  boolean/错误 major，以及 archive 自行声明 scheme；`superseded_archives=[]` 合法，缺失/非数组失败。
- 输出兼容：现有 semver 继续输出 `CURRENT: stock-commercial-opportunities=3.0.0 (v3)`；未来
  numeric-quad 使用完整 `v<latest_version>`，不会把 `0.0.0.1` 错写成 `v0`。
- Preservation：迁移后 entry 仅移除新增 `version_scheme` 的 canonical JSON 与迁移前逐字段相等，
  SHA-256 仍为 `41232c50c051ebc4b5d2e9503bba6c938b8b6e83f81f69bd322ccfdaeeaf98a0`；root 除
  `schema_version/updated_at` 外逐值相等，数组顺序不变。
- 回归：active registry validator PASS；current release 与 archive `[0]/[1]` 实算 SHA 分别仍为
  `3cc89dc510e33c9e341c18e7925c219dda3218c7947f4341414f0c3cba2a0c6d`、
  `01c3d8b069d488cddb4fa3c85959a89bd9b5d072c4b1437cced03073e0442fc4`、
  `73f6934529b401a33271e8bc2f2bf7c89979a2dbb56e92e5abb4e8ff2fc40792`。
- Non-goals：未新增 `Stock_Skill/tests/`、未修改根/Stock Skill 文档或 workflow，未 commit/push。

## 已完成 Task 合同：BSS-S1-P2-T001

- 目标：为 schema `1.1` 和 validator 建立可重复、隔离且 fail-closed 的 durable unittest，不修改 active
  registry/制品或跨入文档/CI Task。
- Artifact：新增 `Stock_Skill/tests/test_validate_registry.py`，共 10 个 unittest；每个 filesystem case
  在 `TemporaryDirectory` 内复制当前 validator，构建具备真实 project/Skill identity、version sources、
  claim paths、release/archive SHA256SUMS、task/backup manifests 与 UI metadata 的最小完整仓库，再启动
  临时 validator CLI，未用 marker/string 检查替代行为。
- Success：覆盖现有 `semver=3.0.0` + v2/v1 lineage，以及
  `numeric-quad=0.0.0.1` + `superseded_archives=[]`；同时断言 stdout 分别保留 `(v3)` 与完整
  `(v0.0.0.1)`。
- Fail closed：覆盖缺失/未知/错误类型 scheme，缺失/错误 arity/前导零/前后缀 version，boolean/string/
  错误 major，缺失/null/object/string archives，非 object archive、等于 latest、跨 scheme arity、重复
  archive、archive 自声明 scheme，以及缺失/legacy/未知/错误类型 root schema 和非 object root。
- Isolation：每个测试前后比较 active registry、validator、current release 与两个 archive 的 SHA-256；
  10/10 PASS，active registry validator 继续 PASS，现有 entry projection hash 仍为
  `41232c50c051ebc4b5d2e9503bba6c938b8b6e83f81f69bd322ccfdaeeaf98a0`。
- Non-goals：未修改根/`Stock_Skill` 发现文档、未创建 workflow，未进入 Stage Review，未 commit/push。

## 已完成 Task 合同：BSS-S1-P2-T002

- 目标：同步四个 canonical 发现面，使 schema `1.1`、两种 version scheme、版本展示、空 archive 与
  fail-closed 口径和 active registry/validator 一致，不跨入 CI 或 Review。
- Artifacts：更新仓根 `AGENTS.md`/`README.md` 与 `Stock_Skill/AGENTS.md`/`README.md`；四者均声明
  `version_scheme` 为必需且仅允许 `semver`/`numeric-quad`、固定 arity/无前导零、严格 `latest_major`、
  同 scheme tuple 比较，以及必需但可为空的 `superseded_archives`。
- Current/planned boundary：继续唯一声明 active
  `stock-commercial-opportunities=3.0.0`（`semver`，validator label `v3`）；明确
  `bottleneck-serenity-skill=0.0.0.1`（`numeric-quad`，完整 label `v0.0.0.1`，首版 `[]`）仅是待 Stage 2
  原子激活合同，不得凭目录或 Task Pack 声称已登记/current。
- Fail closed：四个发现面均要求缺失/未知 scheme、错误 arity/类型/major、前导零、archive 自声明
  scheme、跨 scheme 比较或 identity/path/version/SHA/manifest 冲突时返回 `UNKNOWN`，不得推断或补零。
- Evidence：四文档契约断言 PASS；active registry validator PASS 并继续输出
  `CURRENT: stock-commercial-opportunities=3.0.0 (v3)`；registry 隔离 unittest 10/10、现有项目 unittest
  29/29 与 `git diff --check` 全部 PASS。
- Non-goals：未修改 registry/validator/Skill source 或制品，未创建 workflow，未进入 Stage Review，未
  commit/push。

## 已完成 Task 合同：BSS-S1-P2-T003

- 目标：新增 path-filtered Stock Skill workflow，把 Stage 1 已实现的 registry、tests、manifest/hash 与
  公开安全门转换为 PR/main 自动门，并证明本地等价命令 fail closed；不提前执行 Stage Review/Publish。
- Trigger/scope：新增 `.github/workflows/stock-skill-validation.yml`；`pull_request` 与 `push: main` 在
  `Stock_Skill/**`、根 `AGENTS.md`、根 `README.md` 或 workflow 自身变化时触发，另保留手动诊断入口；
  顶层权限仅 `contents: read`，checkout 不持久化凭据，不上传 artifact，也不写生产系统。
- Toolchain：Python 固定 `3.12`；`actions/checkout` v7.0.0 固定到
  `9c091bb21b7c1c1d1991bb908d89e4e9dddfe3e0`，`actions/setup-python` v6.3.0 固定到
  `ece7cb06caefa5fff74198d8649806c4678c61a1`；两个 SHA 均由官方 tag 实查确认。
- Gates：运行 active registry validator；自动发现并逐目录运行全部非 archive/release `test_*.py` 且零测试
  失败；验证全部 `*MANIFEST.sha256`/`SHA256SUMS` 的 canonical path、完整 file set 与实算 SHA；扫描根
  发现文档、全部 `Stock_Skill` 普通文件和 ZIP payload 的私钥/凭据/用户路径、ZIP path/type/size/encryption。
- Historical exception：只允许既有 immutable v1 谱系已披露的精确 token `/home/oai/skills`；其子路径、
  `file://` 形式或任何其他 `/home`/`/Users`/Windows 用户路径仍失败，避免把历史兼容扩大为通用豁免。
- Evidence：PyYAML 结构/语义合同和官方 checksum 后的 `actionlint v1.7.12` PASS；四个 workflow `run`
  block 原样本地重放，registry PASS、现有/隔离 unittest 29/29 + 10/10、3 manifests + 1 SHA256SUMS、
  70 files/195 blobs/125 ZIP entries 公开安全扫描全部 PASS；9-case 临时负向矩阵证明零测试、失败测试、
  hash mismatch、路径穿越、用户路径、历史例外子路径与 ZIP 内合成凭据均非零退出。
- Non-goals：真实 GitHub workflow check 只能在 Stage 1 Review PASS 后的 Publish push 验证；本 Task 未执行
  Review/Remediation、未 commit/push，未登记新 Skill 或修改制品。

## 已完成 Task 合同：BSS-S1-P3-T001

- 目标：在任何 subject 文件改动前冻结身份并整体复审 Stage 1 的设计、registry/validator、隔离测试、
  四个发现文档、workflow、兼容性、回归和六个 Stage 1 ACC；本 Task 只记录 verdict/finding 与确定性路由。
- 冻结身份：branch=`bottleneck-serenity-skill`、HEAD=
  `287488a303d2da06fbfbe8d9f7195e603855ca70`；规范 `taskpack-tree-sha256-v1` 为
  `20a648cb164947a76961a385ff0837fbbe5fc866e6024d443769eea1e10062f4`。补充审计把 14 个 Stage 1 changed
  path 按 UTF-8 path 排序并以 `path + NUL + bytes + NUL` framing，得到
  `50dcefd0f489f96aebbbe09baab099db3bc6d75593e1fb41bbc2718f43b4a9c1`；它尚不是合同中的规范协议。
- 通过项：active registry validator PASS；现有 entry preservation projection 仍为
  `41232c50c051ebc4b5d2e9503bba6c938b8b6e83f81f69bd322ccfdaeeaf98a0`；release/v2/v1 SHA 均与声明相等；
  workflow 四个原始 run block 重放 PASS（29+10 tests、3 manifests、1 SHA256SUMS、70 files/195 blobs/125
  ZIP entries）；四发现文档一致；Task Graph 52 个唯一 ID、追溯表 44 ACC 与 23/9/7 Source 集合全部 PASS。
- Verdict：`FAIL`。`ACC-S1-001/002/003/005` PASS；`ACC-S1-004` 因 `S1-R004` FAIL；
  `ACC-S1-006` 因 `S1-R002/S1-R003` FAIL；`S1-R001` 另阻断整体 Review 证据完整性。
- Findings：`S1-R001` 规范 subject digest 只覆盖 Task Pack、未绑定 8 个外部 Stage source 面；
  `S1-R002` workflow 以 test file 数代替实际 case 数，单个空 `test_empty.py` 得到 `Ran 0 tests` 仍 exit 0；
  `S1-R003` 公开安全门未识别 GitHub 官方 `github_pat_` fine-grained PAT 前缀，合成凭据探针仍 exit 0；
  `S1-R004` 合同声称覆盖 non-object archive，但删除该拒绝分支的 mutant 仍通过现有 10/10 tests。
- 路由：按确定性复审循环启用 `BSS-S1-P3-T002/T003` 为 `PENDING`；唯一下一 Task 是 T002，四个 finding
  均保持 `OPEN`，只能由 T002 改为 `FIXED_PENDING_REREVIEW`，再由 T003 在新 subject 上关闭。
- Non-goals：本 Task 未修复 workflow/validator/tests，未进入 Publish，未 commit/push，也未登记或安装 Skill。

## 已完成 Task 合同：BSS-S1-P3-T002

- 目标：只整改 Stage 1 review 的 `S1-R001`–`S1-R004`，建立可由下一 Task 独立重审的 durable Oracle；
  Builder 不关闭 finding、不执行 T003 或 Publish。
- `S1-R001`：新增规范 `stage-worktree-source-sha256-v1` 与标准库可执行真源
  `Stock_Skill/scripts/digest_stage_source.py`。协议绑定 base HEAD、完整 tracked/untracked Stage path 集、
  bytes、Git mode 与删除；index dirty、empty、symlink/unmerged/非普通/非法路径 fail closed。六个隔离测试覆盖
  bytes/determinism/untracked、mode、delete、empty、index 与 symlink；T003 必须在改动 subject 前双实现复算。
- `S1-R002`：workflow 改为调用 `scripts/run_unittests.py`；每个 test directory 在隔离子进程中加载 suite，
  使用 `countTestCases()` 要求实际 case 数大于零，并验证唯一正数 marker。空 test file 与失败 case 的 durable
  fixture 均非零退出，现有全部 suite 报告真实 case 总数。
- `S1-R003`：workflow 改为调用 `scripts/validate_public_safety.py`；扫描普通文件与 ZIP payload 时新增
  GitHub 官方 `github_pat_` fine-grained PAT 模式。普通文件和压缩 ZIP 合成凭据均失败；精确反引号历史路径
  仍通过，其 child 仍失败，未扩大既有 allowlist。
- `S1-R004`：`test_validate_registry.py` 新增 archive list 中 `null/string/list` 三个非 object CLI fixture；
  删除 validator 对应拒绝分支的 mutant 产生三项 test failure，证明该分支已被测试保护。
- 受影响回归：registry PASS；Stock Skill 共 52 个真实 unittest case（29+23）PASS；公开安全扫描、workflow
  四个原始 run blocks、3 manifests + 1 SHA256SUMS、PyYAML 语义检查、官方 checksum 的 actionlint v1.7.12
  与 `git diff --check` PASS。真实 GitHub check 仍只属于 Stage Publish。
- Builder 状态：四个 finding 均为 `FIXED_PENDING_REREVIEW`；Producer 依据完整能力首次成立规则转移到本
  Task，只有 `BSS-S1-P3-T003` 可在新双 digest subject 上改为 `CLOSED`。
- Non-goals：未改 active registry、研究核心逻辑或 Skill/release；未执行整体重审、commit/push、Stage 2
  或本机安装。

## 已完成 Task 合同：BSS-S1-P3-T003

- 目标：在任何 subject 文件改动前冻结双 digest，并独立复验完整 Stage 1、`S1-R001`–`S1-R004`、六个
  Stage 1 ACC 与 `ACC-S0-006` 的新增完整 Stage source digest 门；只记录 verdict/finding/closure 和确定性路由。
- 冻结身份：branch=`bottleneck-serenity-skill`、base HEAD=
  `287488a303d2da06fbfbe8d9f7195e603855ca70`、subject paths=`20`；Python 规范实现与独立 Ruby 实现得到
  相同 `taskpack-tree-sha256-v1`=
  `7380b917d699a63300ca461a98a033a49a6ee699eb45b1032fd726bf6475d9dd`，以及相同
  `stage-worktree-source-sha256-v1`=
  `bc429110668964ba654d091462f36ff0a783c5f16d9073038ca60be2c0caaab6`。
- 正向证据：active registry、legacy projection 与 v3/v2/v1 制品 SHA 无漂移；52 个真实 unittest case、
  3 manifests + 1 SHA256SUMS、75 files/200 blobs/125 ZIP entries 基线扫描、四个 workflow 原始 run blocks、
  PyYAML 语义、官方 checksum 的 actionlint v1.7.12、四发现文档、44 ACC/23 REQ/9 CAP/7 NG 追溯和
  non-object archive mutant kill 均 PASS。`S1-R002`、`S1-R003`、`S1-R004` 因原失败 Oracle 现已反转并
  有 durable 保护而 `CLOSED`。
- 未关闭既有 finding：`S1-R001` 仍为 `OPEN`。临时 Git 仓执行 `git add -N intent.txt` 后，porcelain 明确
  存在 intent-to-add index entry，但 `git diff --cached --quiet HEAD` 和 digest helper 都 exit 0；因此合同的
  “index 必须为空”并未 fail closed，`ACC-S0-006` FAIL。
- 新增 P1 finding：`S1-R005` 的 ZIP `..\\escape.txt` 路径、`S1-R006` 的含 DEFLATED 凭据 payload 的目录
  entry、`S1-R007` 的当前 `ghs_APPID_JWT` GitHub App installation token，以及 `S1-R008` 的无尾分隔符
  macOS/Linux/Windows user-home 路径均被公开安全 helper exit 0 放行。`S1-R007` 的格式与 2026 rollout 由
  [GitHub 官方说明](https://github.blog/changelog/2026-04-24-notice-about-upcoming-new-format-for-github-app-installation-tokens/)
  直接证明；四项均违反已冻结的 credential/user-path/ZIP path/payload 门，使 `ACC-S1-006` FAIL。
- Verdict：`FAIL`。`ACC-S1-001`–`ACC-S1-005` PASS；`ACC-S1-006` 与 `ACC-S0-006` FAIL。Stage 1 禁止
  Publish。
- 路由：同一 review Phase 已无未使用条件 Task 对，按最大 suffix+1/+2 追加
  `BSS-S1-P3-T004/T005` 为 `PENDING`；唯一下一 Task 是 T004，只能把五个 OPEN finding 推进到
  `FIXED_PENDING_REREVIEW`，再由 T005 在新双 digest subject 上关闭。
- Non-goals：未整改 digest/public-safety helper 或 tests，未 commit/push、未进入 Publish/Stage 2，也未
  登记、安装或生成 Skill/release。

## 已完成 Task 合同：BSS-S1-P3-T004

- 目标：只整改 T003 未关闭的 `S1-R001/S1-R005/S1-R006/S1-R007/S1-R008`，建立下一 Task 可独立复验的
  durable 正负 Oracle；Builder 不关闭 finding、不执行 T005 或 Publish。
- `S1-R001`：cached index diff 显式使用 `--ita-visible-in-index`，避免 Git 默认隐藏 intent-to-add entry；新增
  真实临时仓 `git add -N` 行为测试，与普通 staged index 一样必须返回“index must be empty”。
- `S1-R005`：ZIP entry name 只接受 canonical POSIX `/`；拒绝任意反斜杠、drive-relative/absolute 前缀、
  UNC 与既有 absolute/traversal 变体。durable matrix 覆盖 `..` 反斜杠、两种 drive 写法、UNC 和内部
  反斜杠。
- `S1-R006`：所有合法 ZIP entry 在 type gate 后都进入 uncompressed size accounting；directory entry
  必须 `file_size=0`，含 DEFLATED credential payload 的目录非零失败，同时空目录加普通文件正例通过。
- `S1-R007`：按 GitHub 官方 2026 rollout 的 `ghs_APPID_JWT` 结构新增 stateless App installation token
  模式，普通文件与 DEFLATED ZIP payload 两个行为 fixture 均失败；既有 opaque `ghs_` 和其他 GitHub token
  规则保持不变。
- `S1-R008`：macOS/Linux/Windows user-home regex 同时覆盖 home 本身与 child，并要求用户名至少一个非点
  字符；三平台 bare-home fixture 均失败，文档 ellipsis placeholder 继续通过。历史例外仍只允许精确反引号
  `/home/oai/skills`；unbackticked、`file://` 与 child 继续失败。
- Evidence：整改前 9 个探针均错误 exit 0；整改后扩展的 11 个独立负向探针均非零。20 个目标行为测试、
  全部 60 个真实 unittest case（29+31）、active registry、3 manifests + 1 SHA256SUMS、75 files/200 blobs/
  125 ZIP entries 基线扫描、四个 workflow 原始 run blocks 与 `git diff --check` PASS。
- Builder 状态：五项 finding 均为 `FIXED_PENDING_REREVIEW`；只有 `BSS-S1-P3-T005` 可在新双 digest subject
  上改为 `CLOSED`。
- Non-goals：未改变 registry/version model、Skill/release 或研究核心逻辑；未执行整体重审、commit/push、
  Publish/Stage 2 或本机安装。

## 已完成 Task 合同：BSS-S1-P3-T005

- 目标：在任何 subject 文件改动前冻结新双 digest，独立重审五项待关闭 finding、完整 Stage 1、
  `ACC-S0-006` 与全部回归；本 Task 只记录 verdict/closure/finding/路由，不整改或 Publish。
- 冻结身份：branch=`bottleneck-serenity-skill`、base HEAD=
  `287488a303d2da06fbfbe8d9f7195e603855ca70`、subject paths=`20`；规范 Python 与独立 Ruby 实现同得
  `taskpack-tree-sha256-v1`=
  `97cc05b82160dd3899462ff09f973124e9b8882f07e509926678bf6155d281aa`，以及
  `stage-worktree-source-sha256-v1`=
  `664bd0415acff4c72a59f2abe47739445a615452b3e8b641a1abfc2127382f15`。评审结束前复算无漂移。
- 原 finding closure：`S1-R001/R005/R006/R007/R008` 的原失败 Oracle 全部反转，五个回退 mutant 均被
  独立行为矩阵杀死。intent-to-add 非零；11 类 ZIP path、非空目录与 size accounting、三种 JWT 尾部的
  plain/ZIP token、三平台标准 bare/child home 与历史例外边界均符合预期，因此五项 `CLOSED`。
- 正向证据：active registry、legacy projection 与 v3/v2/v1 SHA 无漂移；60 个真实 unittest case、
  3 manifests + 1 SHA256SUMS、75 files/200 blobs/125 ZIP entries 基线扫描、四个 workflow 原始 run blocks、
  PyYAML、官方 tag SHA、官方 checksum 的 actionlint v1.7.12、44 ACC/23 REQ/9 CAP/7 NG 追溯、20-path
  scope/index/mode/cache 与 main tree 边界全部 PASS。
- 新增 `S1-R009`（P1）：公开安全 user-home matcher 仍大小写敏感且用户名限定 ASCII；macOS/Windows
  case 变体及三平台全 Unicode 用户名在普通文件和 DEFLATED ZIP 共 12 个探针均 exit 0，违反
  `ACC-S1-006` 的用户路径 fail-closed 门。
- 新增 `S1-R010`（P1）：Stage digest 用任一 execute bit 映射 `100755`，而 Git 只按 owner execute bit
  决定 executable mode；临时 `0654` 新文件被 helper 记为 `100755`、Git staged tree 为 `100644`，使
  `ACC-S0-006` 的完整拟提交树绑定不精确。
- Verdict：`FAIL`。`ACC-S1-001`–`ACC-S1-005` PASS；`ACC-S1-006` 因 `S1-R009` FAIL，`ACC-S0-006`
  因 `S1-R010` FAIL。Stage 1 继续禁止 Publish。
- 路由：按最大 suffix+1/+2 追加 `BSS-S1-P3-T006/T007` 为 `PENDING`；唯一下一 Task 是 T006，只能把
  `S1-R009/R010` 推进到 `FIXED_PENDING_REREVIEW`，再由 T007 在新双 digest subject 上关闭。
- Non-goals：未修复 helper/regex/tests，未 commit/push、未执行 Publish/Stage 2，未登记、安装或生成
  Skill/release。

## 已完成 Task 合同：BSS-S1-P3-T006

- 目标：只整改第三轮 Stage 1 重审新增的 `S1-R009/R010`，补充 durable 行为与回退 mutant Oracle；Builder
  不关闭 finding，也不跨入 T007、Publish、commit/push 或 Stage 2。
- 整改基线：独立复现 case/Unicode user-home 的普通文件与 DEFLATED ZIP 共 12/12 个探针错误 exit 0；
  `0654` 新文件被旧 Stage helper 映射为 `100755`，而 Git staged mode 为 `100644`。
- `S1-R009`：macOS 与 Windows user root 按平台语义大小写不敏感，Linux `/home/` 保持大小写敏感；用户段
  支持 UTF-8 非 ASCII 字符。三平台 bare/child、case/Unicode 的 plain/ZIP fixture 均 fail closed；只由
  `.`/`…` 构成的文档用户名占位继续通过，精确反引号 `/home/oai/skills` 历史例外边界不变。
- `S1-R010`：`digest_stage_source.py` 只按 owner execute bit（`stat.S_IXUSR`）映射 Git mode；`0644` 与
  group-only execute 的 `0654` digest 相等且 staged mode=`100644`，`0755` digest 不同。
- Evidence：8 个 Stage digest 测试与 14 个 CI helper 测试共 22/22 PASS；全部 62 个真实 unittest case、
  3 manifests + 1 SHA256SUMS、75 files/200 blobs/125 ZIP entries 公开扫描、四个 workflow 原始 run blocks
  与 `git diff --check` PASS。整改后原 12 个漏检探针全部非零，5 个 placeholder/历史正例通过且历史 child
  仍失败；回退 case/ASCII mutant 被 10 个 subtest failure 杀死，任一 execute-bit mutant 被新 mode 测试杀死。
- Builder 状态：`S1-R009/R010` 均为 `FIXED_PENDING_REREVIEW`；只有 `BSS-S1-P3-T007` 可在新双 digest
  subject 上关闭并重判 Stage 1 gate。
- Non-goals：未执行 T007、Publish、commit/push 或 Stage 2；未登记、安装、迁移或生成 Skill/release。

## 已完成 Task 合同：BSS-S1-P3-T007

- 目标：在任何 subject 文件改动前冻结新双 digest，独立复验 `S1-R009/R010`、全部既有 Stage 1 finding、
  完整 Stage 1 gate 与 `ACC-S0-006`；本 Task 只记录 verdict/closure/finding/路由，不整改或 Publish。
- 冻结身份：branch=`bottleneck-serenity-skill`、base HEAD=
  `287488a303d2da06fbfbe8d9f7195e603855ca70`、subject paths=`20`；规范 Python 与独立 Ruby 实现同得
  `taskpack-tree-sha256-v1`=
  `01de05cc56ec1fff7e46e1b18a732b5ca25dc9fc5be3b5dfb264264236f37bc1`，以及
  `stage-worktree-source-sha256-v1`=
  `10b429e25764e43da5a1d97a0ed2d11d7b0bdba851b05d00f8f659af9c6cad22`。评审结束前复算无漂移。
- Closure：`S1-R009` 的原 12 个 plain/DEFLATED ZIP case/Unicode 探针全部非零且标签正确，额外 5 个
  mixed-case/decomposed/emoji 探针非零，6 个合法 placeholder/平台正例与 4 个历史反例符合预期；回退
  case-sensitive/ASCII mutant 被 10 个 subtest failure 杀死。`S1-R010` 的 16-mode Git/helper 矩阵全部
  一致，regular/executable digest 分离，任一 execute-bit mutant 被 durable mode 测试杀死。因此两项 `CLOSED`，
  `ACC-S0-006` PASS。
- 回归证据：`S1-R001`–`S1-R008` 的 10 个行为 mutant 全部被无 error 杀死；active registry、legacy
  projection 与 v3/v2/v1 SHA 无漂移；62 个真实 unittest case、3 manifests + 1 SHA256SUMS、
  75 files/200 blobs/125 ZIP entries 基线扫描、四个 workflow 原始 run blocks、PyYAML 语义合同、官方 tag
  SHA、官方 checksum 的 actionlint v1.7.12、四发现文档、44 ACC/23 REQ/9 CAP/7 NG 追溯、20-path
  scope/index/cache/runtime/main 与 remote/PR 边界全部 PASS。
- 新增 `S1-R011`（P1）：历史路径 allowlist 只验证精确路径后紧跟 closing backtick，没有验证 closing
  backtick 之后不能继续组成路径或 token。closing backtick 后分别追加 `/private`、反斜杠 child 与紧接
  suffix，在
  普通文件和 DEFLATED ZIP 共 6/6 个探针均 exit 0；而精确正例通过、反引号内 child 失败，证明是 allowlist
  右边界 fail-open，违反 `ACC-S1-006` 的精确历史例外合同。
- Verdict：`FAIL`。`ACC-S1-001`–`ACC-S1-005` 与 `ACC-S0-006` PASS；`ACC-S1-006` 因 `S1-R011` FAIL。
  Stage 1 继续禁止 Publish。
- 路由：按最大 suffix+1/+2 追加 `BSS-S1-P3-T008/T009` 为 `PENDING`；唯一下一 Task 是 T008，只能把
  `S1-R011` 推进到 `FIXED_PENDING_REREVIEW`，再由 T009 在新双 digest subject 上关闭。
- Non-goals：未修复 allowlist/helper/tests，未 commit/push、未执行 Publish/Stage 2，未登记、安装或生成
  Skill/release。

## 已完成 Task 合同：BSS-S1-P3-T008

- 目标：只整改 `S1-R011`，收紧精确历史路径 allowlist 的 closing-backtick 右边界并增加 durable 行为与
  回退 mutant Oracle；Builder 不关闭 finding，也不跨入 T009、Publish、commit/push 或 Stage 2。
- 整改基线：独立复现 closing backtick 后分别追加 slash、反斜杠与 token suffix 的普通文件 3/3、
  DEFLATED ZIP 3/3 探针错误 exit 0；精确 token 通过而反引号内 child 失败，定位为右边界单点 fail-open。
- 修复：closing backtick 后只允许 EOF、Unicode whitespace 或显式句末/闭合标点；slash、反斜杠、ASCII/
  Unicode token、下划线、连字符、数字与 `@` continuation 均 fail closed；无法解码的 UTF-8 首字符也不豁免。
- Durable evidence：新增 8 类 continuation 的 plain/DEFLATED ZIP 双矩阵，16/16 均非零且标签正确；4 类
  EOF/whitespace/句末或闭合标点正边界通过，反引号内 child 继续失败。目标 CI helper 15/15 PASS；移除
  右边界检查的单点回退 mutant 被 16 个 behavioral failure、0 error 杀死。
- 全量证据：registry validator 与 legacy current 输出 PASS；全部 63 个真实 unittest case、3 manifests +
  1 SHA256SUMS、75 files/200 blobs/125 ZIP entries 公开扫描、四个 workflow 原始 run blocks 与
  `git diff --check` PASS。
- Builder 状态：`S1-R011` 仅推进为 `FIXED_PENDING_REREVIEW`；只有 `BSS-S1-P3-T009` 可在新双 digest
  subject 上关闭并重判 Stage 1 gate。
- Non-goals：未执行 T009、Publish、commit/push 或 Stage 2；未登记、安装、迁移或生成 Skill/release。

## 已完成 Task 合同：BSS-S1-P3-T009

- 目标：在任何 subject 文件改动前冻结新双 digest，独立复验 `S1-R011`、全部既有 Stage 1 finding、
  完整 Stage 1 gate 与 `ACC-S0-006`；本 Task 只记录 verdict/closure/路由，不整改或 Publish。
- 冻结身份：branch=`bottleneck-serenity-skill`、base HEAD=
  `287488a303d2da06fbfbe8d9f7195e603855ca70`、subject paths=`20`；规范 Python 与独立 Ruby 实现同得
  `taskpack-tree-sha256-v1`=
  `91eada4c7cdffcaee519a78da9ff32250c5aabae817e3503a19582039f183433`，以及
  `stage-worktree-source-sha256-v1`=
  `a37cbceb6ef90746cd16b5313c35ae627c93ac369a68d78e78408b117f940782`。记录 verdict 前复算无漂移。
- Closure：`S1-R011` 的 8 类 closing-backtick continuation 在 plain/DEFLATED ZIP 共 16/16 均非零且
  标签正确；6 个 EOF/whitespace/句末或闭合标点正边界通过，unbackticked、file URI 与反引号内 child
  3/3 失败；移除右边界检查的回退 mutant 被 16 failures、0 errors 杀死。因此 `S1-R011` `CLOSED`。
- 回归证据：`S1-R001`–`S1-R010` 的 11 个独立回退 mutant variant 全部被纯 behavioral failure 杀死；
  16/16 mode 的 Git/helper owner-execute 映射一致。registry `1.0→1.1` diff 仅为 schema/date 与现有 entry
  新增 `semver`，legacy projection 与 v3/v2/v1 SHA 无漂移；四发现文档语义一致。
- 全量证据：63 个真实 unittest case、3 manifests + 1 SHA256SUMS、75 files/200 blobs/125 ZIP entries
  公开扫描、四个 workflow 原始 run blocks、PyYAML 语义合同、官方 tag SHA、官方 checksum
  `aba9ced2...0e6953f` 的 actionlint v1.7.12、44 ACC/23 REQ/9 CAP/7 NG 追溯、20-path
  scope/index/cache/runtime/main 与 PR 边界全部 PASS。远端 main 的 230-path 增量与本分支已提交路径及
  Stage subject 均零重叠，PR #76 为 open/draft、mergeable/clean。
- Verdict：`PASS`，无新增 finding；`ACC-S1-001`–`ACC-S1-005`、`ACC-S0-006` 与 `ACC-S1-006` 的本地
  Review portion PASS。`ACC-S1-006` 的真实新 workflow PR check 仍按合同由 Stage 1 Publish push 验证。
- 路由：ledger 23/23 `CLOSED`，唯一下一 Task 是 `BSS-S1-P4-T001`；它必须重新封印、proposed-tree
  replay、commit/push 并验证远端 Stage diff 与 CI，成功前不得进入 Stage 2。
- Non-goals：未执行 Publish、commit/push 或 Stage 2；未登记、安装、迁移或生成 Skill/release。

## 下一个许可动作

唯一允许的下一 Task 是 `BSS-S1-P4-T001 — Stage 1 Publish`。它必须完成全部 Stage 1 source/status 变更、
刷新 manifest 并冻结 source，从 staged/proposed tree 重放四道 workflow 门与 Stage seal，再统一
commit/push 到 draft PR、核对远端 diff 和真实 CI。任一步失败都留在同一 Publish Task 重新封印；成功前
不得进入 Stage 2。
