# MooMooAU v1.0.25 — T0705 first-import 子阶段诊断候选

本包只处理 Stage 7 / T0705 与 S7AC-005，直接继承不可变 v1.0.24。六个 protected GA
失败 head 均固定为 attempt 1、rerun 0，永久禁止 rerun/redispatch；不进入 T0706，也不构成
最终发布。

第六次运行通过 authority 与 plaintext cleanup，但只公开 coarse `FIRST_IMPORT_RECOVERY` 后
失败。只读 private 数据仓核验确认该运行没有新 commit、路径变化、Processed write、
Timeline、checkpoint 或 Gmail mutation。按已提交阶段顺序，边界位于 Raw 远端恢复与
classification 之后、document-envelope 构造和任何 Processed write 之前；精确线上根因保持
`UNKNOWN`。第四次 writer 与第六次 reader 的 schema 未改变，synthetic writer-to-reader
恢复测试通过，因此不对 real-data 差异作无证据推断。

唯一实现变化是在既有 `ProtectedGADiagnostics` 中增加固定 first-import recovery 子阶段枚举，
并将同一个诊断器注入 `RemoteFirstImportTimestampSource`。诊断器不接收或检查异常、URL、
标识符、计数、Secret、邮箱事实或 private 仓定位，不改变控制流。metadata quarantine、
确定性验证、Raw/Processed recovery、二次验证、exact-message Trash、单一 latest Timeline
与 checkpoint-last 顺序保持不变。

剩余授权严格为：一个受控 main diagnostic 交付、一个新 exact-main attempt-1
`SCHEDULE_REHEARSAL`、rerun 0；若 diagnostic 失败，仅允许一个精确 repair-or-PASS closure
候选和一次 attempt-1 rehearsal。protected PASS 后才允许 receipt/schedule closure 交付并启用
已提交的 `04:30 Australia/Sydney` schedule。rehearsal 不伪称平台 schedule event。
