# MooMooAU Archive Roadmap v1.0.6

本版本是 v1.0.5 的基线保真控制继任。v1.0.1 冻结的 Pursuing Goal、S0–S7、34 RQ、34 AC、
58-task DAG、Kill Criteria 与十条不变量全部继续有效。

## 不变的产品契约

| 契约 | 数量或身份 | SHA-256 |
|---|---:|---|
| Requirements | 34 | `ea1c5ec0371576b1852cc23d5836eaf21b044a577ee6c6c1a92dddc3923bea27` |
| Acceptance Contracts | 34 | `3115ea47f01549218c817845554dc32b019a894708c4ac311e99249bcabf95bb` |
| Traceability Matrix | 34 RQ ↔ 34 AC ↔ 58 tasks | `263250bceb42d623c4491b99665dff3d1ba08e78f4e43a4fde74380a5e28abf2` |
| Task DAG | 58 tasks | `72785605390a31c8dbb0a5d349cf81418b158f7714e46fe8e7f8e4b113f318d9` |
| Kill Criteria | 原样继承 | `2a0494577382d1529721b05c6b03f874787f8c8deb5dbd4a56895624573f25dc` |
| Canonical Facts | 十条不变量 | `27110e8e6d8d337474eefa29f51d5bf294061c90dfebac2e0d898268dce96bf2` |
| v1.0.5 Manifest | 不可变直接前序 | `f99413b9c1fb67369ba3039a7acfeb437004d1aad8cb54dc3697f87f38e35cb3` |

## RMD-06 当前 Run Contract

目标仅为建立可运行的 GitHub-hosted 验证前置：

- 修复 GitHub expression context；
- 为私有 Governance 使用单仓只读 Deploy Key；
- 凭据仅供 pinned `actions/checkout` 使用；
- fork PR 在凭据 checkout 前 fail closed；
- 普通 CI 的生产/Gmail/数据仓 Secret 读取保持零；
- 不执行生产、Gmail mutation、私有数据仓写入、部署或最终发布。

本版本不把依赖凭据读取解释为生产 Secret 读取，也不把 GitHub-hosted CI 解释为 protected Oracle。
任何 Workflow syntax、Governance pin、Secret 边界、fork policy、package、publication 或 cumulative gate
失败都停止 RMD-06。

## 后续顺序

1. 配置并验证只读 Governance Deploy Key，立即删除本地临时私钥材料；
2. 对 v1.0.6 候选运行本地累计门和 Secret/publication 扫描；
3. 仅上传受控候选分支，观察 GitHub-hosted 非生产预检；
4. 预检全绿后，RMD-06 才可按 Beta → M3 → Timeline Blue-Green → GA → Recovery → 最终 AC
   的既定顺序继续；每个未知或失败结果立即停止；
5. RMD-06 完成后进入 RMD-07 最终复审与干净一次性发布。
