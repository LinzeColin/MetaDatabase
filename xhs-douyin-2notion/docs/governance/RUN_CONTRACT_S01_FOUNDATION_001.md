# Run Contract — RUN-X2N-S01-F001

## 目标

执行唯一 DAG Task `TSK.x2n.foundation.001`：建立受治理 Skill、Node/Python
workspace、无权限 Extension scaffold、无外部副作用 Companion scaffold 与公共合成
fixture，并对干净副本执行锁文件和 lifecycle rehearsal。

## 权威授权解释

`01_PRD.md` 顶部的 Stage 0-only 字段是 2026-07-19 产品设计基线；后续
`CE-X2N-20260720-S00-REVIEW-RESUME`、G0 机器状态及 Task Pack 已明确授权本独立
Run 启动 Stage 1。该 Change Event 只推进授权状态，不改变 PRD 的产品边界。

## 最小范围

- 只修改 `xhs-douyin-2notion/**`。
- 产出 `SKILL.md`、`agents/openai.yaml`、`apps/extension`、`apps/companion`、
  `packages/contracts`、`packages/test-fixtures`、package locks、测试和紧凑证据。
- `THIRD_PARTY_NOTICES.md` 继续记录实际依赖为 0；Node、npm、Python 与 uv 只作为
  外部构建工具，不进入 Runtime dependency graph。
- 不读取或修改共享认证材料、全局 Git 配置、其他项目或长期开发目录。

## 非范围

不定义 foundation.002 的版本化 Contract/错误分类，不创建 SQLite/迁移、Native
Messaging、Local API、Side Panel 行为、平台 Adapter、Notion/模型/媒体能力，也不
执行真实账号、浏览器或外部网络动作。

## 验收

1. `ACC.x2n.gov.001` 在本 changed scope 复验：0 越界写、0 重复 ID、0 未登记事实
   写入者。
2. npm 与 uv locks 与 workspace 声明一致，第三方 package 为 0，install scripts
   为 0。
3. 在隔离临时 HOME 的新副本运行 npm/uv lock check、Extension self-test，以及
   install/self-test/synthetic Canary/upgrade/rollback/diagnose/uninstall rehearsal。
4. 每个 lifecycle 命令可复制执行；失败使用稳定 code、安全消息和一个最小决策问题。
5. 真实产品 lifecycle 明确为 `DOWNSTREAM_NOT_RUN`；没有未声明授权或外部副作用。

## 风险、回滚与停止条件

- Build output、Runtime、私有路径、Secret/CDN、第三方未锁依赖或其他项目写入一旦
  出现，立即 Fail Closed。
- scaffold 与 Canonical layout 冲突、必须提前实施下游 Contract/产品行为，或依赖
  许可未知时停止。
- 回滚为 revert 本 Task 单一 scaffold commit；没有数据迁移或外部状态需要恢复。

## 验证命令

```bash
python3.12 -B scripts/verify_foundation_001.py --verify-worktree --allow-external-main-dirty
python3 -B -m unittest discover -s tests -p 'test_*.py'
```

中间 Task 完成后只允许本地 commit；Stage 1 整体必须等待 G1 Review/Fix/Re-
acceptance 后才可 push。
