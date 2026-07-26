# MooMooAU v1.0.26 — T0705 pointer-blob recovery 修复候选

本包只处理 Stage 7 / T0705 与 S7AC-005，直接继承不可变 v1.0.25。七个 protected GA
失败 head 均固定为 attempt 1、rerun 0，永久禁止 rerun/redispatch；不进入 T0706，也不构成
最终发布。

第七次运行通过 authority 与 plaintext cleanup，但在固定
`FIRST_IMPORT_POINTER_FETCH` 子阶段失败。只读连接仓核验确认该运行窗口没有新 commit，
因此没有新增 Raw、Processed、Timeline、checkpoint 或 Gmail mutation。两份 current pointer
的 Git tree/blob 与 exact raw media 都是尺寸一致、SHA 绑定正确的 age ciphertext；其中一份
GitHub Contents JSON 内联表示解码后的长度却与声明尺寸不一致。protected exception 未被读取，
所以精确线上根因仍为 `UNKNOWN`，但该 live A/B 证据已证明不能信任内联表示。

唯一运行时修复是：Contents JSON 只提供 exact allowlisted path 的 `type/path/size/sha` 元数据；
随后以 exact raw media 取回 ciphertext，执行 2 MiB 上限、声明尺寸、age envelope 和 canonical
Git blob SHA 校验，再进入解密。任何 raw body 或 revision 漂移均失败关闭，CAS 与 endpoint guard
边界不扩大。

剩余授权严格为一个受控 main repair 交付和一个新 exact-main attempt-1
`SCHEDULE_REHEARSAL`，rerun 0。protected PASS 后才允许 receipt/schedule closure 交付并启用
已提交的 `04:30 Australia/Sydney` schedule。rehearsal 不伪称平台 schedule event。
