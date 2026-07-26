# ADP v1.2 S4.2 六主题移动端统一四标签导航收尾记录

更新时间：2026-07-24 14:38:18 Australia/Sydney

## 任务与边界

- Task：`ADP-V12-S4-T002`
- Run Contract：`docs/pursuing_goal/v1_2/RUN_CONTRACT_05_MOBILE_FOUR_TAB_NAV.md`
- Decision scope：`developer_check`
- S4.2 只在已验收 S4.1 materialization 上叠加移动四标签候选补丁，并验证移动/桌面导航；
  不修改 canonical `worker_cloud.js`，不处理 S4.3 视觉、视频、动效或像素门，不做发布或部署。
- live `0.41.0` / build `c2ccc1fd01ec`、来源与板块、三个 cron、D1/R2、数据结构和数据均未改。

## S4.2 验收结果

| Acceptance | 状态 |
|---|---|
| `ACC-V12-S4-003` | `PASS` |

全新上下文独立 verifier 终局为 `PASS / ACTION NONE`，findings、`P0`、`P1`、`UNKNOWN`、
`BLOCKED` 与 waiver 均为零。已验 Subject 为 clean Git commit
`e5460ef2c62d44af090e8f93b7bac9d607a91090`、tree
`6b3cfce275af94a56d1be3a9e7124cac2ec55343`；确定性物化候选 artifact SHA-256 为
`39f8a8d82aec8f97e83d595f95ba52ae062191b801632661922077c9632b356b`，测试前后身份稳定。

独立 review ZIP 只在 Owner 本机保存，文件名为
`ADP_V12_S4_T002_acceptance_e5460ef2_fresh_r2_acceptance_review_taskpack.zip`，公开登记
SHA-256 `cf884d8a4ab6b2efbd2f6e85a761f97dcf467ab27ffac36827aff6866a95e4cb`、大小
`2255827` bytes、`63` entries；官方 finalizer 原位与解包 `--verify`、`unzip -t` 和
`58` 项内部 checksum 均通过，evidence root 为
`ac80b4f62bb235eaa4d21301c042672eef5e7f9fdf49a0c4658818c603ddbb45`。完整安全摘要见
[`ADP-V12-S4-T002-developer-check.json`](../../machine/runs/ADP-V12-S4-T002-developer-check.json)。

## 内容合同与真实旅程

- 六主题在 `<780px` 统一使用且只使用“今天／队列／雷达／系统”四标签，顺序与 href 精确为
  `/`、`/review`、`/radar`、`/system`，活动态随四条实际 Worker route 正确变化。
- `375×812` 的六主题移动页面均只有一个可见移动主导航、四个等宽栏、`48px` 点击高度，
  无横向 overflow，固定底栏不遮挡 footer。
- `779px` 仍走 mobile，`780px` 恢复 desktop；warm/forest 保持 sidebar，
  minimal/fresh 保持 topbar，techno/cosmos 保持 dock，桌面六项导航未压缩或错配。
- 独立系统 Chrome `150.0.7871.182` 实跑六个移动主题、六个桌面主题、十二个临界宽度案例、
  四条 active route，共十二张截图，console/page error 为零。

## 可承重负控与历史缺陷

十个分离破坏负控全部被同一 Oracle 阻断：删除 mobile nav、加入第五标签、错序/改名、
href 错配、mobile 暴露 desktop nav、breakpoint 回退到 `640px`、点击高度低于 `44px`、
注入横向 overflow、桌面导航压成四项、主题 desktop nav mode 被破坏。

因此 7fd 历史 `F-006` 在本冻结 Subject 上关闭。S4.3 的主题肉眼区分、视频真实播放、
reduced-motion、pixel/visible gate 与其负控仍未运行，不得把本结论外推。

## verifier 自身尝试记录

独立复核如实保留四类 verifier-owned 尝试：

1. 首次 materialization 漏设临时 cwd，patch01 短暂落到冻结 worktree；验收测试前已精确
   反向恢复，并以 canonical hash、零 diff 与 clean status 证明恢复；
2. bare Python 缺 PyYAML、uv 环境无 pip module；离线 Python 3.12.13 环境重跑通过；
3. verifier 工具自测首次因自身 import 生成 pycache 得 `34/35`，禁写 bytecode 后 `35/35`；
4. 首个 sealed ZIP 因不保留三个空必需目录而无法解包复验；未覆写旧 seal，而是新建
   fresh-r2，以三份 `NOT_APPLICABLE.md` 保持目录可移植，再次封存后原位与解包验证均通过。

这些尝试不是产品 finding，也没有使用 waiver；旧首包、旧 run 与临时目录未作为交付保留。

## 回归证据

| 检查 | 结果 |
|---|---|
| 六主题移动端 / 桌面端 | `6/6 PASS` / `6/6 PASS` |
| `779/780px` 边界 / active route | `12/12 PASS` / `4/4 PASS` |
| 分离破坏负控 | `10/10 PASS` |
| 截图 / 浏览器错误 | `12` / `0` |
| S4.2 聚焦治理测试 | `6/6 PASS` |
| S4.1 聚焦回归 | `24/24 PASS` |
| MetaDatabase ADP 治理回归 | `78/78 PASS` |
| 安全边界回归 | `14/14 PASS` |
| 双平面、taskpack integrity/compatibility/drift | `PASS` |
| V7.2 根任务包兼容门 | `PASS` |
| ADP full suite 原始结果 | `962` 项；`2 failures + 11 errors + 29 skips`，原始状态 `FAIL` |
| sealed failure/error key 集合差分 | `PASS`；`candidate_only=[]`、`baseline_only=[]` |

完整测试没有包装成全绿。独立 verifier 先验证 S3 sealed ZIP SHA-256 与 `42` 项内部 hash，
再从其中实际 differential member 读取全部 `13` 个 failure/error key；S4.2 与之精确同集。
owner-sync 广谱命名套件另有冻结基线中的七个 missing-file errors，也未声称通过。

## 收尾自引用边界与下一步

独立 Subject 在 verdict 前已冻结。本 receipt、phase record、S4.3 机器事实及其确定性生成的
七份人类文档、HANDOFF/taskpack README/CHANGELOG 的收尾文字、任务包树摘要、根 CHANGELOG，
以及提交前由项目脚本执行的二十个用户中心时间戳更新被明确排除，避免把“验收已通过”本身
放进待验 Subject 形成自引用。任何产品、测试、候选补丁、taskpack 合同、registry、Owner
内容或 live 边界字节变化都不在排除范围内，必须重新验收。

S4.2 不授权 live 接线、发布或部署。下一任务是 `ADP-V12-S4-T003`（可承重视觉、动效与像素
回归门），对应 `ACC-V12-S4-004..006`；当前为 `NOT_RUN`，Run Contract 尚未创建。下一轮
只能先锁定唯一合同，不得从本记录预签 S4.3、整 S4、版本、运维或部署。
