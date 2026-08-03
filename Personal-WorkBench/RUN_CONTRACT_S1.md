# S1 Run Contract — 视觉真值与获授权素材边界

## 目标

把官方 Sites starter 的可丢弃 loading skeleton 替换为“胡楚靓工作台”五张冻结视觉真值的私有候选源码，并把当前可用参考裁切素材与公开发布所需最终授权原图明确分层。

## 最小范围

- `app/`：五条 reference 页面、正常模式账户入口、元数据和粉白设计 token。
- `public/private-reference-assets/`：仅由任务包列明的受控私有候选素材。
- `scripts/`、`tests/`、`13_evidence/`：素材、结构、视觉验收。

## 不在范围

- Sites Save/Deploy、GitHub push、真实 Google/邮件/Turnstile、用户账户、业务数据、D1/R2 写入。
- 最终 Hello Kitty 授权原图的取得或杜撰。

## 验证与停止条件

- `npm run check`、`npm run test:ui-structure`、`npm run test:visual` 和 `git diff --check` 必须通过。
- 视觉验收固定为 472×1024 app-stage、五条 reference 路线、三轮真实截图；输出 mask 差分/热图，且不将诊断差分伪称为相似度百分比。
- `npm run verify:assets -- --public-deploy` 必须在最终授权原图缺失时失败为 `BLOCKED_ASSET_RIGHTS`。该失败是发布停止条件，不是 S1 私有候选的失败。

## 结果

- 状态：`COMPLETE_PRIVATE_CANDIDATE`
- 发布状态：`BLOCKED_ASSET_RIGHTS`
