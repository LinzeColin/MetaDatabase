# MooMooAU v1.0.17 — T0704 Release Asset 302 恢复修复

本包仍只处理 Stage 7 / T0704 与 S7AC-004。它固化首次 protected 失败，不重跑失败 head，
仅授权一个新的 exact-main 修复候选与一次 attempt-1 执行；成功回执产生前不进入 T0705。

## 已证明事实

- PR #112 合入后的 exact-main attempt 1 通过 authority gate 与 identity cleanup，rerun 为 0。
- 受保护运行已恢复同一 Raw、candidate Processed shadow 与确定性 Timeline snapshot；
  `processed-current` 的路径与 blob 集在运行前后完全一致。
- 运行留下 2 个 candidate shadow 对象、2 个 Timeline snapshot 对象与 1 个加密 repair state；
  固定 private Release 存在，但最终 live asset 为 0。
- GitHub 官方 Release Asset API 明确允许下载返回 `200` 或 `302`。失败实现关闭自动跳转且只接受
  `200`；当前只读探针也实际观察到 `302`。
- 新实现只在 Release Asset read 后允许一次
  `release-assets.githubusercontent.com/github-production-release-asset/...` 跳转，
  第二跳不携带 Authorization，不记录或公开签名 URL。
- 本地完整修复回放证明：失败态首次产生 5 个 encrypted repository commits；修复态不重复创建
  candidate 或 snapshot，只新增 1 个 encrypted HEALTHY state commit，并收敛到 exactly one asset。

## 唯一授权预算

- 新受控 main 交付 1；
- 新 exact-main protected dispatch 1、attempt 1、rerun 0；
- verified full Raw read 1，Raw creation 0；
- candidate Processed 与 Timeline snapshot 新 commit 均为 0，只恢复既有对象；
- Timeline publish 1、Asset upload 1、encrypted state CAS 1、live asset min=max=1；
- Gmail mutation、processed-current mutation、schedule、GA 与 T0705 均为 0。

## 停止边界

失败 head `b3ff184b…` 永不 rerun/redispatch。新修复如果不能远端恢复唯一 live Timeline，
继续保留 zero-asset encrypted repair state、Raw、incumbent current、candidate 和 snapshot，
不触碰 Gmail；不得以本地测试替代 protected PASS。
