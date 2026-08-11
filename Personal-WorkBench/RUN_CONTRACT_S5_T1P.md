# Run Contract — S5-T1P Sites Source Projection Compatibility

## 定位

这是 S5-T1 的传输兼容子阶段，不是产品验收或部署阶段。它只在精确 MetaDatabase commit 无法被 Sites 专用源码库接收时启用；结果只能是 PROJECTION_READY 或 BLOCKED。

## 目标

用 SOURCE_PROJECTION_CONTRACT.json 证明项目根 projection 的 Git tree 与冻结 Personal-WorkBench 子树逐对象一致，并生成可复算的无父 projection commit。

## 最小范围

- 只读 MetaDatabase 冻结 commit/tree 与 taskpack；
- 临时目录中的 Git archive、Git 初始化和确定性 commit 计算；
- 合同、验证脚本、测试和交接文档。

## 明确不在范围

- 不保存 Sites Version、不配置 Secret、不改私有访问策略、不 Deploy；
- 不改产品代码、视觉真值、任务包、Oracle 或阈值；
- 不把 projection 当作 S4/S6 产品 PASS。

## 通过条件

1. npm run verify:source-projection 输出 PASS_SOURCE_PROJECTION_CONTRACT。
2. source commit/root tree/project tree、projection tree 和确定性 projection commit 均与合同一致。
3. projection commit 无 parent，且根 tree 等于冻结项目子树 tree。
4. 工作树中只有本子阶段的合同、验证/测试和交接变更。

## 下一步

PROJECTION_READY 只允许后续独立 S5-T1 run 将合同中同树的源码通道后继提交以非强制方式推送到 Sites 专用源码库，并保存私有、可丢弃的 Version。实际 saved_version.json 必须记录源、内容投影和源码通道三段身份；无法映射或任一 hash 不一致时停止保存。
