# MooMooAU 当前交接

更新时间：2026-07-26（Australia/Sydney）

## 当前目标与状态

- 本轮只处理 Stage 7/T0705，必须停在 T0706 前。
- 当前候选包：`MMAU-ARCHIVE-TP-2026-07-26-V1.0.28`。
- 不可变直接前序：`taskpack/PACKAGE_MANIFEST.v1.0.27.json`，SHA-256
  `de1ed6df0ba804506a04a30e0f3f943a4e968bf85d7c13b5616cc1b6763ac70a`。
- 唯一状态权威：`machine/status/latest.json` =
  `PROTECTED_GA_NINTH_ATTEMPT_FAILED_CANONICAL_GIT_BLOB_RECOVERY_AUTHORIZED`。
- Protected Oracles 5/43 executed、4 PASS、1 FAILED；final Acceptance 0/34；
  T0705 production workflow 9；final publication 0。

## 已冻结前序

- T0702、T0703、T0704 protected PASS receipts 及全部 failed-attempt ledgers 不可变。
- T0705 九个不同 exact-main head 均只执行 attempt 1、rerun 0；authority 与 identity cleanup
  均 PASS，protected GA 均 FAILED，live schedule hold 均 SKIPPED。
- 第四次独立后验确认六个新增、可恢复且具有 age magic 的 Raw、Processed 与 current pointer
  对象；Timeline snapshot/manifest、Timeline state 和 checkpoint 均未改变。
- 第五次公开输出只有 coarse `PROCESSED_PLAN`。只读 private 数据仓核验确认第五次零 commit、
  零路径变化；已提交阶段顺序把边界限定在 Raw 远端恢复之后、Processed write/Timeline/
  checkpoint/Gmail mutation 之前，精确 root cause 仍 `UNKNOWN`。
- 第六次公开输出只有 coarse `FIRST_IMPORT_RECOVERY`。只读 private 数据仓核验确认第六次零
  commit、零路径变化；已提交顺序把边界限定在 Raw recovery/classification 之后、
  document-envelope 构造与 Processed/Timeline/checkpoint/Gmail mutation 之前。writer/reader
  schema 未改变且 synthetic recovery 通过，精确 root cause 仍 `UNKNOWN`。
- 第七次公开输出只有 coarse `FIRST_IMPORT_POINTER_FETCH`。只读连接核验确认第七次零 commit；
  两个 current pointer 的 Git tree/blob 与 raw media 均为有效、同一声明大小的 age ciphertext，
  但其中一个 Contents JSON inline 表示的解码长度与声明 size/blob 不一致。受保护 exception 未
  检查，精确 root cause 仍 `UNKNOWN`。
- 第八次在 pointer-blob raw-media 绑定修复后仍只输出 `FIRST_IMPORT_POINTER_FETCH`；只读核验
  确认运行窗口 private commit 0、Gmail mutation 0。Owner 随后确认现有 GitHub App 已链接到
  唯一 private 数据仓；这是新的外部前提，不是旧失败根因证明，精确 root cause 仍 `UNKNOWN`。
- 第九次 App repository-scope activation 后仍只输出 `FIRST_IMPORT_POINTER_FETCH`；只读核验
  确认运行窗口 private commit 0、Gmail mutation 0。对同一 pointer 的只读 live A/B 回放证明
  Contents metadata 正确但 raw-media body 非 age/非 canonical，而 metadata SHA 定址的
  Git Blobs API 返回 size、age envelope 和 canonical SHA 全部一致的 ciphertext。
- 一次性 authority 与 production enablement 均已清除；九个失败 head 永不得
  rerun/redispatch。

## T0705 canonical Git Blob recovery 候选

- `GitHubProcessedCiphertextStore.fetch_current` 先读取 bounded Contents metadata，只把
  `type/path/size/sha` 作为绑定；ciphertext 必须由精确
  `GET /git/blobs/{metadata_sha}` 的 JSON base64 body 取得。
- 在解密前核对 Git Blob 响应 SHA、声明/解码 size 与 age envelope，再按
  `blob <size>\0<ciphertext>` 重算 canonical Git blob SHA；任何表示漂移、size mismatch 或
  revision drift 均 fail closed。
- 不扩大 allowlist、端点、权限或 mutation；metadata quarantine、pending replay、远端恢复、
  二次验证、Trash、Timeline 与 checkpoint 顺序保持不变。
- 入口继续绑定 owner、exact main、固定 workflow ref、attempt 1、one-shot exact-head
  authority、T0702–T0704 receipts、九份失败账本与当前 Run Contract。
- 复用现有 `moomooau-beta` 八个精确 Secret 名称；值不复制、不写盘、不公开。已安装 GitHub App
  在 Gmail exchange 前必须生成仅绑定唯一 Repository ID 的 token，核验 installation repository
  列表、目标仓 ID/private 属性，并刷新实时容量。
- 只完整读取确定性 `VERIFIED` 来源；Raw/Processed recovery 与二次验证后才允许最多一次
  exact-message Trash。Timeline snapshot、唯一 latest age Asset 与 checkpoint-last CAS 均须
  远端恢复。
- `workflow_dispatch` 如实称为 `SCHEDULE_REHEARSAL`，rehearsal platform schedule event 为 0。

## 当前安全边界与下一步

- T0705 总 delivery 最多 11，九个失败 launch 已消耗 9；只剩 canonical Git Blob recovery
  delivery 1
  与 receipt/schedule closure delivery 1。
- 总 rehearsal dispatch 最多 10，九个失败 attempt 已消耗 9；只剩一个新 recovery dispatch，
  必须为 attempt 1、rerun 0。
- 不使用真实时间 Soak、观察期或全量测试作为前置；时间与历史分支由 Fake Clock、Fixture、历史
  回放和故障注入即时验证。
- protected PASS receipt 绑定前，`MOOMOOAU_PRODUCTION_ENABLED` 不得为 true。
- 合入新 exact-main recovery candidate 后只设置一个 exact-head authority，运行一次；无论
  结果如何立即删除，绝不 rerun 或 redispatch 失败 head。
- PASS 后才固化 receipt、关闭 rehearsal 入口并启用已提交 04:30 Australia/Sydney schedule。
- 不进入 T0706，不创建 Codex Automation，不运行 Recovery Drill/Patch Lifecycle，不做最终发布。
