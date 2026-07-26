# MooMooAU v1.0.28 — T0705 canonical Git Blob 恢复候选

本包只处理 Stage 7 / T0705 与 S7AC-005，直接继承不可变 v1.0.27。九个 protected GA
失败 head 均固定为 attempt 1、rerun 0，永久禁止 rerun/redispatch；不进入 T0706，也不构成
最终发布。

第九次运行通过 authority、精确 GitHub App repository scope 与 plaintext cleanup，随后仍在
`FIRST_IMPORT_POINTER_FETCH` 失败。独立后验确认运行窗口 private commit 0、Gmail mutation 0。
protected exception 未被读取或检查，因此本包不声称其文本。

只读 live replay 对未改变的 private head 复现了生产 adapter：Contents metadata 均有效，
Contents raw media 均返回 HTTP 200，但其中一个 body 不是 age envelope，且不匹配声明 size 与
canonical Git SHA；同一 metadata SHA 对应的 Git Blobs API 对所有 current pointer 均通过
base64、response SHA、声明/解码 size、age envelope 与 canonical Git SHA 校验。

唯一代码修复是：Contents 只提供有界 path/size/blob SHA metadata；Processed current/immutable
恢复必须从精确 `GET /git/blobs/{40hex_sha}` 读取规范 base64 blob，并再次验证 SHA、size 与 age。
Contents inline 与 raw-media body 不再作为 Processed 密文真源。Fixture 覆盖换行 base64，故障注入
覆盖 response revision drift 并 fail closed。

剩余授权严格为一个受控 main 交付和一个新 exact-main attempt-1
`SCHEDULE_REHEARSAL`，rerun 0。protected PASS 后才允许 receipt/schedule closure 交付并启用
已提交的 `04:30 Australia/Sydney` schedule。验证不依赖 Soak、观察期、真实时间等待或全量测试。
