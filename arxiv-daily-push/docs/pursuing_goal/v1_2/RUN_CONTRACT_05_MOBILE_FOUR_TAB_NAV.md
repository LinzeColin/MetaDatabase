# Run Contract 05 — `ADP-V12-S4-T002`

## Goal

在不改 live、不覆盖六主题桌面导航设计的前提下，关闭 7fd 验收 `F-006`：所有六主题在
CSS viewport `<780px` 时必须统一呈现且只呈现“今天／队列／雷达／系统”四标签固定底栏，
在 `375×812` 下无横向溢出；`>=780px` 时继续按前端 v1.1 基线保留
sidebar/topbar/dock 三种桌面导航和原有六个入口。

## Immutable Subject and Preconditions

- Subject 是 MetaDatabase 当前分支中的 `arxiv-daily-push/`；禁止读取或恢复 CodexProject
  已删除的 ADP 旧源。
- `ADP-V12-S0-T001` 至 `ADP-V12-S4-T001` 必须保持已验收。S4.1 冻结候选为 commit
  `c50d7f7b6a1f01831c56d1a11b76f6ccd5248860`、tree
  `d40fb7b23ceae89c3df11449b1673d48422e1e9a`。
- canonical `deploy/cloudflare/worker_cloud.js` 是 live `0.41.0` / build `c2ccc1fd01ec`
  的封存 production Subject，文件 SHA-256
  `319178f05490588701c10c40fd8dad653d4b58e35c7acbfe1224f7282a20a196`；本轮不得修改、
  部署或重冻 production bundle。
- S4.2 candidate 必须严格按顺序物化：
  1. 对 canonical Worker 应用已验收
     `v1_2/patches/01_human_language_fail_closed.patch`，其 SHA-256 必须为
     `3f323220cad779d353e0b653d6edfdbd94292433aa8306f9045f9badcda8e9cf`；
  2. 得到 S4.1 blob `9ff676970c20369ca562aa8a9639016fa08bb1c7` / build
     `cc52e9dc2102` 后，再用 `git apply --unidiff-zero --unsafe-paths`
     无 fuzz 应用本轮 `02_mobile_four_tab_nav.patch`；U0 补丁只在前述 base blob 精确匹配后执行；
  3. 对最终物化 Worker 复算 self-excluding BUILD stamp。
- 权威产品来源是前端 v1.1
  `docs/design/前端呈现基线_v1/前端重构增补包/02_首屏与导航结构.md`，
  缺陷来源是 7fd `F-006`，阻断 Oracle 仅为 `ACC-V12-S4-003`。
- 本合同只处理 `ADP-V12-S4-T002`。不得顺带修 S4.3 视觉门、视频、动效、像素基线、
  reduced-motion、版本、SLO、运维或发布。

## Minimum Scope

- 新增独立移动主导航 DOM；其链接按固定顺序精确映射：
  `今天 → /`、`队列 → /review`、`雷达 → /radar`、`系统 → /system`。
- `<780px` 时隐藏 sidebar/topbar/dock 三种桌面主导航，只显示一个移动主导航；四个链接
  等宽、单行、点击高度至少 `44px`，固定在 viewport 底部并处理 safe-area。
- 移动底栏结构、顺序、标签和命中区域在六主题间完全一致；主题只能通过既有 CSS 变量影响
  配色，不得让某个主题恢复六项导航、改变位置、改变标签或丢失链接。
- `375×812` 的六主题逐一记录 DOM、computed style、viewport/scroll width、点击目标矩形和
  screenshot；`779px` 必须仍是四标签，`780px` 必须恢复对应桌面导航。
- `>=780px` 时移动导航不可见；暖纸/森林继续 sidebar，简约/清新继续 topbar，
  炫技/宇宙继续 dock，且桌面六个入口
  “今天／复习／前沿雷达／关注／知识库／系统”及 href 不变。
- 保持所有既有 route、主题、首屏、搜索、主题选择器、视频、动效、数据与交互实现存在；
  本轮只改变导航在 viewport 宽度上的呈现和移动标签文案。
- 新增可复跑的完整 Worker 行为验证器和治理测试；阶段完成前仅本地提交，不上传 GitHub。

## Non-goals

- 不修改 canonical Worker、production bundle、live、Cloudflare 配置、cron、D1/R2、
  schema/data、来源/板块、排序、FSRS 或产品版本。
- 不删除 `/watchlist`、`/library`、`/history`、`/search` 等 route，也不把桌面六项压成四项。
- 不重写六主题、首屏、字体、形状、视频或动效，不新增 UI 框架、GSAP、图标库、外部字体、
  图片、CDN 或网络依赖。
- 不重冻视觉 baseline，不新建视觉 approval；可承重视觉/负控门属于 S4.3。
- 不用静态字符串、构建者自报或一张截图代替真实浏览器 DOM/布局证据。

## Mobile Navigation Contract

- **Breakpoint**：CSS viewport `width < 780px`。实现使用可审计的 `max-width:779px`；
  `779px` 为 mobile，`780px` 为 desktop，不得沿用旧 `640px` 临界点。
- **唯一可见主导航**：mobile 下 `nav[aria-label="移动端主导航"]` 恰好一个且可见；
  `nav-top`、`nav-side`、`nav-dock` 的 computed display 均为 `none`。
- **精确四标签**：移动主导航恰好四个 `<a>`，可见文本、顺序和 href 精确等于
  `今天/`、`队列/review`、`雷达/radar`、`系统/system`；不得残留“复习、前沿雷达、关注、
  知识库”等桌面标签。
- **活动态**：沿用现有 route 前缀规则并保持单一 `aria-current="page"`；`/` 只激活今天，
  `/review`、`/radar`、`/system` 分别激活对应标签。
- **布局**：四列等宽，链接单行不换行，最小高度 `44px`，底栏固定、全宽、safe-area 安全；
  不遮住 footer 最后一行，不产生 document/body 横向 overflow。
- **桌面保持**：`>=780px` 仅显示当前主题的既有 desktop nav，移动 nav computed display
  为 `none`；桌面标签、href、active 语义和主题到 nav mode 的映射不变。

## Deterministic Browser Tests and Negative Controls

- `TST-V12-MOBILE-NAV-SIX-THEMES`：物化完整 S4.2 candidate，通过实际 Worker
  `default.fetch` 取得页面，在 system Chrome/Chromium 中以 `375×812` 逐一切换六主题，
  检查唯一移动主导航、精确四标签/href、活动态、四等列、点击高度、fixed/safe-area、
  desktop nav 隐藏和 `scrollWidth === clientWidth`，并保存六张截图。
- `TST-V12-DESKTOP-NAV-REGRESSION`：同一 candidate 在 `1440×900` 逐主题检查
  sidebar/topbar/dock 映射、六个 desktop 链接/href/活动态、mobile nav 隐藏和无 overflow；
  另测 `779/780px` 边界。
- 浏览器不可用、截图缺失、console/page error、任一主题未运行或 viewport metrics 缺失均为
  `UNKNOWN/BLOCKED`，不得以源码扫描降级为 PASS。
- 同一 Oracle 必须逐项阻断至少这些独立破坏：删除 mobile nav、加入第五标签、错序/改名、
  href 错配、mobile 下暴露 desktop nav、把 breakpoint 改回 640、点击高度低于 44px、
  注入横向 overflow、把任一桌面导航压成四项、破坏任一主题的 nav mode。
- 验证器必须执行最终物化 Worker，而非复制一份导航实现；治理测试必须固定 patch 顺序、
  精确标签/href、负控名称与数量，并确认 canonical Worker 未变。

## Validation

```bash
node arxiv-daily-push/tools/verify_mobile_four_tab_nav.mjs
PYTHONPATH=arxiv-daily-push/src python3.12 -B -m unittest tests/governance/test_adp_mobile_four_tab_nav.py -q
node arxiv-daily-push/tools/verify_human_language_fail_closed.mjs
PYTHONPATH=arxiv-daily-push/src python3.12 -B -m unittest tests/governance/test_adp_human_language_fail_closed.py -q
python3.12 arxiv-daily-push/docs/pursuing_goal/v1_2/tools/validate_package.py --repo-root .
python3.12 arxiv-daily-push/machine/tools/check_dual_plane_ci.py --root . --projects arxiv-daily-push --require-projects
PYTHONPATH=arxiv-daily-push/src python3.12 -B -m unittest discover -s tests/governance -p 'test_adp_*.py' -q
PYTHONPATH=arxiv-daily-push/src python3.12 -B -m unittest discover -s arxiv-daily-push/tests -q
git diff --exit-code origin/main -- arxiv-daily-push/deploy/cloudflare/worker_cloud.js
```

full suite 继续按失败/错误完整测试键集合与 S3 sealed baseline 比较；candidate-only 和
baseline-only 必须均为空。S4.2 通过后仍不部署、不上传，等待 S4.3 和完整 S4 阶段复审。

## Risks, Rollback and Stop

- 风险：CSS 优先级使某主题仍显示桌面 nav；四标签只在 375px 偶然通过而 640–779px 失效；
  active 规则错误；safe-area 或 footer 被遮挡；桌面入口/主题 nav mode 回归；测试只检查 DOM
  存在而没有检查可见性和几何；patch 链顺序或 BUILD identity 漂移。
- 回滚：删除 `02_mobile_four_tab_nav.patch`、本轮验证器/测试和合同状态；S4.1 patch、
  canonical Worker、schema/data、production bundle 与 live `0.41.0` 保持不变。
- 立即停止：`desktop_navigation_regression`、`theme_specific_function_loss`、浏览器或截图
  证据不可获得、负控不阻断、canonical Worker 或 live 发生变化、需要付费/联网/部署才能继续、
  出现新增 P0/P1/UNKNOWN/BLOCKED，或同一路径连续失败两次。
