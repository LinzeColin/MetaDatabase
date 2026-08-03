# Personal-WorkBench — S1 完成交接

## 当前目标

“胡楚靓工作台”已完成 S1 的私有候选源码、授权素材边界和五张冻结视觉真值验收。下一 run 进入 S2：在不改变 reference 模式页面的前提下，实现真实的多账户认证与账户边界。当前没有 Deploy、Sites Saved Version、GitHub push 或任何真实账户测试。

## 当前状态

- 阶段：`S1_COMPLETE_PRIVATE_CANDIDATE`
- 产品源码：官方 Sites starter skeleton 已移除；`app/page.tsx` 提供 `welcome`、`home`、`ledger`、`fatloss-food`、`period` 五条 `?reference=` 冻结路线，固定为 472×1024 app-stage，正常路线才显示账户入口。
- 私有素材：`public/private-reference-assets/` 有 37 项受控的参考裁切/衍生素材；`13_evidence/asset_manifest.json` 连同 5 张视觉真值形成 42 项来源、SHA-256、用途与权利记录。
- 公开权利：最终 Hello Kitty 原始授权素材和权利记录仍未进入 workspace。因此 `npm run verify:assets -- --public-deploy` 预期失败为 `BLOCKED_ASSET_RIGHTS`；这只阻止公开 Deploy，不阻止当前私有候选源码和视觉验收。
- Sites：仍是 S0 建立的独立、Owner-only、未 Deploy Site；D1=`DB`、R2=`FILES`。本轮未读取任何 Secret、Cookie、Token、密码或用户数据。

## 已核验证据

- S1-T1：`13_evidence/asset_manifest.json`。当前素材核验返回 `PASS_PRIVATE_CANDIDATE_PUBLIC_DEPLOY_BLOCKED`；若提供 `TASKPACK_ROOT`，5 张参考图和 5 张 mask 的 SHA-256 也已实际重算通过。
- S1-T2：`13_evidence/ui_structure.json`。built worker 的五条 reference 路线均有冻结结构、没有账户 chrome；正常 home 才有独立账户入口。
- S1-T3：`13_evidence/visual/manifest.json`。Chrome 本地预览的 3 轮、5 页、固定 472×1024 app-stage 截图、几何锚点、mask 差分、热图和 overlay 均已保留。差分指标明确为诊断值，未换算或宣称为相似度百分比。
- 质量命令全部通过：`npm run check`、`npm run test:ui-structure`、`npm run test:visual`、`git diff --check`。`npm audit` 基线仍为 18 项（1 low / 4 moderate / 13 high，0 critical），未自动执行 `npm audit fix`。

## 关键文件

- 页面与 token：`app/page.tsx`、`app/globals.css`、`app/layout.tsx`
- 仅 S1 视觉入口：`app/auth/sign-in/page.tsx`。它只是账户入口布局，不处理凭据；S2 才能接入真实认证。
- 素材与公开发布门：`scripts/verify-assets.mjs`、`13_evidence/asset_manifest.json`
- 结构与视觉验收：`tests/ui-structure.test.mjs`、`scripts/record-ui-structure.mjs`、`scripts/create-visual-evidence.mjs`、`scripts/finalize-visual-evidence.mjs`、`scripts/test-visual.mjs`

## 下一步（S2）

1. 保持五条 `?reference=` 路线无登录态、Cookie、调试或迁移信息；实现 Google、邮箱注册/验证、登录、忘记/重置密码和会话边界。
2. 认证完成后再实现账户切换、D1 schema/RLS 型隔离和业务写入；不信任客户端 `user_id`，不把业务正文写入日志或证据。
3. 公开 Deploy 前，Owner 必须在同容器与裁切框内原位提供最终获授权 Hello Kitty 原图及权利记录；不得用当前裁切素材、替代角色或“全部授权”文字绕过该实际资产缺口。

## 可复核命令

```bash
cd Personal-WorkBench
npm run check
npm run test:ui-structure
npm run test:visual
TASKPACK_ROOT='/Users/linzezhang/Downloads/TaskPack/Personal-WorkBench/胡楚靓工作台_ChatGPT-Sites多用户SaaS最终开发任务包_v0.0.0.8' npm run verify:assets -- --record
npm run verify:assets -- --public-deploy # 预期 BLOCKED_ASSET_RIGHTS / exit 1
git diff --check
```
