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
- 当前 Stage：`S2 — Canonical Skill migration and registration`
- 最近完成 Task：`BSS-S2-P4-T005 — Re-review 2`
- 下一许可 Task：`BSS-S2-P5-T001 — Publish`
- 状态：`STAGE_2_REVIEW_PASSED_READY_TO_PUBLISH`

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

## 已完成 Task 合同：BSS-S1-P4-T001

- 目标：在 Stage 1 Review PASS 后重新封印完整 source，完成 proposed-tree replay、统一 commit/push，
  并把 Git/PR/CI 作为不反写 seal 的外部叶子；本 Task 未进入 Stage 2。
- Seal：`taskpack-tree-sha256-v1`=
  `336ff05d5d56918a631fd12cc437bd140466d401bbcea3f2b36f192d500d570b`，
  `stage-worktree-source-sha256-v1`=
  `75b9bda170ca42d267e2d1b151ecea92fb8f977e48c2f3f0f9eb2d17320b22ab`；staged tree=
  `8ca5889b6126576d874a2f977537f4d5a55723e3`，相对 main 的 proposed merge tree=
  `ae6c8cf430d9c4d6ec77eafba55868027fe7519c`。
- Replay：current、staged 与 proposed-merge 三个快照均原样重放四道 workflow 门并 PASS：63 个真实
  unittest case、3 manifests + 1 SHA256SUMS、75 files/200 blobs/125 ZIP entries；registry/current
  preservation 与公开安全门无漂移。
- 外部叶子：commit `8308d170325c2ce35581d3fb757a2b731f7803dc` 已 push；本地 HEAD、remote branch
  与 draft PR #76 head 三者一致。PR 为 `OPEN`/`DRAFT`、merge state `CLEAN`，完整 21-path diff 与本地
  `origin/main...HEAD` 精确一致；`dual-plane` 与 `Stock Skill validation / validate` 两项真实 check 均
  `SUCCESS`。
- 回填：按无环封印合同，本行与 Task Graph 的 `DONE` 只能由下一 Stage 首个本地 Task
  `BSS-S2-P1-T001` 查询上述已发生证据后写入；未预写 commit/push/CI 结果。
- Non-goals：未登记、迁移、安装或生成新 Skill/release，未修改 active registry 当前项。

## 已完成 Task 合同：BSS-S2-P1-T001

- 目标：核验并回填 Stage 1 Publish 外部叶子；使用 `skill-creator` 初始化最终稳定 ID 的最小 canonical
  Skill 骨架，不导入源资源或提前执行后续迁移 Task。
- 输入边界：只读核对工作间六条铁律、仓根与 `Stock_Skill/AGENTS.md`、active registry/validator、
  T001 验收、源包最小清单，以及 PR #76/remote/CI 证据；未把输入包文件复制进仓库。
- 初始化：运行 `skill-creator/scripts/init_skill.py`，名称固定为 `bottleneck-serenity-skill`；未传
  `--resources` 或 `--examples`。canonical root 仅生成 `SKILL.md` 与 `agents/openai.yaml` 两个普通文件，
  没有空资源目录、示例或无关占位文件。
- 身份：目录 basename、frontmatter `name`、UI `display_name` 均精确为
  `bottleneck-serenity-skill`；frontmatter 仅含 `name`/`description`，default prompt 显式调用
  `$bottleneck-serenity-skill`，short description 满足 25–64 字符合同。
- Evidence：官方 `quick_validate.py` 输出 `Skill is valid!`；独立结构/YAML 断言验证精确两文件 surface、
  无 TODO/placeholder、frontmatter 与 UI identity 全部 PASS；active registry validator 继续 PASS，唯一
  current 仍为 `stock-commercial-opportunities=3.0.0 (v3)`。
- Non-goals：未执行 T002 import、T003 rename、T004 semantic parity、metadata/project/registry/release、
  Stage Review/Publish、commit/push 或任何本机 Skill runtime 安装。
- 停止条件：T001 已满足；唯一下一 Task 是 `BSS-S2-P1-T002 — Import`。

## 已完成 Task 合同：BSS-S2-P1-T002

- 目标：以输入归档的 53-entry 集合为权威真源，把 scripts/references/schemas/templates/evals/examples/tests
  原样导入 canonical Skill，并为每项建立唯一 import/migrate/exclude 决定；不执行身份改名。
- 输入封印：逻辑 artifact `input-archive.zip` SHA-256=
  `541fce14f8eaa4b73a8c170fc6f6bc0f8cd5aa509942fe2192bd8cddafd90815`，73,957 bytes；`unzip -t`
  PASS，精确 53 entries = 45 regular files + 8 directories，file payload 共 152,598 bytes。路径全部为
  UTF-8/NFC canonical POSIX relative path，无 duplicate、absolute、traversal、反斜杠、symlink 或非普通类型。
- Source baseline：输入包自带 validator PASS、9/9 unittest PASS、8 个 JSON 可解析；5 个脚本只导入
  Python 标准库，静态检查未发现网络、broker 或 order-execution capability。
- Inventory：首次创建外层 `SOURCE_INVENTORY.md` 作为 `ACC-S2-005` 的 Producer artifact，SHA-256=
  `01e0c912775649c72915751e7882779d9ad1d43c6903f1fe0d5e888a70962a94`。53 行的编号、顺序、path、type、
  mode 与 file SHA 精确等于归档清单；每行仅有一个决定，计数为 `IMPORT 43 / MIGRATE 9 / EXCLUDE 1`。
- Import：43 entries 为 36 files + 7 directories；目标七类 resource path 集合与归档子集精确相等，
  36 个文件 bytes/SHA 全等，7 个目录为 `0755`，5 个脚本为 `0755`，其余普通文件为 `0644`。
- Migration/exclusion：root、README、MANIFEST、SKILL、PROVENANCE、handoff、quickstart、build brief 与
  NOTICE 共 9 项迁往 stable-ID root、Task Pack 或后续外层项目文档；源 `VERSION=0.1.0` 因与冻结
  `0.0.0.1` 冲突而明确排除，不建立伪 archive。
- Canonical validation：官方 skill-creator quick validator、导入的 validator 与导入后 9/9 unittest
  均 PASS。旧身份基线为 14 个 canonical resource 文件中的 21 个 match：display-form token 15
  （token SHA-256=`25fd0e9c...8015`）、kebab-form token 5（`13b191ed...66e1`）、snake-form token 1
  （`15684214...f5f39a9`），作为 T003 的明确输入；本 Task 未修改这些 bytes。
- Repository regression：GitHub workflow 四个原始 `run` blocks 本地重放 PASS；active registry validator
  继续只输出 `stock-commercial-opportunities=3.0.0 (v3)`，全部 72 个真实 unittest case（7 files/3
  suites）、3 manifests + 1 SHA256SUMS，以及 114 files/239 blobs/125 ZIP entries 公开安全扫描全部 PASS。
- License boundary：输入包没有 LICENSE/COPYING；provenance 声明为原创综合且未复制列出的 Serenity 项目
  代码。本 Task 只记录该事实，最终 proprietary/attribution 结论仍由 `BSS-S2-P2-T002` 独立完成。
- Non-goals：未执行 T003 rename、T004 semantic parity、SKILL metadata 重构、外层项目工程化、registry、
  release、Review/Publish、commit/push 或任何本机 Skill runtime 安装。
- 停止条件：T002 已满足；唯一下一 Task 是 `BSS-S2-P1-T003 — Rename`。

## 已完成 Task 合同：BSS-S2-P1-T003

- 目标：只对 T002 导入的 canonical resources 执行机械身份迁移，不开展核心逻辑、阈值或版本影响审计。
- 冻结映射：上述 display-form 与 kebab-form token → `bottleneck-serenity-skill` 分别 15/5 处，snake-form
  token → `bottleneck_serenity_skill` 1 处；共 21 处、14 文件。旧 token 只以形态、计数和 SHA 记录，避免
  重新进入 current release payload。
- Forward-transform Oracle：逐一读取输入 ZIP 中 36 个导入文件，只应用上述三项有序 byte replacement；
  canonical 结果与 expected bytes、mode 和 path 全等，其中 14 文件发生身份转换，另 22 文件保持逐字节不变。
  资源树 framing 为 `relative_path + NUL + mode + NUL + payload + NUL`；source digest=
  `48f8724489953dad8ac174d8ce655058b1e1c98f75cc43e7c0f7c4527163960c`，expected/actual renamed digest 均为
  `ae21e31ba95c1334c352f522ffe8d2e98f20c0011219ada1c7e2a7e242316fb4`。
- Identity Oracle：canonical path 与内容中的大小写不敏感 `constraint[-_ ]alpha` 命中均为 0；调用只保留
  `$bottleneck-serenity-skill`；三个 schema `$id` 均迁到 `https://example.local/bottleneck-serenity-skill/`；
  completion event 精确且唯一为 `bottleneck_serenity_skill.thesis.completed`。
- History boundary：`SOURCE_INVENTORY.md` 未改写，SHA-256 仍为
  `01e0c912775649c72915751e7882779d9ad1d43c6903f1fe0d5e888a70962a94`；源 ZIP 路径、hash 与旧身份记录继续
  作为不可变迁移证据。
- Targeted validation：官方 skill-creator quick validator、导入 validator、9/9 imported unittest、8 个 JSON
  解析、score Markdown 与 portfolio JSON example parity、`git diff --check` 全部 PASS。
- Repository regression：GitHub Stock Skill workflow 四个原始 `run` blocks 本地重放 PASS；active registry
  current 无漂移，全部 72 个真实 unittest case（7 files/3 suites）、3 manifests + 1 SHA256SUMS，以及
  114 files/239 blobs/125 ZIP entries 公开安全扫描全部通过。
- Non-goals：未执行 T004 semantic parity 独立审计，未修改通用 `constraint`/`alpha`/`Serenity` 术语、评分或
  硬门逻辑；未执行 metadata/project/registry/release、Stage Review/Publish、commit/push 或本机 runtime 安装。
- 停止条件：T003 验证与 Task Pack 封印完成后停止；唯一下一 Task 是
  `BSS-S2-P1-T004 — Semantic parity`。

## 已完成 Task 合同：BSS-S2-P1-T004

- 目标：独立审计输入包与 T003 后 canonical resources 的核心逻辑、行为边界和版本影响；任何非身份变化
  都必须停止并取得用户决定。
- Subject boundary：审计精确覆盖 T002 导入的 36 个文件，即
  `scripts/references/schemas/templates/evals/examples/tests`。源 `SKILL.md` 在
  `SOURCE_INVENTORY.md` 中明确为 `MIGRATE`，由下一 Metadata Task 重构；本 Task 不把尚未发生的入口
  迁移伪称为完成，而是冻结其必须继续遵守的核心不变量。
- Independent neutral diff：独立 Ruby 实现把源/目标身份统一为中性 token 后逐文件比较；8 Python、8 JSON、
  4 CSV、16 Markdown 共 36/36 相等，14 个身份变更文件与 22 个不变文件之外
  `NON_IDENTITY_DIFFS=0`；semantic-neutral tree SHA-256=
  `69b2048137dff371c9f4dc56beb8f08ca4471d0377e6dc50ade5015da2fa840d`。
- Structured parity：8/8 Python neutral AST 相等，digest=
  `b1fed355247be26b75779dcc9be70d9238a743f82770f0d05d3377872d255651`；8/8 JSON 解析后语义相等，
  digest=`afe6229438729726f69313faae417eb67de00b6f886276f814fecfe288948aed`；4/4 CSV row matrix 相等，
  digest=`e94b8611c25be83d9e483f0074d6729f5845e78dcc8a1c0a9e9bcae09f7a6113`。
- Behavioral parity：source/canonical 各 9/9 tests PASS；双运行 34 个 score 正例矩阵、4 个失败输入、
  5 个 evidence case 与 5 个 portfolio case，输出/异常完全相等，behavior SHA-256=
  `d1badec309fd443eb4e094d62fec771b1cdb3c82576d8d52a2da5d4911fc92a8`。额外 Oracle 证明几何聚合、
  硬 flag、60/55/60/50/45 门槛、三个时钟、独立一手证据和根因聚类未弱化；两个 case initializer
  均生成同一 7-file snapshot，并拒绝覆盖非空历史目录。
- Protected design：角色中立搜索、负向搜索、系统需求→每股收益桥、价格不充当基本面反证、历史版本
  append-only 与无交易边界均处于 neutral-byte-equal subject；8 个 Python 文件的 import roots 仅为标准库，
  网络/券商模块为 0。
- Version impact：输入 `VERSION=0.1.0` 是未登记的三段源包值，已由 T002 明确排除；目标使用冻结
  `numeric-quad=0.0.0.1`，禁止跨 scheme 比较。schema/event/invocation 改名是用户确认的首次激活前身份
  迁移；active registry/current release 均不存在，项目外旧 ID 运行时消费者和 event 消费者均为 0。
  因核心语义 diff 为零，不触发版本升级，结论为保持 `0.0.0.1`。
- Verdict：`PASS`；`ACC-S2-012` 的 Producer evidence 已建立，后续 Metadata/Project 必须保持本
  baseline，并由 Stage 2 Review 在完整最终 subject 上独立复验。
- Repository regression：GitHub Stock Skill workflow 四个原始 `run` blocks 本地重放 PASS；active registry
  仍只含 `stock-commercial-opportunities=3.0.0 (v3)`，全部 72 个 unittest case（7 files/3 suites）、
  3 manifests + 1 SHA256SUMS，以及 114 files/239 blobs/125 ZIP entries 公开安全扫描全部通过。
- Non-goals：未执行 T005 Metadata、外层项目工程化、registry/release、Stage Test/Review/Publish、
  commit/push 或任何本机 runtime 安装。
- 停止条件：T004 证据与 Task Pack manifest 封印后停止；唯一下一 Task 是
  `BSS-S2-P2-T001 — Metadata`。

## 已完成 Task 合同：BSS-S2-P2-T001

- 目标与边界：只把源 `SKILL.md` 重构为 stable-ID canonical 入口，并用官方 skill-creator generator
  确定性维护 `agents/openai.yaml`；未创建 T006 所属的外层 Project 文件，未执行 registry/release、
  Stage Test/Review/Publish、commit/push 或本机 runtime 安装。
- Canonical metadata：frontmatter 只含 `name` 与 `description`；name 与目录名均精确为
  `bottleneck-serenity-skill`。最终 `SKILL.md` 为 204 行、description 602 chars、SHA-256=
  `afc2d411182697c0efa9fc693c89efd007c75e415831f0a0bc6d2ac199a32ffc`。
- Workflow parity：入口保留五种 mode、funded demand、functions-before-tickers、角色中立假设、claim-level
  evidence/负向搜索、四个非补偿 gate、三个时钟、需求到 per-share 桥、法律实体与 listed exposure、capital
  cycle、bear/base/bull、red team/kill switches、几何评分与 60/55/60/50/45/六个月硬门、根因组合聚类、七个
  decision labels、append-only snapshots 和 research-only/no-broker/no-order 边界。
- Progressive disclosure：11/11 references、4/4 runtime scripts、3/3 schemas 与
  `templates/examples/evals/tests` 四类 bundled route 均由入口显式路由；示例与 eval 不得作为投资证据，bundled
  原件不得被 case 运行覆盖。
- UI metadata：generator 输入精确为 display name `bottleneck-serenity-skill`、short description
  `Build auditable, falsifiable bottleneck investment theses`、default prompt
  `Use $bottleneck-serenity-skill to turn this investment theme into an auditable, falsifiable bottleneck thesis.`；
  `openai.yaml` SHA-256=`e90b9449d3cb2df99ad5f67eeb4097de2d0171a2dce5853f880e9603bdb7dc27`，隔离临时目录重生成与
  canonical bytes 全等。
- Provenance/notice boundary：源 `PROVENANCE.md` 与 `NOTICE.md` SHA-256 分别仍为
  `0fb17bab95dccdc0ce944cbd74a29ee65ba25c7f14dcc9031ffd829d1de689f9`、
  `7b2c21c87bb6184bacd28de83b4c920a5233f58c0d5d07540a0063735b5f885e`；两者不进入 canonical Skill，
  唯一归宿保持为 T006 外层 `LICENSE_AND_ATTRIBUTION.md`。`SOURCE_INVENTORY.md` 未改写，SHA-256 仍为
  `01e0c912775649c72915751e7882779d9ad1d43c6903f1fe0d5e888a70962a94`。
- Baseline preservation：T004 的 36-file resource tree（`relative_path + NUL + mode + NUL + payload + NUL`）
  SHA-256 仍为 `ae21e31ba95c1334c352f522ffe8d2e98f20c0011219ada1c7e2a7e242316fb4`；旧身份 token 命中为 0。
- Validation：官方 quick validator、项目 validator、9/9 unittest、8/8 JSON、frontmatter/UI/route/概念/行数/
  whitespace/fence 静态断言与 generator determinism 全部 PASS。自写静态断言首次因 Ruby 默认 US-ASCII
  在读取中文路径说明前中止，显式 UTF-8 后完整 PASS；该 runner 修正未改 Skill bytes。
- Read-only forward tests：正向合成历史 prompt 选择 `scan` 并冻结 2024-12-31 cutoff，以
  `WATCH_EVIDENCE` 输出研究合同，覆盖全部四门、证据策略、三时钟、rent-capture、valuation、red team、
  hard blocks 与 causal portfolio；负向 prompt 拒绝猜实时报价、访问券商、下杠杆期权单或保证收益。两项均
  未联网、未写文件、未调用 broker，且只渐进读取所需资源。
- Repository regression：GitHub Stock Skill workflow 四个原始 `run` blocks 本地重放 PASS；active registry
  唯一 current 仍为 `stock-commercial-opportunities=3.0.0 (v3)`，全部 72 个 unittest case（7 files/3
  suites）、3 manifests + 1 SHA256SUMS，以及 114 files/239 blobs/125 ZIP entries 公开安全扫描均通过。
  Task Graph 为 58 total / 34 DONE / 18 PENDING / 6 CONDITIONAL，首个 pending 精确为 T006。
- 停止条件：Metadata 验收与 Task Pack manifest 封印后停止；唯一下一 Task 是
  `BSS-S2-P2-T002 — Project`。

## 已完成 Task 合同：BSS-S2-P2-T002

- 目标与边界：只建立 outer source project、许可归属、版本/接口/Owner 与恢复说明；未实现 builder，未生成
  release/`SHA256SUMS`/backup manifest，未修改 active registry/发现面，未执行 Stage Test/Review/Publish、
  commit/push 或本机 runtime 安装。
- Outer project artifacts：新增 `AGENTS.md`、`README.md`、`VERSION`、`CHANGELOG.md`、
  `LICENSE_AND_ATTRIBUTION.md`、`RESTORE_AND_VERIFY.md`，并只追加完善既有 `SOURCE_INVENTORY.md`。七文件
  SHA-256 依次为 `b6984ecf...c50a`、`068a8517...dac4`、`4cca2fc0...253b3`、`eba3bd50...9e56`、
  `c79340eb...a1fe`、`c562d4ad...cba3`、`e46b0eb4...b23d`。
- Version/state：outer 与 Task Pack `VERSION` 均逐字等于 `0.0.0.1`；README/AGENTS 明确 machine/display
  版本、五种 mode、主要用户、默认值、输入输出、Owner、adapter 与 research-only 边界，同时把项目状态冻结为
  `SOURCE_PROJECT_DRAFT / REGISTRY_NOT_ACTIVE / RELEASE_NOT_BUILT / NOT_INSTALLED`，不把目录存在伪称激活。
- Migration completion：保留 53 行 source ledger 与 `IMPORT 43 / MIGRATE 9 / EXCLUDE 1` 原始决定，只追加
  README/quickstart/provenance/notice/build/handoff 等 destination completion；源 `0.1.0` 继续排除，不建伪
  archive。新 inventory SHA-256=`e46b0eb4ac91802f3ae45efefbe458d98e88a7d42ee658b5640cad01c44bb23d`。
- Independent license audit：固定四个公开仓当前 commit 并 unshallow 审计其完整 Git history；38 个 target
  text files 对 1,951 upstream historical text blobs 的 exact matches=`0`、规范化连续四行 match=`1`。唯一
  四行 match 与另一个 34-token validator match 均来自 `muxuuu/serenity-skill` 的 MIT-covered 初始提交；
  final attribution 不依赖输入包“零复制”主张，保守标注 `POSSIBLE_ADAPTATION / MIT-COVERED` 并保存完整 MIT
  notice。两个无明确 license 仓零 exact/四行 match，仅作事实与思想引用，禁止复制 payload。
- Restore boundary：Task Pack 状态句的 `RESTORE.md` 误写已按 architecture、`ACC-S2-011` 与同仓约定统一为
  `RESTORE_AND_VERIFY.md`。文档可执行当前 source checks，并明确未实现 builder/release/hash 时必须
  `NOT_AVAILABLE`；proposed-tree 和 final clean sparse-checkout 流程只冻结后续接口，`ACC-S2-011` 仍由 T008
  产生真实双重建证据。当前 sparse-checkout command 已在隔离 clone 语法/checkout 验证通过。
- ACC producer evidence：`ACC-S2-003` 的双 VERSION 已建立；`ACC-S2-009` 证明 5 scripts/10 import roots 全部
  标准库且 network/broker/order/daemon/scheduler capability=0、两个用户 runtime target 均不存在；
  `ACC-S2-010` 的 proprietary/逐来源/copy decision/redistribution 证据已建立；`ACC-S2-013` 的用户、接口、
  默认值、Owner 与 adapter 边界已落入 README/AGENTS。最终 verdict 仍由对应 Test/Review Task 复验。
- Baseline/targeted validation：T004 的 36-file resource tree SHA 仍为
  `ae21e31ba95c1334c352f522ffe8d2e98f20c0011219ada1c7e2a7e242316fb4`；官方 quick validator、项目
  validator、9/9 tests、8/8 JSON、README 双接口 JSON、source ledger、license/commit/notice、outer path/
  whitespace 与公开安全扫描均 PASS；公开安全扫描为 120 files/245 blobs/125 ZIP entries。
- Repository regression：GitHub Stock Skill workflow 四个原始 `run` blocks 本地重放 PASS；active registry
  唯一 current 仍为 `stock-commercial-opportunities=3.0.0 (v3)`，全部 72 个 unittest case（7 files/3
  suites）、3 manifests + 1 SHA256SUMS 及 120 files/245 blobs/125 ZIP entries 公开安全门均通过。Task
  Graph 为 58 total / 35 DONE / 17 PENDING / 6 CONDITIONAL，首个 pending 精确为 T007。
- 停止条件：Project 验收与 Task Pack manifest 封印后停止；唯一下一 Task 是
  `BSS-S2-P2-T003 — Registry prep`。

## 已完成 Task 合同：BSS-S2-P2-T003

- 目标与边界：只在 `Stock_Skill/tests/test_validate_registry.py` 的临时仓 fixture 中冻结并验证待激活
  entry；未修改 active `Stock_Skill/REGISTRY.json`、四个 root/Stock Skill 发现面、项目发现面、release、
  `SHA256SUMS` 或 backup manifest，未执行 T004/Stage Test/Review/Publish、commit/push 或 runtime 安装。
- Executable plan：既有 fixture builder 参数化 stable ID、display name、canonical project path 与 release
  filename；新增 Oracle 对 14 个 entry 字段和字段顺序做全量相等断言。冻结值为
  `id/display_name=bottleneck-serenity-skill`、`latest_version=0.0.0.1`、
  `version_scheme=numeric-quad`、`latest_major=0`、`current=true`、`SOURCE_ONLY/PROHIBITED`、canonical project
  `Stock_Skill/bottleneck-serenity-skill`、canonical Skill
  `Stock_Skill/bottleneck-serenity-skill/task-pack/skill_draft/bottleneck-serenity-skill`、两条 VERSION 来源、
  六个发现面、完整 v0.0.0.1 release path 与 `superseded_archives=[]`。
- Discovery plan：六条 `version_claim_paths` 顺序精确为 root `AGENTS.md`/`README.md`、
  `Stock_Skill/AGENTS.md`/`README.md`、project `AGENTS.md`/`README.md`；本 Task 只在临时仓生成 claim，真实
  文档仍保留“待激活”语义，待 T004 与真实 release SHA 同事务更新。
- SHA boundary：fixture 只为临时合成 release 动态实算 SHA-256，并让 validator 同时核对 release bytes、
  `SHA256SUMS` 和 manifest；该 SHA 不写入任何 source/registry，不冒充候选或 current release SHA。真实
  filename 冻结为 `bottleneck-serenity-skill_codex-skill-task-pack_v0.0.0.1.zip`。
- Validation：定向 Oracle 1/1 PASS；完整 registry isolation suite 12/12 PASS；active validator PASS 且仍只
  输出 `stock-commercial-opportunities=3.0.0 (v3)`。active registry before/after SHA-256 均为
  `45c43e544231283028bedc5f4ea4779dd69292d413af8d23b97fc1366be59646`，Git diff 为空，新 stable ID 不在
  active skills 集合。
- Repository regression：GitHub Stock Skill workflow 四个原始 `run` blocks 本地重放 PASS；active registry
  仍只有既有 current，全部 73 个 unittest case（7 files/3 suites）、3 manifests + 1 SHA256SUMS 与公开安全门
  均通过。Task Graph 为 58 total / 36 DONE / 16 PENDING / 6 CONDITIONAL，首个 pending 精确为 T008。
- 停止条件：Registry prep 与 Task Pack manifest 封印后停止；唯一下一 Task 是
  `BSS-S2-P2-T004 — Release/activate`。

## 已完成 Task 合同：BSS-S2-P2-T004

- 目标与边界：实现 deterministic build/activate/verify，构建真实 Stage 2 candidate，并把 T003 冻结的
  entry、三个 SHA 消费面与六个发现面原子物化；未执行下一 Test、Stage Review/Publish、commit/push 或
  runtime 安装。
- Builder：新增标准库 `scripts/build_release.py`（mode `0755`）。默认 build 只从当前 Task Pack 重建 ZIP；
  `--activate` 必须先独立重现当前 ZIP，再写 `SHA256SUMS`/registry 并最后生成 backup manifest；`--verify`
  同时验证版本、manifest、ZIP bytes/metadata、发现面、registry 与四面 SHA 一致性。
- Deterministic ZIP：filename 与唯一 root 分别固定为
  `bottleneck-serenity-skill_codex-skill-task-pack_v0.0.0.1.zip`、
  `bottleneck-serenity-skill-task-pack-v0.0.0.1/`；entry 按 UTF-8 bytes 排序，时间固定 1980-01-01，使用
  `ZIP_STORED`，目录/脚本/普通文件 mode 为 `0755/0755/0644`，拒绝 duplicate、symlink、非普通、缓存、
  unsafe path、错误 file set 与 manifest 漂移。预备与最终 candidate 均连续双构建 byte-identical。
- Activation：registry 新 entry 精确沿用 T003 的 14-field plan：stable ID/display name、
  `numeric-quad=0.0.0.1`、major `0`、SOURCE_ONLY/PROHIBITED、两个 canonical path、两条 VERSION、六条 claim
  path、真实 release path/SHA 与 `superseded_archives=[]`；既有 semver entry projection 未改变。
- Hash DAG：Task Pack files → task manifest → release → 实算 release SHA → `SHA256SUMS`/registry；outer
  project 稳定后最后生成 backup manifest。实际 release SHA 只持久化在这三个消费面，不写回 Task Pack、
  inventory 或 changelog；task manifest 无 Root 外 entry，首版未创建 `archives/`。
- Discovery/restore：root、`Stock_Skill` 与 project 的 README/AGENTS 六面均声明
  `bottleneck-serenity-skill=0.0.0.1`，移除 pre-activation 状态；project README/CHANGELOG/SOURCE_INVENTORY/
  RESTORE 同步 current candidate、无环职责、重建与 source-only/not-installed 边界。
- Validation：默认 build 连续两次同 SHA；`--activate` 与 `--verify` PASS；独立 ZIP/file-set/mode/time/type/
  DAG 审计 PASS，current release 解包路径/内容的旧身份 token 命中为 0；registry validator 同时输出既有
  v3 与完整 `v0.0.0.1`；官方/项目 Skill validators、9/9
  project tests、全部 73 个仓库 unittest、4 manifests + 2 SHA256SUMS 与公开安全门均 PASS。
- Repository state：Task Graph 为 58 total / 37 DONE / 15 PENDING / 6 CONDITIONAL，首个 pending 精确为
  `BSS-S2-P3-T001`；主树保持 `main`/clean，任务 index 为空，HEAD/remote branch 未移动，用户级两个 Skill
  runtime target 均不存在。
- 停止条件：Release/activate 制品链与 Task Pack manifest 封印后停止；唯一下一 Task 是
  `BSS-S2-P3-T001 — Test`。

## 已完成 Task 合同：BSS-S2-P3-T001

- 目标与边界：运行并补强 Stage 2 的结构、单元、schema、hash、ZIP、registry 与 candidate 恢复回归；只修复
  Test Oracle 缺口，未执行整体 Stage Review/Remediation/Publish、commit/push 或 runtime 安装。
- Durable release Oracle：新增仓级 `Stock_Skill/tests/test_bottleneck_serenity_release.py`，5 个 case 对 active
  builder `--verify`、task/backup manifests、确定性 ZIP metadata/payload、existing v3 projection、新 entry、
  三个 release SHA 消费面、空 archive 和隔离双构建做正向断言；stale Task Pack、release、sums、registry、
  backup、discovery、manifest drift、symlink 共 8 类临时变异全部 fail closed，active artifacts before/after
  digest 保持不变。
- Durable schema Oracle：新增 canonical `tests/test_schema_contracts.py`，仅用 Python 标准库解析全部 8 个 JSON，
  fail closed 校验三份 Draft 2020-12 schema 的已用 keyword/local `$ref`，并验证 opportunity/portfolio 示例与
  synthetic evidence fixture；missing required、score 上界、未知 score group、scenario 下界、portfolio weight
  上界及独立 evidence date/enum/minLength 共 8 类反例全部被拒绝。
- Derived DAG refresh：canonical test 与 Task Pack 状态改变后重算 task manifest，从新 subject 连续构建两次
  byte-identical candidate，再运行 `--activate`/`--verify` 原子刷新 release、`SHA256SUMS`、registry 与最后
  backup manifest；release SHA 仍只持久化在三个许可消费面，project 不存在 `archives/`。
- Validation：官方 quick validator、项目 validator、13/13 canonical tests、全部 82 个仓库 unittest
  （9 files/3 suites）、全部 JSON/schema Oracle、registry 双 current、4 manifests + 2 SHA256SUMS、
  deterministic ZIP/hash DAG、公开安全门与 `git diff --check` 全部 PASS；隔离 clean build 两次同 bytes，
  proposed-tree/final sparse-checkout seal 继续由 Stage Publish 在 Review PASS 后执行。
- Repository state：Task Graph 为 58 total / 38 DONE / 14 PENDING / 6 CONDITIONAL，首个 pending 精确为
  `BSS-S2-P4-T001`；主树保持 `main`/clean，任务 index 为空，HEAD/remote branch 未移动，两个用户级 Skill
  runtime target 均不存在。
- 停止条件：Test 回归、Task Pack manifest 与 candidate DAG 刷新完成后停止；唯一下一 Task 是
  `BSS-S2-P4-T001 — Review`。

## 已完成 Task 合同：BSS-S2-P4-T001

- 目标与边界：在任何 subject 文件改动前锁定 Task Pack 与完整 Stage source，独立整体复审 Stage 2 的迁移、
  身份、版本、遗漏、许可、恢复性、制品 DAG 与全部 acceptance；本 Task 只记录 finding、verdict 与确定性路由，
  不整改、Publish、commit/push 或安装 runtime。
- 冻结 subject：branch=`bottleneck-serenity-skill`、base HEAD=
  `8308d170325c2ce35581d3fb757a2b731f7803dc`、subject paths=`61`。Python 规范实现与独立 Ruby 实现同得
  `taskpack-tree-sha256-v1`=
  `cdbe9cf21c1f2929b79b47cb41011f914cdc3cd6a233c42bfcdd7d2d74e9f347`，以及
  `stage-worktree-source-sha256-v1`=
  `e65847005cee5e03a949168e724ca01928731d0e0551530d1da22c09d889609c`；Task Pack subject 为 47 个文件。
- 通过项：53 个输入 ZIP entry 与 inventory 逐项/顺序/类型/mode/hash 精确相等，决定集合仍为
  `IMPORT 43 / MIGRATE 9 / EXCLUDE 1`；36-file 迁移资源树只含三类已授权身份替换，semantic tree digest 与
  Producer 记录相等。稳定 ID、frontmatter、metadata、双 VERSION、旧身份零命中、六发现面、空 archive、
  registry 双 current、三 SHA 消费面、两个 manifest、deterministic ZIP 与 source-only/runtime 边界均 PASS。
- 独立恢复与回归：临时 Git index 物化 61-path proposed tree，连续两次 clean build byte-identical，release、
  task manifest、backup manifest、registry 与 canonical source digest 均与 active candidate 相等；最终 sealed
  commit 的 clean sparse-checkout 仍只属于 Publish，不在 Review 中预写。官方/项目 validator、13 canonical
  tests、82 个仓库 tests（9 files/3 suites）、4 个 workflow 原始 run blocks、4 manifests + 2 SHA256SUMS、
  126 files/298 blobs/172 ZIP entries 公开安全门、44 ACC/23 REQ/9 CAP/7 NG 追溯与 58 个唯一 Task ID 均 PASS。
- `S2-R001`（P1）：冻结的 Task Pack/项目 README completion payload 均要求 `skill_version` 与
  `source_cutoff`，canonical `references/integration_contract.md` 的 primary event 却缺少二者；同时
  `output_contract.md`、三份 schema、`templates/research_config.json` 与 `new_research_case.py` 未落实
  `SKILL.md` 的“每个 machine-readable artifact 包含 schema/Skill version、source cutoff”合同，输入 scaffold
  还以 `question` 取代 `query` 并遗漏 `request_id/upstream_artifacts`。现有 schema tests 只验证 JSON/schema
  局部有效性，不能发现该跨文档漂移，因此 `ACC-S2-013` FAIL。
- `S2-R002`（P1）：`LICENSE_AND_ATTRIBUTION.md` 与 `SOURCE_INVENTORY.md` 的独立相似性审计仍声明覆盖
  38 个 target text files，但 current canonical 已因 T009 新增 schema contract test 而有 39 个文件；文档也未
  固化 text-blob eligibility、规范化与计数算法，独立宽口径复算虽确认四个冻结 commit/license 事实与零 exact
  file match，却无法重现文档的精确 blob/四行计数。current payload 的 durable 许可覆盖因此不完整，
  `ACC-S2-010` FAIL。
- Verdict：`FAIL`。`ACC-S2-001`–`ACC-S2-009` 与 `ACC-S2-012` 的 Review portion PASS；
  `ACC-S2-006/011` 的最终 Publish seal 仍按合同留给 `BSS-S2-P5-T001`，不冒充已完成；
  `ACC-S2-010/013` 因上述 finding
  FAIL，Stage 2 禁止 Publish。
- 路由：按确定性复审循环启用 `BSS-S2-P4-T002/T003` 为 `PENDING`；唯一下一 Task 是 T002。两项 finding
  均保持 `OPEN`，只能由 T002 推进为 `FIXED_PENDING_REREVIEW`，再由 T003 在新双 digest subject 上关闭。
- Non-goals：本 Task 未修复 canonical contract/schema/template/script、许可文档或审计 Oracle，未执行
  Publish、commit/push、runtime 安装或真实 clean-checkout seal。

## 已完成 Task 合同：BSS-S2-P4-T002

- 目标与边界：只整改 `S2-R001/S2-R002` 并建立 T003 可独立复验的 durable 正负 Oracle；未执行 T003
  Re-review、Publish、commit/push、runtime 安装或 finding closure。
- `S2-R001`：Task Pack、项目 README 与 canonical integration 的 input/completion JSON projection 现逐字段、
  值与顺序相等；输入补齐 `schema_version/skill_version/source_cutoff/previous_version`，completion 补齐
  `previous_version`。运行期机器可读研究 artifact 的五字段 envelope 冻结为 `schema_version=1.0`、
  `skill_version=0.0.0.1`、canonical `as_of/source_cutoff` 与非空 prior ID 或首版 `null`。
- Artifact implementation：三份 schema、research config、三个 CSV template、三个 JSON 示例、case initializer、
  score/evidence/portfolio 脚本输入输出同步 envelope；initializer 使用 `query/request_id/upstream_artifacts`、
  生成 UUID、拒绝未来 cutoff/overwrite，并产生 schema-valid evidence/opportunity scaffold。仓级 cross-doc
  projection 与 canonical schema/runtime tests 对 missing、rename、错误 version/nullability 等 mutant fail closed。
- `S2-R002`：新增 mode `0755` 的标准库 `scripts/audit_license_similarity.py` 与确定性
  `LICENSE_SIMILARITY_AUDIT.json`。target 为全部 39 个 canonical regular UTF-8 files；upstream 为四个冻结
  commit 的全部可达 unique blobs，无 path/size 排除；eligibility、NFC/whitespace、连续四物理行、pair identity、
  token20 review threshold 与无上游文本 evidence schema 全部固化。
- Full-history evidence：2,489 个 reachable blob instances 中 2,485 个 text-eligible；两次完整重算报告
  byte-identical，exact pairs=`0`、four-line pairs=`3`、token20 pairs=`1`。两个无明确许可仓 exact/token20
  均为 `0`；wesson 唯一宽 pair 只有零 token JSON 闭合标点。MIT muxuuu score/validator scaffolding 继续保守
  归属，LICENSE/INVENTORY/RESTORE 与 project discovery 已同步。
- Durable Oracle：仓级 fixture 证明历史已删除 blob 仍纳入、NUL/non-UTF-8 排除、exact/NFC-whitespace/
  four-line/token20 计数，并拒绝算法、target hash/file set 与冻结 upstream metadata mutant；committed report
  快速门精确绑定 39 个 current target，报告无 clone path、凭据或上游文本。
- 状态：`S2-R001/S2-R002` 只推进为 `FIXED_PENDING_REREVIEW`；Task Graph 为 58 total / 40 DONE / 14 PENDING /
  4 CONDITIONAL，首个 pending 精确为 `BSS-S2-P4-T003`。
- 停止条件：T002 source、durable Oracle、报告、派生 release/hash DAG 与全量回归完成后停止；只有 T003 可在
  新双 digest subject 上把 finding 改为 `CLOSED`。

## 已完成 Task 合同：BSS-S2-P4-T003

- 目标与边界：在任何 subject 修改前冻结新双 digest，独立复验 `S2-R001/S2-R002` 与完整 Stage 2；本
  Task 只记录 verdict、finding closure/failure 和确定性路由，不整改、Publish、commit/push 或安装 runtime。
- 冻结身份：branch=`bottleneck-serenity-skill`、base HEAD=
  `8308d170325c2ce35581d3fb757a2b731f7803dc`、subject paths=`66`；Python 规范实现与独立 Ruby 实现同得
  47-file `taskpack-tree-sha256-v1`=
  `7f3e9238a81de7a0d6d738411d2709b62831de3a16acb85a7f93900daeec5486`，以及
  `stage-worktree-source-sha256-v1`=
  `d956354782afb6979a68519cce79e5b465c14d5203c751aade0c231da0847b0b`；记录 verdict 前复算无漂移。
- `S2-R002` closure：四个 fresh、非 shallow、credential-free HTTPS clone 上，规范 Python 重算报告与
  committed report byte-identical；独立 Ruby 实现同得 39 targets、2,489 reachable / 2,485 eligible blobs、
  exact=`0`、four-line=`3`、token20=`1` 及逐 pair/evidence 精确相等，故 `S2-R002` `CLOSED`、
  `ACC-S2-010` PASS。
- `S2-R001` 未关闭：score/evidence/portfolio 三条入口均用 `payload.get("previous_version")`；删除或改名
  nullable 字段的 6/6 独立探针全部被接受并输出 `previous_version:null`。schema 层虽拒绝，但 19 个
  canonical tests 未覆盖三条 runtime presence 分支，故 `S2-R001` 回到 `OPEN`、`ACC-S2-013` FAIL。
- Stage 证据：53-entry/43-9-1 来源映射、36-file 核心语义等价、身份/版本/UI、registry 双 current、候选
  release/hash DAG、六发现面、source-only/runtime 边界、19 canonical tests、93 repository tests、四个
  workflow 原始 run blocks、4 manifests + 2 SHA256SUMS 与公开安全门全部 PASS；`ACC-S2-005/010/012`
  PASS。Publish 专属 proposed-tree/clean-checkout seal 未提前执行。
- Verdict：`FAIL`。按最大 suffix+1/+2 追加 `BSS-S2-P4-T004/T005` 为 `PENDING`；Task Graph 为 60 total /
  41 DONE / 15 PENDING / 4 CONDITIONAL，首个 pending 精确为 T004。唯一下一 Task 是 T004，只能把
  `S2-R001` 推进到 `FIXED_PENDING_REREVIEW`，再由 T005 在新双 digest subject 上关闭。

## 已完成 Task 合同：BSS-S2-P4-T004

- 目标与边界：只整改 T003 未关闭的 `S2-R001` nullable field presence 缺口并建立 T005 可独立复验的
  durable 正负 Oracle；Builder 不关闭 finding，也不执行 T005、Publish、commit/push 或 runtime 安装。
- 失败基线与实现：score/evidence/portfolio 三条 runtime 的 missing/renamed `previous_version` 共 6/6 错误
  ACCEPT；三处 `_artifact_metadata` 现均在读取值前显式要求 key 存在。显式首版 `null` 和非空 lineage ID
  继续通过，错误类型、空字符串、未来 cutoff 与错误 schema/Skill version 继续拒绝。
- Durable Oracle：三个 canonical test module 各新增一个 presence case，覆盖 lineage 正例与 missing/rename
  两个负例；canonical suite 从 19 增至 22 cases。整改后 6/6 负例以精确错误拒绝；临时副本删除三处新分支
  后，新增测试产生 6 failures、suite 非零，证明回退 mutant 被持久化测试杀死。
- License/hash coupling：六个 canonical target bytes 改变后，旧报告 `--verify-targets` 因 target hash/size
  drift 非零。使用四个 fresh、非 shallow、credential-free HTTPS clone 重新生成并再次全历史复算，报告
  byte-identical；39 targets、2,489 reachable / 2,485 eligible blobs、exact/four-line/token20=`0/3/1` 均不变，
  `S2-R002` 保持 `CLOSED`。
- Producer/status：`ACC-S2-013` 的完整 machine-interface 验收能力与主制品集合首次成立于本 Task，Producer
  转移到 T004；`S2-R001` 仅推进为 `FIXED_PENDING_REREVIEW`。Task Graph 为 60 total / 42 DONE / 14 PENDING /
  4 CONDITIONAL，首个 pending 精确为 T005。
- Validation：官方/项目 validators、22 canonical tests、96 repository tests、registry 双 current、候选
  release/hash DAG、4 manifests + 2 SHA256SUMS、四个 workflow 原始 run blocks与公开安全门全部 PASS。
  派生 Task manifest、release、sums/registry 与 backup manifest 已按无环顺序刷新。
- 停止条件：source、durable Oracle、许可报告、状态文档与派生 DAG 全部验证后停止；只有
  `BSS-S2-P4-T005` 可在新双 digest subject 上把 `S2-R001` 改为 `CLOSED`。

## 已完成 Task 合同：BSS-S2-P4-T005

- 目标与边界：以 `developer_check`、中风险候选评审独立复验 T004 的 `S2-R001` 整改与完整 Stage 2；本
  Task 只记录 closure/verdict/路由并刷新派生 DAG，不整改产品、不执行 Publish、commit/push 或 runtime 安装。
- 冻结身份：在任何 subject 修改前锁定 branch=`bottleneck-serenity-skill`、base HEAD=
  `8308d170325c2ce35581d3fb757a2b731f7803dc`、subject paths=`66`；Python 规范实现与独立 Ruby 实现同得
  47-file `taskpack-tree-sha256-v1`=
  `f92345a4d7ee05f84dba2c88c2c88ebbc0156c2ccc09f8cc6fceb68c36bdd6f0`，以及
  `stage-worktree-source-sha256-v1`=
  `795ac48e7293d1604724cd107ba3c73e90f2ba9308921b39c9c2c0faa251af63`；记录 verdict 前四项复算无漂移。
- `S2-R001` closure：Task Pack、项目 README 与 canonical integration 的 input/completion projection 精确
  相等；三 schema、四个静态 artifact、scaffold 的四个 JSON/一个 CSV 及三条 runtime 均保持五字段 envelope。
  missing/renamed `previous_version` 6/6 以精确错误拒绝，显式 `null`/lineage 6/6 通过；22 canonical cases
  PASS，临时回退副本删除三处 presence 分支后产生精确 6 failures。因此 `ACC-S2-013` PASS、finding CLOSED。
- 完整 Stage 2：五个输入 artifact 与 53-entry ZIP/ledger 的 path/order/type/mode/hash 精确相等，决定仍为
  `IMPORT 43 / MIGRATE 9 / EXCLUDE 1`；8 个 Python 源函数零删除，30 个 score、5 个 evidence、5 个
  portfolio 有效输入的核心 source/current 输出相等。identity/version/UI、registry 双 current、空 archive、
  39-file canonical/release parity、source-only/runtime 边界与 66-path allowlist 全部 PASS。
- 许可与制品：四个 fresh、非 shallow、credential-free HTTPS clone 上规范 Python 全历史重算报告与 committed
  bytes 相等；独立 Ruby 不复用审计器代码复核 39 targets、2,489 reachable / 2,485 eligible、
  exact/four-line/token20=`0/3/1`，无许可仓 exact/token20=`0/0`。确定性双构建、47-file ZIP、4 manifests、
  2 SHA256SUMS、三个 release SHA 消费面与无环 DAG 全部 PASS。
- 回归：官方 quick validator、项目 validator、22 canonical/96 repository tests、四个 workflow 原始 run
  blocks、129 files / 301 blobs / 172 ZIP entries 公开安全门、44 ACC / 23 REQ / 9 CAP / 7 NG 追溯全部 PASS；
  主树 `main`/clean、任务 index 空、远端 branch/PR head 未移动，两个本机 Skill runtime target 均不存在。
- AI/release 边界：T004 只改变确定性 JSON presence gate，未改变 model/prompt/tool/retrieval，故本评审的 AI
  多 trial gate 为 `NOT_APPLICABLE`；隔离正/负 forward-test 仅作附加回归，不提前完成 Stage 3。Publish 专属
  staged/proposed-tree 与最终 clean-checkout seal 仍保留给 P5，不冒充本 Task 证据。
- Verdict：`PASS`。`S2-R001/S2-R002` 与 ledger 25/25 均为 `CLOSED`；Task Graph 为 60 total / 43 DONE /
  13 PENDING / 4 CONDITIONAL，首个 pending 精确为 `BSS-S2-P5-T001`。

## 下一个许可动作

唯一允许的下一 Task 是 `BSS-S2-P5-T001 — Publish`。它必须从复审通过后的 frozen source 重新封印 task
manifest，重建 release/SHA DAG，并在 commit/push 前完成 staged/proposed-tree replay；本 T005 不提前执行
Publish、commit/push、安装 runtime 或进入 Stage 3。
