# Task Pack Changelog

## Unreleased — v0.0.0.1

### Stage 0

- 建立 `bottleneck-serenity-skill` 专用 worktree，并恢复 canonical 主树到干净 `main`。
- 冻结全局稳定 ID `bottleneck-serenity-skill`。
- 冻结机器版本 `0.0.0.1` 与展示/release 版本 `v0.0.0.1`。
- 定义 source-only、禁止本机安装、禁止交易执行与公开安全边界。
- 创建 compact `5+1` Task Pack。
- 将后续工作拆为单 Task run，并为每个 Stage 定义整体复审、整改、重审和上传门。
- 完成 Task Pack 结构、身份、版本、Task ID、阶段门、公开路径和 registry 回归自检。
- 完成 Stage 0 整体复审，锁定 subject digest
  `37452ef7fe3cdef60ffcdbf9c448b82b79537c01b2f6819936900c5d4ab9f863`。
- 按 `BSS-S0-P2-T002` 整改 6 个 P1 与 1 个 P2 finding，等待独立重审关闭。
- `BSS-S0-P2-T003` 在整改后 subject
  `d2794667d739d30012faf8f28889e27574772d53a6b70eca62308acef28883e4` 上重审，verdict `FAIL`。
- `BSS-S0-P2-T004` 仅整改五个未关闭 finding；Builder 状态更新为
  `FIXED_PENDING_REREVIEW`，等待 `BSS-S0-P2-T005` 在新 subject 上独立关闭。
- `BSS-S0-P2-T005` 在 subject
  `b97ef4030e9bb23581ca22dc89560a738c583dff6eeb4e5ce037ce670528edcd` 上完成第二轮整体重审，
  关闭三项 finding、保留两项并新增一项，verdict `FAIL`。
- `BSS-S0-P2-T006` 只整改三项 OPEN finding；Builder 状态更新为
  `FIXED_PENDING_REREVIEW`，等待 `BSS-S0-P2-T007` 独立关闭。
- `BSS-S0-P2-T007` 在 subject
  `849caf740442f5450db016462b030f9c22b15507c3c805571960b4b6da5ac5d5` 上完成第三轮整体重审，
  关闭一项、保留两项，verdict `FAIL`。
- `BSS-S0-P2-T008` 只整改两项 OPEN finding；Builder 状态更新为
  `FIXED_PENDING_REREVIEW`，等待 `BSS-S0-P2-T009` 独立关闭。
- `BSS-S0-P2-T009` 在 subject
  `1fbfff05462e03b514edb6bf9ba434cc50b645ec02a45291a393953485ca2315` 上完成第四轮整体重审；
  关闭 `S0-R001/R011`，新增 release/manifest 封印图不可执行的 `S0-R012`，verdict `FAIL`。
- `BSS-S0-P2-T010` 只整改 `S0-R012`：冻结 task manifest、release、sums/registry、backup manifest 的
  单向 DAG，首次 registry 激活的真实 SHA 门，以及 Review 候选 → Publish source freeze → derived render →
  staged-tree replay → upload 的封印顺序。
- `BSS-S0-P2-T011` 在 subject
  `f17ad7dfaa2088f645e37a88ce415ee3d0e672ebe07361b1f69d9a810a7636ad` 上完成第五轮整体重审；
  `S0-R012` 与全部历史 finding 回归 PASS，ledger 零未关闭 finding，Stage Review verdict `PASS`。
- `BSS-S0-P3-T001` 从已复审 subject 封印并上传完整 Stage 0：commit
  `287488a303d2da06fbfbe8d9f7195e603855ca70`、draft PR #76、8-file 远端 diff、remote/local SHA 与
  `dual-plane` check 全部通过；外部证据由 `BSS-S1-P1-T001` 查询后回填。

### Stage 1

- `BSS-S1-P1-T001` 冻结 registry schema `1.1`：entry 必须显式声明 `semver` 或 `numeric-quad`，
  两者使用固定 arity、无前导零的 canonical grammar，只能同 scheme 整数 tuple 比较，未知/跨 scheme
  fail closed。
- 冻结原子迁移边界：下一 Task 只把 schema 升到 `1.1`、给现有 entry 新增 `semver` scheme 并同步
  validator；不登记新 Skill，不提前执行 tests/docs/CI Task。
- 现有 entry 的 canonical preservation projection SHA-256 锁定为
  `41232c50c051ebc4b5d2e9503bba6c938b8b6e83f81f69bd322ccfdaeeaf98a0`；`3.0.0`、路径、release、
  archives、SHA 和数组顺序不得漂移；冻结时 active registry validator 为 `PASS`。
- `superseded_archives` 在 `1.1` 中仍为必需数组但允许 `[]`；机器版本无 `v`、展示/release 加 `v` 的
  `A-001` 正式锁定。
- `BSS-S1-P1-T002` 原子升级 active registry：schema `1.0` → `1.1`，现有 entry 只新增
  `version_scheme=semver`；validator 实现 canonical 三段/四段解析、同 scheme 比较、严格 major、空
  archive 与缺失/未知/跨 scheme fail-closed。
- 迁移后移除新增 scheme 的 entry projection SHA-256 仍为
  `41232c50c051ebc4b5d2e9503bba6c938b8b6e83f81f69bd322ccfdaeeaf98a0`；root 非迁移字段、全部路径、
  数组顺序、current release 与 v2/v1 archive SHA 均无漂移，active registry validator PASS。
- 保持现有 semver stdout `(v3)`；numeric-quad 将显示完整 `v0.0.0.1`，避免错误缩写为 `v0`。
- `BSS-S1-P2-T001` 新增 10 个隔离 unittest：在临时完整仓库中复制并执行真实 validator CLI，覆盖
  semver/numeric-quad、空 archive、root/entry 缺字段与错误类型、major、arity、前导零、未知/跨
  scheme、archive lineage 与非 object root 的 success/fail-closed 矩阵。
- 每个隔离测试前后锁定 active registry、validator、current release、v2/v1 archive SHA；10/10 PASS，
  active registry 与 legacy entry projection 无变化。
- `BSS-S1-P2-T002` 同步仓根与 `Stock_Skill` 的四个 canonical README/AGENTS 发现面：统一声明 schema
  `1.1`、显式 `semver`/`numeric-quad`、固定 arity/无前导零、严格 major、同 scheme 比较、必需但可为空
  的 archive 数组，以及冲突时 `UNKNOWN` 的 fail-closed 规则。
- 四个发现面继续把 `stock-commercial-opportunities=3.0.0`（`semver`，`v3`）作为唯一 active current，
  并将 `bottleneck-serenity-skill=0.0.0.1`（`numeric-quad`，完整 `v0.0.0.1`，首版 `[]`）明确标为 Stage 2
  原子激活前的待登记合同，未提前创建 registry entry 或占位制品。
- 文档契约断言、active registry validator、10 个隔离 unittest、29 个现有项目 unittest 与 whitespace
  检查全部 PASS；本 Task 未创建 CI、未进入 Stage Review、未 commit/push。
- `BSS-S1-P2-T003` 新增 `.github/workflows/stock-skill-validation.yml`：PR 与 main push 在
  `Stock_Skill/**`、根 AGENTS/README 或 workflow 自身变化时触发；权限只读、checkout 不持久化凭据，
  actions 固定官方完整 SHA、Python 固定 3.12。
- Workflow 自动运行 active registry、全部 Stock Skill unittest、全部 manifest/SHA256SUMS 精确覆盖与
  实算 hash、根发现面/Stock Skill 普通文件及 ZIP payload 公开安全扫描；不安装第三方运行依赖、不上传
  artifact、不使用 secrets 或写生产系统。
- 公开安全扫描仅对既有 immutable v1 谱系已披露的精确 `/home/oai/skills` 保留窄 allowlist；任何子路径、
  `file://` 形式或其他用户目录仍 fail closed。
- PyYAML 合同、官方 checksum 后的 actionlint v1.7.12、四个原始 run blocks 本地重放全部 PASS：registry、
  29+10 tests、3 manifests、1 SHA256SUMS、70 files/195 blobs/125 ZIP entries；9-case 临时矩阵证明零测试、
  失败测试、hash/path/secret 负例均非零退出。真实 GitHub check 等待 Stage Review PASS 后统一 Publish。
- `BSS-S1-P3-T001` 在规范 Task Pack subject
  `20a648cb164947a76961a385ff0837fbbe5fc866e6024d443769eea1e10062f4` 与补充 14-path Stage 1 source audit
  digest `50dcefd0f489f96aebbbe09baab099db3bc6d75593e1fb41bbc2718f43b4a9c1` 上完成整体复审：
  `ACC-S1-001/002/003/005` PASS，`ACC-S1-004/006` FAIL；登记四个 P1 finding，verdict `FAIL`。
- 复审负向证据包括：空 test file 实际运行 `Ran 0 tests` 仍 exit 0；合成 `github_pat_` fine-grained PAT
  仍通过公开安全门；移除 non-object archive 拒绝分支的 mutant 仍通过 10/10 tests；外部 workflow
  假想变更不改变规范 Task Pack digest。启用 `BSS-S1-P3-T002/T003`，禁止进入 Publish。
- `BSS-S1-P3-T002` 只整改 `S1-R001`–`S1-R004`：新增完整 Git worktree Stage source digest 协议及
  6 个隔离测试；把 unittest 与 public-safety inline block 抽为标准库 helper；用真实 `countTestCases()`
  拒绝 zero-case suite；补齐普通文件/压缩 ZIP 的 `github_pat_` durable negative；新增三种 non-object
  archive CLI fixture 并杀死对应 mutant。
- 整改后 registry、52 个真实 unittest case（29+23）、公开扫描 75 files/200 blobs/125 ZIP entries、
  3 manifests + 1 SHA256SUMS、workflow 原始 run blocks、PyYAML、actionlint v1.7.12 与 whitespace 全部 PASS。
  四项 finding 只推进为 `FIXED_PENDING_REREVIEW`；T003 必须在新双 digest subject 上独立关闭。
- `BSS-S1-P3-T003` 在 base HEAD
  `287488a303d2da06fbfbe8d9f7195e603855ca70`、20-path subject 上完成第二轮整体重审；Python 规范实现与
  独立 Ruby 实现同得 Task Pack digest
  `7380b917d699a63300ca461a98a033a49a6ee699eb45b1032fd726bf6475d9dd` 和完整 Stage source digest
  `bc429110668964ba654d091462f36ff0a783c5f16d9073038ca60be2c0caaab6`。
- registry/legacy projection/制品 SHA、52 个真实 unittest case、manifest/hash、四个 workflow 原始 run
  blocks、基线公开扫描、PyYAML、官方 checksum 的 actionlint、四发现文档、44 ACC/23 REQ/9 CAP/7 NG
  追溯与 archive mutant kill 均 PASS；`S1-R002/R003/R004` `CLOSED`。
- `S1-R001` 未关闭：intent-to-add index fixture 的 porcelain 非空，但 cached diff 与 digest helper 均 exit 0，
  没有满足“index 必须为空”的 fail-closed 合同。
- 新增四个 P1 finding：ZIP 反斜杠 traversal path、带 DEFLATED 凭据内容的 directory entry、GitHub 2026
  `ghs_APPID_JWT` installation token，以及无尾分隔符的 macOS/Linux/Windows user-home path 均被安全 helper
  exit 0 放行。`ACC-S1-006` 与 `ACC-S0-006` FAIL，Stage verdict `FAIL`。
- 按确定性循环追加 `BSS-S1-P3-T004/T005`；唯一下一 Task 是 T004，Publish 继续禁止。
- `BSS-S1-P3-T004` 只整改 `S1-R001/S1-R005/S1-R006/S1-R007/S1-R008`：Stage digest 显式识别
  intent-to-add index；ZIP name 拒绝反斜杠、drive 与 UNC；所有合法 entry 纳入 size accounting 且目录必须
  零 payload；公开扫描补齐当前 `ghs_APPID_JWT` 与三平台 bare-home 边界。
- 整改前 9 个探针均错误 exit 0；整改后扩展的 11 个独立负向探针、20 个目标行为测试、全部 60 个真实
  unittest case、registry、manifest/hash、75 files/200 blobs/125 ZIP entries 基线扫描、四个 workflow 原始
  run blocks 与 whitespace 全部 PASS。五项 finding 只推进为 `FIXED_PENDING_REREVIEW`；唯一下一 Task 是
  `BSS-S1-P3-T005` 独立复审，Publish 继续禁止。
- `BSS-S1-P3-T005` 在 base HEAD `287488a303d2da06fbfbe8d9f7195e603855ca70`、20-path subject 上完成
  第三轮整体重审；规范 Python 与独立 Ruby 同得 Task Pack digest
  `97cc05b82160dd3899462ff09f973124e9b8882f07e509926678bf6155d281aa` 和完整 Stage source digest
  `664bd0415acff4c72a59f2abe47739445a615452b3e8b641a1abfc2127382f15`，评审结束前无漂移。
- 五项原 finding 的失败 Oracle 全部反转，五个回退 mutant 均被杀死，`S1-R001/R005/R006/R007/R008`
  `CLOSED`；registry/制品 SHA、60 tests、manifest/hash、四个 workflow 原始 run blocks、公开基线扫描、
  PyYAML/actionlint、追溯、scope/index/mode/cache 与主树边界均 PASS。
- 新增两个 P1：user-home matcher 的 case/Unicode 变体在普通文件与 ZIP 共 12 个探针 fail open（`S1-R009`）；
  group-only execute 的 `0654` 新文件被 Stage helper 记为 `100755`，Git staged mode 实为 `100644`
  （`S1-R010`）。`ACC-S1-006`、`ACC-S0-006` FAIL，Stage verdict `FAIL`。
- 按确定性循环追加 `BSS-S1-P3-T006/T007`；唯一下一 Task 是 T006，Publish 继续禁止。
- `BSS-S1-P3-T006` 只整改 `S1-R009/R010`：macOS/Windows user root 改为平台大小写语义，三平台用户段
  支持 Unicode，同时保留 ellipsis placeholder 与精确历史例外；Stage digest 改为只按 owner execute bit
  映射 Git mode，并增加 `0644/0654/0755` durable Oracle。
- 原 12 个 plain/ZIP 漏检探针全部反转为非零；5 个 placeholder/历史正例通过且历史 child 仍失败；两个
  回退 mutant 分别产生 10 和 1 个 failure。22 个目标测试、全部 62 个真实 unittest case、manifest/hash、
  75 files/200 blobs/125 ZIP entries 公开扫描、四个 workflow 原始 run blocks 与 whitespace 全部 PASS。
- `S1-R009/R010` 只推进为 `FIXED_PENDING_REREVIEW`；唯一下一 Task 是 `BSS-S1-P3-T007` 独立复审，
  Publish、commit/push 与 Stage 2 继续禁止。
- `BSS-S1-P3-T007` 在 base HEAD `287488a303d2da06fbfbe8d9f7195e603855ca70`、20-path subject 上完成
  第四轮整体重审；规范 Python 与独立 Ruby 同得 Task Pack digest
  `01de05cc56ec1fff7e46e1b18a732b5ca25dc9fc5be3b5dfb264264236f37bc1` 和完整 Stage source digest
  `10b429e25764e43da5a1d97a0ed2d11d7b0bdba851b05d00f8f659af9c6cad22`，评审结束前无漂移。
- 原 12 个 case/Unicode 探针与额外 5 个边界探针非零，16-mode Git/helper 矩阵一致，两个回退 mutant
  被杀死，`S1-R009/R010` `CLOSED`；既有 `S1-R001`–`S1-R008` 的 10 个回退行为 mutant、62 tests、
  registry/制品 SHA、manifest/hash、四个 workflow 原始 run blocks、公开基线扫描、PyYAML/actionlint、
  追溯、scope/index/cache/runtime/main 与 remote/PR 边界均 PASS。
- 新增 `S1-R011`（P1）：closing backtick 后分别追加 `/private`、反斜杠 child 与 suffix，在
  普通文件/DEFLATED ZIP 共 6 个探针全部 fail open；精确正例通过、反引号内 child 失败，定位为历史
  allowlist 的 closing-backtick 右边界缺失。`ACC-S1-006` FAIL，Stage verdict `FAIL`。
- 按确定性循环追加 `BSS-S1-P3-T008/T009`；唯一下一 Task 是 T008，Publish 继续禁止。
- `BSS-S1-P3-T008` 只整改 `S1-R011`：closing backtick 后只允许 EOF、Unicode whitespace 或显式句末/
  闭合标点；slash、反斜杠、ASCII/Unicode token、下划线、连字符、数字、`@` 与非法 UTF-8 continuation
  均 fail closed。
- 原 6 个 fail-open 探针全部反转；扩展后的 8 类 continuation 在普通文件/DEFLATED ZIP 共 16/16 非零，
  4 类合法右边界通过且反引号内 child 继续失败；移除右边界检查的回退 mutant 产生 16 failures、0 errors。
  15 个目标测试、全部 63 个真实 unittest case、registry、manifest/hash、75 files/200 blobs/125 ZIP entries
  公开扫描、四个 workflow 原始 run blocks 与 whitespace 全部 PASS。
- `S1-R011` 只推进为 `FIXED_PENDING_REREVIEW`；唯一下一 Task 是 `BSS-S1-P3-T009` 独立复审，Publish、
  commit/push 与 Stage 2 继续禁止。
- `BSS-S1-P3-T009` 在 base HEAD `287488a303d2da06fbfbe8d9f7195e603855ca70`、20-path subject 上完成
  第五轮整体重审；规范 Python 与独立 Ruby 同得 Task Pack digest
  `91eada4c7cdffcaee519a78da9ff32250c5aabae817e3503a19582039f183433` 和完整 Stage source digest
  `a37cbceb6ef90746cd16b5313c35ae627c93ac369a68d78e78408b117f940782`，记录 verdict 前无漂移。
- 8 类 closing-backtick continuation 的 plain/ZIP 16/16 非零，6 个合法右边界通过、3 个历史反例失败，
  回退 mutant 被 16 failures、0 errors 杀死，`S1-R011` `CLOSED`；`S1-R001`–`S1-R010` 的 11 个回退
  mutant variant 与 16-mode Git/helper 矩阵全部 PASS。
- registry preservation/三项制品 SHA、63 tests、3 manifests + 1 SHA256SUMS、75 files/200 blobs/125 ZIP
  entries、四个 workflow 原始 run blocks、PyYAML/actionlint/官方 tag、四发现文档、44/23/9/7 追溯、
  scope/index/cache/runtime/main 与 PR mergeability 全部 PASS；main 增量与本 Stage subject 零重叠。
- 无新增 finding，ledger 23/23 `CLOSED`，Stage 1 Review verdict `PASS`；唯一下一 Task 是
  `BSS-S1-P4-T001` Stage 1 Publish，真实新 workflow PR check 留给该 push，成功前不得进入 Stage 2。
- `BSS-S1-P4-T001` 重新封印 Stage 1：Task Pack/source digest 分别为 `336ff05d...d570b` 与
  `75b9bda1...b22ab`，current、staged tree `8ca5889b...e3` 与 proposed merge tree
  `ae6c8cf4...19c` 三个快照均重放 63 tests、manifest/hash 与公开安全四道 workflow 门并 PASS。
- Stage 1 commit `8308d170325c2ce35581d3fb757a2b731f7803dc` 已 push 到 draft PR #76；本地、remote、
  PR head 一致，完整 21-path diff 一致，PR `OPEN`/`DRAFT`/`CLEAN`，`dual-plane` 与 Stock Skill
  `validate` 两项真实 CI 均 `SUCCESS`。该外部叶子由下一 Stage 首个本地 Task 查询后回填为 `DONE`。

### Stage 2

- `BSS-S2-P1-T001` 按远端 commit/PR/diff/CI 实证回填 `BSS-S1-P4-T001`；active registry validator
  继续 PASS，唯一 current 仍是 `stock-commercial-opportunities=3.0.0 (v3)`。
- 使用官方 `skill-creator/scripts/init_skill.py` 初始化
  `task-pack/skill_draft/bottleneck-serenity-skill/`；只生成 `SKILL.md` 与 `agents/openai.yaml`，未创建
  resource/example 占位，未导入输入包。
- canonical basename、frontmatter `name` 与 UI `display_name` 均精确等于 `bottleneck-serenity-skill`；
  default prompt 调用 `$bottleneck-serenity-skill`，官方 quick validator 与独立结构/YAML 断言 PASS。
- 本 Task 未执行 import/rename/semantic parity、metadata/project/registry/release、Review/Publish、
  commit/push 或本机 runtime 安装；唯一下一 Task 为 `BSS-S2-P1-T002`。
- `BSS-S2-P1-T002` 封印输入归档 SHA `541fce14...90815` 与 53-entry 集合：45 files、8 directories、
  152,598 bytes payload，`unzip -t`、canonical path/type/mode 安全检查、源 validator 和源 9/9 tests PASS。
- 新建 `SOURCE_INVENTORY.md`，以完整 53 行 source path/type/mode/SHA 记录唯一决定：
  `IMPORT 43 / MIGRATE 9 / EXCLUDE 1`；ledger 与 ZIP 顺序及集合精确相等，inventory SHA 为
  `01e0c912775649c72915751e7882779d9ad1d43c6903f1fe0d5e888a70962a94`。
- 原样导入 scripts/references/schemas/templates/evals/examples/tests：36 个文件 bytes/SHA 与 ZIP 全等，
  7 个目录、5 个 executable script 及其余文件 mode 全等；未把 README/install、build/provenance/notice
  或冲突的源 `VERSION=0.1.0` 塞入 canonical root。
- 导入后官方 skill-creator validator、源 validator 与 9/9 tests PASS；旧身份保留为
  `21 matches / 14 files` 的 T003 输入，本 Task 未静默改名或改语义。
- GitHub workflow 四个原始 run blocks 本地重放 PASS：active registry current 无漂移，72 tests、
  3 manifests + 1 SHA256SUMS，以及 114 files/239 blobs/125 ZIP entries 公开安全扫描全部通过。
- 本 Task 未执行 rename/semantic parity、metadata/project/registry/release、Review/Publish、commit/push
  或本机 runtime 安装；唯一下一 Task 为 `BSS-S2-P1-T003`。
- `BSS-S2-P1-T003` 只执行三项冻结身份映射：旧 display/kebab/snake-form token 分别 15/5/1 处，共
  21 matches / 14 files；token 以 SHA `25fd0e9c...8015` / `13b191ed...66e1` / `15684214...f5f39a9`
  绑定，不把旧字面量重新放入 current release；通用方法术语、阈值、评分与硬门逻辑未改写。
- 36 个 imported resource files 的逐字节 forward-transform Oracle PASS：14 个 renamed files 精确等于源 bytes
  应用三项 replacement，另 22 个文件逐字节不变；source tree digest 为 `48f87244...3960c`，expected 与
  actual renamed tree digest 均为 `ae21e31b...16fb4`。
- canonical path/content 的旧身份大小写不敏感命中归零；新 invocation、三个 schema `$id` 与唯一 completion
  event `bottleneck_serenity_skill.thesis.completed` 精确成立。`SOURCE_INVENTORY.md` SHA 仍为
  `01e0c912...62a94`，source path/hash 历史未改写。
- 官方 quick validator、导入 validator、9/9 imported unittest、8 个 JSON 解析、两个 example parity 与
  whitespace 检查 PASS；GitHub workflow 四个原始 `run` blocks 本地重放继续通过 active registry、
  72 tests、3 manifests + 1 SHA256SUMS 及 114 files/239 blobs/125 ZIP entries 公开安全门。
- 本 Task 未执行 T004 semantic parity、metadata/project/registry/release、Review/Publish、commit/push 或
  本机 runtime 安装；唯一下一 Task 为 `BSS-S2-P1-T004`。
- `BSS-S2-P1-T004` 将审计边界精确冻结为 T002 导入的 36 个 resources；源 `SKILL.md` 仍按 inventory
  留给 T005 Metadata 重构，未把尚未发生的入口迁移伪称完成。
- 独立 Ruby identity-neutral diff 覆盖 8 Python、8 JSON、4 CSV、16 Markdown：36/36 相等、
  `NON_IDENTITY_DIFFS=0`，neutral tree SHA 为 `69b20481...a840d`。8/8 neutral AST、8/8 JSON semantic
  object、4/4 CSV row matrix 也分别同 digest。
- source/canonical 各 9/9 tests PASS；34 个 score 正例、4 个失败输入、5 个 evidence 与 5 个 portfolio
  case 双运行完全一致，behavior SHA 为 `d1badec3...c92a8`。几何聚合、硬 flag、60/55/60/50/45 门槛、
  三个时钟、独立一手证据、根因聚类与 7-file 历史快照覆盖保护均通过专门 Oracle。
- 角色中立搜索、负向搜索、系统需求→每股收益桥、价格不作为基本面反证、append-only 历史与无交易边界
  均保持 neutral-byte-equal；Python import 仅标准库，网络/券商模块为 0。
- 版本结论：输入 `0.1.0` 是已排除、未登记的三段源包值；目标 `0.0.0.1` 是冻结 numeric-quad 首版，
  禁止跨 scheme 比较。身份 API 变化发生在首次激活前，active registry/release 和项目外运行时消费者均为 0；
  核心语义 diff 为零，因此保持 `0.0.0.1`，无需用户版本决策。
- `ACC-S2-012` Producer evidence 判定 `PASS`，但仍须由 Stage 2 Review 在 T005/T006 等完成后的完整
  subject 上独立复验；四个 GitHub workflow 原始 `run` blocks 本地重放通过 active registry、72 tests、
  3 manifests + 1 SHA256SUMS 和 114 files/239 blobs/125 ZIP entries 公开安全门。
- 本 Task 未执行 Metadata/Project/registry/release、Review/Publish、commit/push 或本机 runtime 安装，
  唯一下一 Task 为 `BSS-S2-P2-T001`。
- `BSS-S2-P2-T001` 将源 `SKILL.md` 重构为 204 行 stable-ID 入口；frontmatter 仅保留 name/description，
  SHA-256=`afc2d411...32ffc`，五种 mode、四门、三时钟、rent-capture、valuation/red-team、几何评分硬门、
  causal portfolio、append-only 与 research-only/no-order 语义均保留。
- 入口显式路由 11 references、4 runtime scripts、3 schemas 与四类 bundled resource；官方 quick validator、
  项目 validator、9/9 tests、8/8 JSON、UTF-8 静态合同与 whitespace 全部 PASS。T004 的 36-file resource tree
  SHA 仍为 `ae21e31b...16fb4`，旧身份命中为 0。
- 官方 generator 以冻结的 display name、57-char short description 与含唯一精确调用
  `$bottleneck-serenity-skill` 的 default prompt 生成 `agents/openai.yaml`；隔离重生成 byte-identical，SHA-256=
  `e90b9449...dc27`。
- 源 provenance/notice hashes 保持 `0fb17bab...89f9` / `7b2c21c8...885e`，canonical Skill 中均不存在；
  `SOURCE_INVENTORY.md` 仍把二者唯一分配给 T006 的外层 `LICENSE_AND_ATTRIBUTION.md`，inventory SHA 未变。
- 正向只读前测以 2024-12-31 cutoff 输出完整 `WATCH_EVIDENCE` 研究合同；负向只读前测拒绝实时报价猜测、
  broker/order、杠杆期权与保证收益。两者均无网络、文件写入或外部副作用。
- GitHub workflow 四个原始 run blocks 本地重放继续通过 active registry、72 tests、3 manifests + 1
  SHA256SUMS 及 114 files/239 blobs/125 ZIP entries 公开安全门；Task Graph 为 34 DONE / 18 PENDING /
  6 CONDITIONAL，首个 pending 为 T006。
- 本 Task 未执行 Project/registry/release、Stage Test/Review/Publish、commit/push 或 runtime 安装；唯一下一
  Task 为 `BSS-S2-P2-T002`。
- `BSS-S2-P2-T002` 新增 outer `AGENTS/README/VERSION/CHANGELOG/LICENSE_AND_ATTRIBUTION/
  RESTORE_AND_VERIFY` 并追加 `SOURCE_INVENTORY` destination evidence；双 VERSION 均为 `0.0.0.1`，项目明确
  保持 `REGISTRY_NOT_ACTIVE / RELEASE_NOT_BUILT / NOT_INSTALLED`。
- README/AGENTS 逐项覆盖用户、五种 mode、默认值、输入/输出 schema namespace、Owner、adapter、source-only、
  freshness 与无交易/无服务边界；源 quickstart 的 runtime 安装命令未复制。
- 完整历史许可审计覆盖 38 target text files × 1,951 upstream blobs：exact file=0、四行 match=1；唯一实质
  相似面来自 muxuuu MIT scaffolding，已保守标注 `POSSIBLE_ADAPTATION / MIT-COVERED` 并保存完整 notice。
  两个无明确 license 仓只作事实/思想引用，零 exact/四行 match，无 code/data/media payload。
- `SOURCE_INVENTORY` 保持 53 行与 43/9/1 决定不变，仅追加九项 destination completion 与 license evidence，
  SHA-256 更新为 `e46b0eb4...b23d`；源 `0.1.0` 继续排除且不建伪 archive。
- `RESTORE.md` 状态句误写按 architecture/ACC/同仓约定纠正为 `RESTORE_AND_VERIFY.md`；当前 source checks
  可执行，未实现 release/hash 明确 `NOT_AVAILABLE`，proposed-tree/clean-checkout 最终 Oracle 留给 T008。
- 官方 validators、9/9 tests、8 JSON、双接口、source/license contract、5-script 标准库与零
  network/broker/order/daemon/scheduler capability、120 files/245 blobs/125 ZIP entries 安全扫描全部 PASS；
  T004 resource tree SHA 不变。
- GitHub workflow 四个原始 run blocks 本地重放继续通过 active registry、72 tests、3 manifests + 1
  SHA256SUMS 与 120 files/245 blobs/125 ZIP entries 公开安全门；Task Graph 为 35 DONE / 17 PENDING /
  6 CONDITIONAL，首个 pending 为 T007。
- 本 Task 未执行 registry prep/release/Stage Test/Review/Publish、commit/push 或 runtime 安装；唯一下一 Task
  为 `BSS-S2-P2-T003`。
- `BSS-S2-P2-T003` 参数化既有临时仓 registry fixture，并新增精确 activation-plan Oracle；它逐字段冻结
  stable ID/display name、numeric-quad `0.0.0.1`、major `0`、SOURCE_ONLY/PROHIBITED、两个 canonical path、
  两条 VERSION 来源、六个发现面、完整 release filename 与空 archive 数组。
- Fixture 使用临时合成 release 的动态实算 SHA，通过真实 validator 核对 release bytes、`SHA256SUMS` 与
  manifests；该 SHA 不持久化、不进入 source/active registry，也不冒充 T004 的真实候选 SHA。
- 定向 Oracle 1/1、完整 registry suite 12/12 PASS；active registry validator 仍只输出
  `stock-commercial-opportunities=3.0.0 (v3)`，before/after SHA-256 均为 `45c43e54...9646`，Git diff 为空且
  active skills 集合不含新 stable ID。
- GitHub workflow 四个原始 run blocks 本地重放继续通过 active registry、73 tests、3 manifests + 1
  SHA256SUMS 与公开安全门；Task Graph 为 36 DONE / 16 PENDING / 6 CONDITIONAL，首个 pending 为 T008。
- 本 Task 未构建 release、激活 registry/发现面、执行 Stage Test/Review/Publish、commit/push 或 runtime
  安装；唯一下一 Task 为 `BSS-S2-P2-T004`。
- `BSS-S2-P2-T004` 新增 mode `0755` 的标准库 deterministic builder：默认 build、`--activate` 与
  `--verify` 分离；activation 在写任何 SHA 消费面前先从当前 Task Pack byte-identical 重现现有 ZIP。
- ZIP 固定完整 v0.0.0.1 filename/root、UTF-8 byte order、1980 timestamp、`ZIP_STORED` 与
  `0755/0644` mode，拒绝 unsafe path、duplicate、symlink、non-regular/cache、错误 type 与 manifest/file-set
  漂移；预备和最终 candidate 的连续双构建均同 SHA。
- T003 的 14-field entry plan 以真实 SHA 物化；existing v3 projection 保持，new entry 使用
  `numeric-quad=0.0.0.1`、major `0`、SOURCE_ONLY/PROHIBITED 与 `superseded_archives=[]`，不建伪 archive。
- 无环职责保持 task files→task manifest→release→release SHA→sums/registry，outer project→backup
  manifest；真实 SHA 只写三个消费面，backup 最后生成，Task Pack/inventory/changelog 不复制该值。
- 六个 README/AGENTS 发现面同步 exact active claim；project CHANGELOG/SOURCE_INVENTORY/RESTORE 记录候选、
  rebuild 与 source-only/not-installed 边界，不提前声称 Stage Review/GitHub Publish 已完成。
- builder activate/verify、独立 ZIP/DAG 审计、registry 双 current、官方/项目 validators、9 project tests、
  73 repository tests、4 manifests + 2 SHA256SUMS 和公开安全门全部 PASS；Task Graph 为 37 DONE / 15
  PENDING / 6 CONDITIONAL，首个 pending 为 `BSS-S2-P3-T001`。
- 本 Task 未执行 Stage Test/Review/Publish、commit/push 或 runtime 安装；唯一下一 Task 为
  `BSS-S2-P3-T001`。
- `BSS-S2-P3-T001` 新增仓级 durable release/hash-DAG Oracle：5 个 case 覆盖 active verify、两个 manifest、
  deterministic ZIP、registry 双 current、existing v3 projection、三 SHA 消费面与隔离双构建；stale Task
  Pack、release/sums/registry/backup/discovery drift、manifest drift 与 symlink 共 8 类变异全部 fail closed。
- canonical Skill 新增标准库 schema contract tests：全部 8 个 JSON 可解析，三份 Draft 2020-12 schema 的已用
  keyword/local `$ref` 可执行，两个示例与 synthetic evidence 正例通过；missing required、三个 range、
  additional property、date、enum、minLength 共 8 类反例被拒绝。未知 schema keyword 默认失败，避免
  “文件存在即通过”。
- source/Task Pack 改变后重算 task manifest，从新 subject 连续双构建同 bytes，并用 `--activate`/`--verify`
  刷新完整无环 DAG；实际 release SHA 仍只进入 sums/registry/backup 三个许可消费面，不写回 release 输入。
- 官方/项目 validators、13 canonical tests、82 个仓库 tests（9 files/3 suites）、registry 双 current、
  4 manifests + 2 SHA256SUMS、ZIP/hash DAG、公开安全与 whitespace 门全部 PASS；最终 proposed-tree 与 clean
  sparse-checkout seal 仍保留给 Review PASS 后的 Publish Task。
- Task Graph 为 38 DONE / 14 PENDING / 6 CONDITIONAL，首个 pending 为 `BSS-S2-P4-T001`；本 Task 未执行
  Stage Review/Publish、commit/push 或 runtime 安装。
- `BSS-S2-P4-T001` 在任何 subject 修改前由 Python 规范实现与独立 Ruby 实现锁定 47-file Task Pack 和
  61-path 完整 Stage source；双实现分别同得 taskpack digest
  `cdbe9cf21c1f2929b79b47cb41011f914cdc3cd6a233c42bfcdd7d2d74e9f347` 与 stage digest
  `e65847005cee5e03a949168e724ca01928731d0e0551530d1da22c09d889609c`，base HEAD 为
  `8308d170325c2ce35581d3fb757a2b731f7803dc`。
- 迁移 53-entry/43-9-1 决定、36-file semantic parity、身份/metadata/双 VERSION、old token、registry 双
  current、deterministic ZIP、三 SHA 消费面、两个 manifest、六发现面、source-only 边界与临时 proposed-tree
  双构建均 PASS；44 ACC/23 REQ/9 CAP/7 NG 追溯与 58 个 Task ID 精确，官方/项目 validators、13 canonical
  tests、82 个仓库 tests、四个 workflow 原始 run blocks、4 manifests + 2 SHA256SUMS 与公开安全门均 PASS。
- Review 新增两个 P1 finding：`S2-R001` 为 canonical completion/input/artifact versioning 合同与 Task Pack、
  README、SKILL 及 scaffold 不一致，现有 schema tests 不覆盖跨文档 projection；`S2-R002` 为许可相似性审计
  仍只声明覆盖 38 个 target files，而 current canonical 已有 39 个，且 blob eligibility/规范化算法未固化，
  精确计数不可独立复现。
- Stage 2 Review verdict=`FAIL`：`ACC-S2-010/013` FAIL，最终 clean-checkout seal 仍保留给 Publish；启用
  `BSS-S2-P4-T002/T003` 为 `PENDING`，两个 finding 保持 `OPEN`。Task Graph 为 39 DONE / 15 PENDING /
  4 CONDITIONAL，首个 pending 为 T002；本 Task 未整改、Publish、commit/push 或安装 runtime。
- `BSS-S2-P4-T002` 只整改 `S2-R001/S2-R002`：Task Pack、项目 README 与 canonical integration 的
  input/completion projection 逐字段/值/顺序相等；五字段 runtime artifact envelope 已落实到三 schema、
  JSON/CSV templates、examples、initializer 与三个 JSON-producing validators/analyzers。
- canonical durable Oracle 从 13 增至 19 cases，覆盖 schema vocabulary/nullable string、全部 envelope field
  missing/rename、错误 schema/Skill version、未来 cutoff、UUID/scaffold validity 与 overwrite；仓级 projection
  Oracle 的正例及三类跨文档 mutant 均 PASS。
- 新增标准库 full-history 许可审计器、39-file 确定性报告和 3-case 仓级 fixture/mutation Oracle。四个冻结
  upstream 共 2,489 reachable blob instances / 2,485 text-eligible；两次完整重算报告 byte-identical，
  exact=`0`、four-line pairs=`3`、token20 pairs=`1`，两个无明确许可仓 exact/token20 均为 `0`。
- `LICENSE_AND_ATTRIBUTION.md`、`SOURCE_INVENTORY.md`、`RESTORE_AND_VERIFY.md` 与 discovery/architecture 已同步；
  `S2-R001/R002` 只推进为 `FIXED_PENDING_REREVIEW`。Task Graph 为 40 DONE / 14 PENDING / 4 CONDITIONAL，
  唯一下一 Task 是 T003；本 Task 未 Re-review、关闭 finding、Publish、commit/push 或安装 runtime。
- `BSS-S2-P4-T003` 在任何 subject 修改前冻结 base HEAD
  `8308d170325c2ce35581d3fb757a2b731f7803dc` 与 66-path Stage 2 subject；Python 规范实现和独立 Ruby 实现
  同得 47-file `taskpack-tree-sha256-v1`=
  `7f3e9238a81de7a0d6d738411d2709b62831de3a16acb85a7f93900daeec5486` 及
  `stage-worktree-source-sha256-v1`=
  `d956354782afb6979a68519cce79e5b465c14d5203c751aade0c231da0847b0b`，记录 verdict 前复算无漂移。
- `S2-R002` `CLOSED`：四个 fresh、非 shallow、credential-free HTTPS clone 上，规范 Python 重算报告与
  committed report byte-identical；独立 Ruby 实现同得 39 targets、2,489 reachable blobs、2,485 eligible
  text blobs、exact=`0`、four-line pairs=`3`、token20 pairs=`1`，并逐 pair/evidence 精确相等。冻结 commit、
  origin、license history、current target hash/file set 与三类 mutation Oracle 全部 PASS。
- `S2-R001` 仍为 `OPEN`：三条 JSON 运行时入口都用 `payload.get("previous_version")`，使字段缺失与显式
  首版 `null` 不可区分。对 score/evidence/portfolio 分别删除或改名该字段的 6 个独立探针全部被接受并重新
  输出 `previous_version:null`；schema 层虽拒绝，但现有 19 个 canonical case 未覆盖三条 runtime nullable
  presence 分支，因此 `ACC-S2-013` 的 missing/rename fail-closed Oracle 仍 FAIL。
- 53-entry/43-9-1 来源映射、36-file 核心语义等价、identity/version/UI、registry 双 current、候选 release/
  hash DAG、六发现面、source-only/runtime 边界、19 canonical tests、93 repository tests、四个 workflow 原始
  run blocks、4 manifests + 2 SHA256SUMS 与 129 files/301 blobs/172 ZIP entries 公开安全门全部 PASS。
  `ACC-S2-005/010/012` PASS，`ACC-S2-013` FAIL；Publish 所属 proposed-tree/clean-checkout seal 未提前执行。
- Stage 2 Re-review verdict=`FAIL`。按最大 suffix+1/+2 追加 `BSS-S2-P4-T004/T005` 为 `PENDING`；唯一下一
  Task 是 T004，只能整改 `S2-R001` 并推进到 `FIXED_PENDING_REREVIEW`，再由 T005 在新双 digest subject
  上关闭。Task Graph 为 60 total / 41 DONE / 15 PENDING / 4 CONDITIONAL；本 Task 未修复、Publish、
  commit/push 或安装 runtime。
- `BSS-S2-P4-T004` 只整改 `S2-R001`：score/evidence/portfolio 三条 `_artifact_metadata` 在读取 nullable
  值前先要求 `previous_version` key 存在，继续允许显式首版 `null` 与非空 lineage ID，并继续拒绝错误类型、
  空字符串、未来 cutoff 和错误 schema/Skill version。
- 整改前删除/改名 `previous_version` 的 6/6 runtime 探针全部被接受并输出 `null`；整改后 6/6 均以精确
  `previous_version is required` 拒绝。三组持久化测试同时保护非空 lineage 正例；canonical suite 从 19 增至
  22 cases。临时副本精确删除三处 presence 分支后，新增测试产生 6 failures，证明回退 mutant 被杀死。
- canonical 六文件变化使旧 39-target 许可报告按预期因 hash/size drift 非零；四个 fresh、非 shallow、
  credential-free HTTPS clone 上重新生成后，再次完整复算 byte-identical。计数保持 2,489 reachable / 2,485
  eligible、exact=`0`、four-line=`3`、token20=`1`，未改变 `S2-R002` 的关闭结论或许可归属。
- `ACC-S2-013` 的完整验收能力与主制品集合首次成立于 T004，Producer 按稳定 Owner 规则转移到本 Task；
  `S2-R001` 只推进为 `FIXED_PENDING_REREVIEW`，不得由 Builder 自行关闭。Task Graph 为 60 total / 42 DONE /
  14 PENDING / 4 CONDITIONAL，首个 pending 为 T005；本 Task 未执行 T005、Publish、commit/push 或安装 runtime。
- `BSS-S2-P4-T005` 在任何 subject 修改前冻结 base HEAD
  `8308d170325c2ce35581d3fb757a2b731f7803dc` 与 66-path Stage 2 subject；Python 规范实现和独立 Ruby 实现
  同得 47-file `taskpack-tree-sha256-v1`=
  `f92345a4d7ee05f84dba2c88c2c88ebbc0156c2ccc09f8cc6fceb68c36bdd6f0` 及
  `stage-worktree-source-sha256-v1`=
  `795ac48e7293d1604724cd107ba3c73e90f2ba9308921b39c9c2c0faa251af63`，记录 verdict 前复算无漂移。
- `S2-R001` `CLOSED`：三条 runtime missing/renamed `previous_version` 6/6 精确拒绝，显式 `null`/lineage
  6/6 通过；22 canonical cases PASS，删除三处 presence 分支的回退 mutant 产生 6 failures。三份 machine
  projection、三 schema、四个 static artifact 与 scaffold 的四 JSON/一 CSV envelope 全部一致，`ACC-S2-013` PASS。
- 完整 Stage 2 重审 PASS：五个输入 artifact 与 53-entry/43-9-1 ledger 精确；8 个 Python 源函数零删除，
  30+5+5 个 core valid-input behavior 相等；identity/version/UI、registry、release/hash DAG、runtime 边界、
  44 ACC/23 REQ/9 CAP/7 NG 追溯、96 tests、四个 workflow 原始 run blocks、4 manifests + 2 SHA256SUMS 与
  129 files/301 blobs/172 ZIP entries 公开安全门均 PASS。
- 四个 fresh full-history clone 上规范 Python 报告 byte-identical；独立 Ruby target/report 复核同得
  39/2,489/2,485 与 exact/four-line/token20=`0/3/1`。无新增 finding，ledger 25/25 `CLOSED`，Stage 2
  verdict=`PASS`；Task Graph 为 43 DONE / 13 PENDING / 4 CONDITIONAL，唯一下一 Task 是 P5 Publish。

## Stage review ledger

状态：`OPEN` → `FIXED_PENDING_REREVIEW` → `CLOSED`。Builder 不得把自己的修复直接标为 `CLOSED`。

| Finding | Severity | Reviewed subject | Remediation Task | 状态 | Remediation evidence | Closure evidence |
|---|---|---|---|---|---|---|
| `S0-R001` 端到端追溯缺失 | `P1` | `1fbfff05...a2315` | `BSS-S0-P2-T008` | `CLOSED` | Producer=首次建立完整验收能力/主制品集合的稳定 Owner；例行刷新派生 hash 不转移，责任性变更才转移 | `BSS-S0-P2-T009 — Producer 稳定性、44 行映射与引用复验 PASS` |
| `S0-R002` Task Pack 未封印 | `P1` | `d2794667...883e4` | `BSS-S0-P2-T002` | `CLOSED` | 新增 `VERSION`、完整 manifest 与 digest 规则 | `BSS-S0-P2-T003 — 文件集合、哈希与锁定 digest PASS` |
| `S0-R003` finding/等级规则缺失 | `P1` | `b97ef403...8edcd` | `BSS-S0-P2-T004` | `CLOSED` | ledger 显式记录整改 Task、整改证据、状态与独立关闭证据 | `BSS-S0-P2-T005 — 七列 schema、状态与关闭 Owner 复验 PASS` |
| `S0-R004` Stock Skill 无 CI | `P1` | `d2794667...883e4` | `BSS-S0-P2-T002` | `CLOSED` | 加入 `BSS-S1-P2-T003`、`ACC-S1-006` 与专用 workflow 契约 | `BSS-S0-P2-T003 — Task/ACC/架构三处一致` |
| `S0-R005` release/恢复契约不足 | `P1` | `d2794667...883e4` | `BSS-S0-P2-T002` | `CLOSED` | 冻结 ZIP root/payload/order/time/mode/build/verify/restore | `BSS-S0-P2-T003 — release/restore 条款逐项 PASS` |
| `S0-R006` 许可与核心逻辑门缺失 | `P1` | `d2794667...883e4` | `BSS-S0-P2-T002` | `CLOSED` | 加入许可归属、项目文件、语义审计 Task 与 Acceptance | `BSS-S0-P2-T003 — REQ/Task/ACC 映射 PASS` |
| `S0-R007` 假设/四段版本规则不完整 | `P2` | `d2794667...883e4` | `BSS-S0-P2-T002` | `CLOSED` | 加入假设冻结点与无前导零 numeric-quad 正则 | `BSS-S0-P2-T003 — 生命周期与正则复验 PASS` |
| `S0-R008` Stage 0 worktree Oracle 冲突 | `P1` | `b97ef403...8edcd` | `BSS-S0-P2-T004` | `CLOSED` | pre-publish 仅要求本项目 scoped changes；Publish commit 后才要求干净 | `BSS-S0-P2-T005 — main clean、8 个 changed file 全在本项目，复验 PASS` |
| `S0-R009` 需求权威等级过高 | `P2` | `b97ef403...8edcd` | `BSS-S0-P2-T004` | `CLOSED` | 新增 `DERIVED`/`SOURCE_MANDATED`，修正 `REQ-022/REQ-023` 与证据 | `BSS-S0-P2-T005 — taxonomy 与两行 authority 复验 PASS` |
| `S0-R010` 重审失败后无合法循环 Task | `P1` | `849caf74...ac5d5` | `BSS-S0-P2-T006` | `CLOSED` | Stage 4 终态 Phase 改为 `Publish`，明确其交付/合并语义及成功后进入 Cleanup | `BSS-S0-P2-T007 — 五 Stage 正常/失败路由复验 PASS` |
| `S0-R011` subject digest 算法缺失 | `P1` | `1fbfff05...a2315` | `BSS-S0-P2-T008` | `CLOSED` | 参考实现检查 Root/manifest/非空 subject，并拒绝 Root/entry symlink 与非普通文件；六类负例非零 | `BSS-S0-P2-T009 — 双实现同 digest，八类负例全部 fail closed` |
| `S0-R012` release/manifest 封印图不可执行 | `P1` | `f17ad7df...7636ad` | `BSS-S0-P2-T010` | `CLOSED` | task manifest 不越 Root；release SHA 只进入 sums/registry/backup；首次 registry 激活等待真实 SHA；backup 最后生成；Publish 从 frozen source 重建并 staged-tree/clean replay；外部终态证据不反写 | `BSS-S0-P2-T011 — DAG/反向边、双构建、三消费面、原子激活与 proposed-tree replay 全 PASS` |
| `S1-R001` Stage Review digest 未绑定完整 Stage source | `P1` | `taskpack=7380b917...d9dd; stage=bc429110...aab6; base=287488a3; paths=20` | `BSS-S1-P3-T004` | `CLOSED` | 保留完整 Stage source 绑定；cached index 检查新增 `--ita-visible-in-index`，真实 `git add -N` fixture 现 fail closed | `BSS-S1-P3-T005 — intent-to-add 原 Oracle 非零且移除该选项的回退 mutant fail open，复验 PASS` |
| `S1-R002` CI 零 test case 仍可绿色放行 | `P1` | `taskpack=7380b917...d9dd; stage=bc429110...aab6; base=287488a3; paths=20` | `BSS-S1-P3-T002` | `CLOSED` | helper 用 `countTestCases()` 和唯一正数 marker；empty file/failing case 非零、positive case=1 | `BSS-S1-P3-T003 — empty=nonzero、failing=nonzero、positive=1，52 个真实 case，复验 PASS` |
| `S1-R003` 公开安全门漏检 `github_pat_` | `P1` | `taskpack=7380b917...d9dd; stage=bc429110...aab6; base=287488a3; paths=20` | `BSS-S1-P3-T002` | `CLOSED` | plain/ZIP 合成 fine-grained PAT 均失败；精确历史 allowlist 通过而 child 失败；全仓扫描 PASS | `BSS-S1-P3-T003 — GitHub 官方前缀、plain/DEFLATED ZIP PAT 与窄 allowlist 复验 PASS` |
| `S1-R004` non-object archive 拒绝分支无测试保护 | `P1` | `taskpack=7380b917...d9dd; stage=bc429110...aab6; base=287488a3; paths=20` | `BSS-S1-P3-T002` | `CLOSED` | `null/string/list` 三个 CLI fixture 非零；删除拒绝分支的 mutant 被三项 failure 杀死 | `BSS-S1-P3-T003 — 三类真实 CLI fixture PASS；移除 error、保留 continue 的 mutant 被 3 failures 杀死` |
| `S1-R005` ZIP 反斜杠 traversal path 被当作 canonical | `P1` | `taskpack=7380b917...d9dd; stage=bc429110...aab6; base=287488a3; paths=20` | `BSS-S1-P3-T004` | `CLOSED` | 反斜杠、drive-relative/absolute、UNC、absolute/traversal durable matrix 全部非零 | `BSS-S1-P3-T005 — 11 类 path matrix 与回退 safe-name mutant 复验 PASS` |
| `S1-R006` ZIP directory entry 的压缩 payload 未扫描 | `P1` | `taskpack=7380b917...d9dd; stage=bc429110...aab6; base=287488a3; paths=20` | `BSS-S1-P3-T004` | `CLOSED` | 所有合法 entry 计入 size accounting；非零 directory payload 非零、空目录正例通过 | `BSS-S1-P3-T005 — 非空/空目录、低阈值 accounting 与回退 mutant 复验 PASS` |
| `S1-R007` 当前 GitHub stateless App installation token 漏检 | `P1` | `taskpack=7380b917...d9dd; stage=bc429110...aab6; base=287488a3; paths=20` | `BSS-S1-P3-T004` | `CLOSED` | 官方 `ghs_APPID_JWT` 结构的 plain 与 DEFLATED ZIP synthetic fixture 均非零 | `BSS-S1-P3-T005 — 三类 JWT 尾部的 plain/ZIP 与移除模式 mutant 复验 PASS` |
| `S1-R008` 无尾分隔符 user-home 路径漏检 | `P1` | `taskpack=7380b917...d9dd; stage=bc429110...aab6; base=287488a3; paths=20` | `BSS-S1-P3-T004` | `CLOSED` | 三平台 bare home 与 child 均 fail closed；ellipsis placeholder 通过，历史例外仍精确 | `BSS-S1-P3-T005 — 标准 bare/child、双 Windows separator、历史边界与回退 mutant 复验 PASS` |
| `S1-R009` user-home case/Unicode 变体漏检 | `P1` | `taskpack=97cc05b8...281aa; stage=664bd041...82f15; base=287488a3; paths=20` | `BSS-S1-P3-T006` | `CLOSED` | macOS/Windows root 大小写语义与三平台 Unicode 用户段已覆盖 plain/ZIP；ellipsis/历史正例保持；12/12 原探针非零且回退 mutant 被 10 个 subtest failure 杀死 | `BSS-S1-P3-T007 — 原 12 个与额外 5 个边界探针、6 个正例、4 个历史反例及回退 mutant 复验 PASS` |
| `S1-R010` Stage digest execute mode 不等于 Git mode | `P1` | `taskpack=97cc05b8...281aa; stage=664bd041...82f15; base=287488a3; paths=20` | `BSS-S1-P3-T006` | `CLOSED` | 只按 owner execute bit 映射；`0644=0654`、Git=`100644`、`0755` 不同，任一 execute-bit 回退 mutant 被 durable mode 测试杀死 | `BSS-S1-P3-T007 — 16-mode Git/helper 矩阵一致，regular/executable 分离且回退 mutant 被杀死` |
| `S1-R011` 历史路径 allowlist closing-backtick 右边界缺失 | `P1` | `taskpack=01de05cc...37bc1; stage=10b429e2...ad22; base=287488a3; paths=20` | `BSS-S1-P3-T008` | `CLOSED` | closing backtick 后只允许 EOF/Unicode whitespace/显式句末或闭合标点；8 类 plain/ZIP continuation 16/16 非零、4 类正边界通过、反引号内 child 失败，回退 mutant 被 16 failures 杀死 | `BSS-S1-P3-T009 — 新双 digest subject 上 16/16 continuation、6 个正边界、3 个历史反例与 16-failure mutant 复验 PASS` |
| `S2-R001` canonical machine interface/versioning 合同漂移 | `P1` | `taskpack=f92345a4d7ee05f84dba2c88c2c88ebbc0156c2ccc09f8cc6fceb68c36bdd6f0; stage=795ac48e7293d1604724cd107ba3c73e90f2ba9308921b39c9c2c0faa251af63; base=8308d170325c2ce35581d3fb757a2b731f7803dc; paths=66` | `BSS-S2-P4-T004` | `CLOSED` | 三条 runtime 显式要求 `previous_version` key；missing/rename 6/6 非零，null/lineage 正例 PASS；22 canonical cases PASS，删除 presence 分支的回退 mutant 产生 6 failures；39-target 许可报告双重算 byte-identical | `BSS-S2-P4-T005 — 新双 digest 无漂移；6/6 负向、6/6 正向、6-failure rollback mutant 与完整 Stage 2 重审 PASS` |
| `S2-R002` current payload 许可相似性审计覆盖/算法未封印 | `P1` | `taskpack=7f3e9238a81de7a0d6d738411d2709b62831de3a16acb85a7f93900daeec5486; stage=d956354782afb6979a68519cce79e5b465c14d5203c751aade0c231da0847b0b; base=8308d170325c2ce35581d3fb757a2b731f7803dc; paths=66` | `BSS-S2-P4-T002` | `CLOSED` | 标准库审计器/39-file hash-bound report；2,485 eligible blobs 两次 full-history 重算 byte-identical；算法/target/upstream mutation Oracle PASS；无许可仓 exact/token20=0 | `BSS-S2-P4-T003 — fresh full clones 上规范 Python 报告 byte-identical；独立 Ruby 同得 2,489/2,485、0/3/1 与逐 pair/evidence，PASS` |

### Pending

- Stage 2 review ledger 25/25 `CLOSED`，verdict `PASS`。唯一下一 Task 是 `BSS-S2-P5-T001 — Publish`：
  从复审通过后的 frozen source 重新封印 release/hash DAG，并执行 staged/proposed-tree replay；T005 未提前
  commit/push、安装 runtime 或进入 Stage 3。
