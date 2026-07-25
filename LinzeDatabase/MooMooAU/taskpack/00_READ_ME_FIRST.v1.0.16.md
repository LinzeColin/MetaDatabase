# MooMooAU v1.0.16 — T0704 受保护 Blue-Green 首次执行授权

本包只交付 Stage 7 / T0704 与 S7AC-004 的候选和一次受保护执行权限，成功回执产生前不进入 T0705。

## 已证明事实

- T0702/S7AC-002 与 T0703/S7AC-003 的精确 protected PASS 回执保持不可变。
- 本地 14 项 T0704 测试覆盖同一已恢复 Raw、1.0.0/2.0.0 SAFE_DEFERRED 对比、
  candidate-only Processed、processed-current 不变、Timeline 恢复与单 live asset。
- protected entrypoint 在读取 Secret 前绑定 exact main、attempt 1、rerun 0、T0703 receipt、
  固定控制仓身份、`moomooau-beta` Environment 与 T0704 Run Contract。
- protected runtime 只读取唯一 current-backed Trash source，不调用 Gmail mutation API，
  不创建 Raw，不提升 candidate pointer，不启用 schedule。
- 旧 capacity snapshot 只保留 limits/连续性基线；每次 protected job 在 Gmail 交换前只读
  实测私有仓 metadata、完整 default-branch tree 与 live Release，截断/未知 LFS/超限均零写入停止。
- 公开输出只包含固定枚举与聚合计数，不包含 Gmail 字段、private locator、Secret 或精确邮箱总数。

## 唯一授权预算

- 受控 main 交付 1；
- exact-main protected workflow dispatch 1、rerun 0；
- verified full Raw read 1、candidate Processed shadow commit/recovery 1；
- Timeline snapshot commit/recovery 1、latest Timeline publish 1、live asset min=max=1；
- Gmail mutation、Raw creation、processed-current mutation、schedule、GA 与 T0705 均为 0。

## 失败边界

失败时保留 Raw、incumbent current pointer 与任何有效 live Timeline；candidate shadow 可留作
append-only quarantine。失败 head 不 rerun，修复必须使用新的审查 SHA 与显式契约。
