# S5-T1 Sites Source Projection Contract

## 目的

PWB-S5-SOURCE-PROJECTION-001 只解决一个已观测到的传输兼容问题：Sites 专用源码库无法接收包含完整 MetaDatabase 历史的精确提交。它把冻结 commit 中的 Personal-WorkBench Git 子树原样投影为一个独立、无父提交的项目根源码仓。

## 不变项

- 原始 MetaDatabase commit、root tree、项目子树 tree 与受控文件数量必须精确匹配合同 JSON。
- projection 的根 tree 必须与原项目子树 tree 完全相同；因此产品代码、视觉真值、Hello Kitty 素材、架构和锁定依赖都不被重写。
- projection commit 不是对原 MetaDatabase commit 的替代性验收结论。未来真实 Saved Version 证据必须同时记录两段身份和 archive SHA-256。

## 使用边界

先执行 npm run verify:source-projection。只有 PASS_SOURCE_PROJECTION_CONTRACT 时，后续单独的 S5-T1 run 才可将合同中的 projection commit 推送到 Sites 专用源码库并保存私有 Version。

此合同不创建 Version、不改访问策略、不配置 Secret、不部署，也不让任何 NOT_RUN 需求变成 PASS。
