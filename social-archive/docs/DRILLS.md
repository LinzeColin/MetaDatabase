# 演练清单：什么时候跑，谁来跑

<!-- 这份表由 scripts/check_every_drill_has_a_caller.py 逐条核对：
     scripts/ 下每个 *_drill.py 都必须在这里有一行；标着 **每次发布** 的
     必须真的出现在 scripts/deploy_to_production.sh 里。 -->

## 为什么要有这一页

2026-08-06 查了一遍：仓里 **15 个演练，调用方是 0**。不在发布门里、不在部署
脚本里、不在任何清单里 —— 唯一的触发方式是**有人记得去跑**。

代价当场就看到了：十一个真 Chrome 演练**全都加载源码目录**，而且加载前把
`optional_host_permissions` 提升成 `host_permissions`（为了不弹权限框）。
于是**他真正下载的那个包、在权限还没授予的状态下会怎样**——从来没被走过。
第一次真的去跑那个状态，当场发现读取失败时报的是「读不出当前页面的域名」——
真因是授权没给，而那句话把他指向**是不是页面没打开**。

**演练不写进流程，就只是一个我记得的习惯。**

## 它们不该抢你的屏幕

2026-08-07 Owner 的原话：**「为什么你永远都要不停开了又关关了又开我的浏览器」**。

13 个演练每个都起一个**可见的** Chrome，一次部署跑 15 个 = 十五次弹窗又关掉，
调试时还会连跑好几遍。它们一个都不需要人看着——弹出来纯粹是从来没人加过
`--headless=new`。现在全部默认无头，判据钉着
（`tests/focused/test_drills_do_not_take_over_the_screen.py`）。

要看着调试：`SA_DRILL_HEADED=1 python scripts/<某个>_drill.py`。
**开关只往看得见那一侧开** —— 没有反向的开关（不存在一个能让它默认弹窗的变量）。

（顺带更快了：save_page 12.8s→6.0s，routing 9.6s→3.9s。）

## 为什么不全塞进发布门

发布门在每次提交前跑（约 5 秒）。这些演练每个都要起一个真 Chrome 或连远端，
一分钟起步。全塞进去等于逼人绕过它。所以分三档：

| 档 | 什么时候跑 | 谁触发 |
|---|---|---|
| 每次发布 | 发布前，包已经打好之后 | `scripts/deploy_to_production.sh` → `run_all_drills.py`（14 个，约 4 分 42 秒） |
| ~~改到那条路时~~ | **这一档取消了** | 见下 |
| 定期 | 恢复类，季度或换机器后 | 人 |

## 这些演练的绿，覆盖不到哪一维

**除 `shipped_package_drill.py` 外，每一个真 Chrome 演练在加载前都做这件事：**

```
manifest["host_permissions"] = host_permissions | optional_host_permissions
manifest["optional_host_permissions"] = []
```

为的是不弹权限框、跑得顺。代价是它们的绿**不覆盖权限那一维**——
2026-08-06 量出来的：三个权限申请点全在 service worker 里，而
`chrome.permissions.request` 在那里**一个都要不到**
（`This function must be called during a user gesture`）。
也就是说账号页上每一颗连接按钮都拿不到权限，而十一个演练全绿。

权限那一维现在由 `shipped_package_drill.py` 覆盖：它原样解包、不改 manifest，
并且把同一个 API 在两个地方各调一次做对比
（service worker 里抛异常、扩展页面里弹出授权框）。

**读这些演练的结论时要记得这条边界。** 绿不等于"他那边也这样"。

## 怎么跑

**每个都零参数直接跑**：

```bash
python scripts/<演练名>.py
```

扩展类演练不给 `--ext-dir` 时会**现打一次发布包再解出来用**——
也就是说它们默认验的是他真正下载的那一份。Chrome 也由演练自己起
（临时 profile，跑完收掉），不需要你先开一个带调试端口的浏览器。

这一条是被两次实事逼出来的：`extension_routing_drill` 不自己起 Chrome，
只抛一句 `Connection refused`，看起来像它坏了；其余七个要先打包再解压
才跑得动。**要先做准备才跑得动的演练，就是没人跑的演练。**

`extension_platform_wiring_drill` 还要 `--platform` 和 `--sample-url`
（它一次验一个平台），恢复类那三个要备份清单——那几个的参数是它们的题目本身。

## 清单

| 演练 | 什么时候跑 | 它回答的问题 |
|---|---|---|
| `shipped_package_drill.py` | 每次发布 | 他下载的那个 zip，和我一直在测的是同一个东西吗；权限没给时它说得对吗 |
| `popup_states_drill.py` | 每次发布 | **弹窗那一屏在三种状态下各说什么**（从没连过 / 连过后来断了 / 连着）——他点插件图标看到的第一屏 |
| `production_reachability_drill.py` | 每次发布 | **装上发布包的真 Chrome，够不够得着刚部署的那台生产**（唯一一个不做域名映射的演练；跑在部署之后） |
| `extension_update_in_place_drill.py` | 每次发布 | 在原文件夹里覆盖再重载：ID 变不变、版本更不更新、已配对的凭据还在不在 |
| `stale_extension_is_blocked_drill.py` | 每次发布 | **他更新之前**点「连接账号」拦不拦得住（旧插件用 git 里 v0.0.0.22 那份真实构建；正反两个方向都跑） |
| `slow_extension_is_still_detected_drill.py` | 每次发布 | 插件**答得慢**时这一页还认不认得出它（假插件，延迟由脚本定：快答/慢答必须认出，完全不答必须认不出） |
| `list_shape_end_to_end_drill.py` | 改到那条路时 | 不知道接口地址，能不能从页面自己发的响应里认出收藏列表（`--platform` 逐个平台跑） |
| `bilibili_end_to_end_drill.py` | 改到那条路时 | 从连接账号到档案馆里真的出现条目，真 Chrome 里整条通不通 |
| `bilibili_acquisition_drill.py` | **每次发布**（run_all_drills） | B 站收藏夹取数路真的读得到吗（打真接口） |
| `extension_capture_drill.py` | 改到那条路时 | 「拦截 → 读懂」整条链 |
| `extension_capture_buffer_drill.py` | 改到那条路时 | 诊断按钮之后，两件最容易骗人的事 |
| `extension_save_page_drill.py` | 改到那条路时 | 「保存当前页面」那一下真的送到档案馆了吗 |
| `extension_routing_drill.py` | 改到那条路时 | 扩展的同步分流对不对 |
| `extension_platform_wiring_drill.py` | 改到那条路时 | 加一个平台时，四张表都接上了吗 |
| `extension_bridge_boundary_drill.py` | 改到那条路时 | 档案馆页面能给令牌，但不能改它往哪儿发 |
| `extension_install_page_drill.py` | 改到那条路时 | 装着旧插件的人能不能靠那一页更新掉 |
| `pwa_render_drill.py` | 改到那条路时 | 页面上那两段话真的显示出来了吗；**「连接新账号」那个弹窗里，做不到的平台不许有按钮**（快手/X 只显示原因） |
| `douyin_recogniser_does_not_grab_the_wrong_list_drill.py` | 改到形状识别那条路时（打一次抖音公开页，零费用） | 真抖音页面上，形状识别器会不会把别的东西认成收藏列表。**它当场逮到一个**：登录二维码那个 Lottie 动画文件的 `assets` 数组被认成 7 条收藏，过一遍归一化就是 7 条 `douyin.com/video/image_0` 这样的 404 落库。内建正对照（混一条真像列表的进去，识别器必须认出来），不然它是空转。`--platform` 可选 douyin/xiaohongshu/reddit/instagram——**同一个识别器四家都用**；**实测三家里只有抖音真见到了推荐流**（56 条真响应条条带内容，识别器不乱抓）；**小红书那一跑没见到内容流**——无头 Chrome 被风控挡在 `/website-login/error`，收到的 14 条全是安全与埋点接口，所以那一跑只证明识别器还活着（正对照认出了塞进去的列表），**不能据此说它面对真列表不乱抓**（2026-08-13 收窄）；**reddit 量不到且已定性**——它给无头 Chrome 的是一屏人机验证（Prove your humanity），唯一的通路是过验证码，而那件事不做。那一行永远是**没量到**，不是通过，也不必再试 |
| `list_selectors_meet_a_real_page_drill.py` | 每次发布（B 站 + 小红书，公开页零费用） | `LIST_SELECTORS` 那几条落在**真页面**上选不选得中。实测 B 站热门榜 **21 个节点**、小红书 **96 个节点**。两家取页面的路不同且是量出来的：B 站列表 JS 渲染只能真浏览器开；小红书**拒无头**（`error_code=300012`）而服务端已渲染好，取 HTML 再解析。**无头被识别 ≠ 通道不可达——我先按后者写过一版，是错的。**抖音仍答不了（没有公开的列表页），回 `BLOCKED_CHANNEL` 不是 `FAIL` |
| `net_observer_sees_a_real_page_drill.py` | 改到拦截那条路时（打一次 B 站公开页，零费用） | 拦截器在**真页面**上包不包得住：注进 document_start → 页面自己发请求 → 扣在 pending 里 → 配置下来后补判抛出。实测扣住 16 条、抛出 15 条、收藏夹那一族抓到 4 条。**顺带查出 `INTERCEPT_PREFIXES` 里配的 `resource/list` 不是网页真正请求的地址**（网页用 resource/ids + resource/infos）。不验权限那一下——那要 Owner 本人 |
| `read_what_his_diagnosis_left_behind.py` | **每次发布**（deploy 第 8.86 步，**播报不是门**） | 他按过那颗诊断按钮没有？按了就把该盯的地址和响应字段骨架印出来。没有这一步的话，他做完了他那一份而我不知道——机制建好了没人去看，这次断在我这一头 |
| `check_a_relation_never_loses_the_author.py` | **每次发布**（deploy 第 8.85 步，**播报不是门**） | 按「平台 × 关系」分组算作者填充率，某一组条数够多而填充率为 0 就说出来。按**产品显示时**的口径算（点赞数不算作者）。整体看抖音 54/86 缺失像是**一半取不到**，拆开才看见 **favorite 16/16、like 69/69 都是零**——抖音那条自动取数路从没取到过一个真作者，而 B 站同一套机制是 93–99% |
| `check_every_guide_step_has_a_drill.py` | **发布门每次跑**（`final_verify.py`） | 使用说明里每一节小标题，都登记了一个真的在跑的演练。隔壁那道 `check_the_guide_matches_the_product.py` 只回答**那颗按钮存不存在**，不回答**这一步有没有人走过** |
| `forget_button_render_drill.py` | **每次发布**（deploy 第 8.65 步） | **从公开域名取回来的那份前端**，在真 Chrome 里画不画得出这次发的界面（0.0.0.29 实测：/health 报新版，而 CDN 给的 app.js 还是旧的、少了「删除并清空」） |
| `from_zero_drill.py` | **每次发布**（deploy 第 8.68 步） | **在刚部署的那个镜像上**从空库走到能用：连账号 → 同步 → 看得见（标题/作者都对）→ 删除并清空 → 又空了 → 重连 → 再同步。跑在一次性容器的 tmpfs 上，**碰不到他的库** |
| `real_platform_into_archive_drill.py` | **每次发布**（deploy 第 8.55 步） | **一个真平台的收藏，真的进到档案馆里**：B 站公开收藏夹（不带登录态）→ 插件自己的 `readFolder` → `POST /v1/captures/batch` → 从库里**按标题**读回来。跑在一次性容器的 tmpfs 上；**跑前跑后各数一次他的库，条数变了就红**（不是写着「碰不到」，是量过）；只证明 bilibili 一个平台 |
| `disaster_recovery_drill.py` | **每次发布**（deploy 第 8.69 步，**抽样 25 个制品**，起点按版本号环形挪） | 索引和制品还对不对得上：索引说有 552 个，那些是不是真取得回来、字节是不是那个哈希 |
| `restore_private_database_drill.py` | **每次发布**（deploy 第 8.69 步，实测 2 秒） | Private-Database 的 fact 包取得回来吗，哈希逐条对得上吗 |
| `restore_runtime_db_drill.py` | **每次发布**（deploy 第 8.69 步，经 `check_the_backup_can_actually_be_restored.py`） | 运行库快照取回来之后，真的打得开吗、里面是不是他的数据 |

> ****定期**那一档原来没有闹钟。**（2026-08-11 查明，当天解掉了一格）
>
> `run_all_drills.py` 此前在四处写着这三个「真跑在部署第 8.95 步（生产机上）」——
> **查无此步**：部署脚本里这三个脚本名出现 0 次，8.9 是**今天确认得到几份副本**的
> 播报，不是恢复演练。也就是说**东西还在不在、拿不拿得回来这件事**没有任何自动触发。
>
> ### 运行库那一格已经接进流程了
>
> 拦着它的一直是「要在生产机上跑、要几分钟」。今天两个数都量了：
> 快照 **1.1 MB/批**，r2 + oci 各取一次**实测 12 秒**；按铁律 7 算月操作量
> ≈ 4.5 万次，是 R2 免费额度的 **4.5%**。**没有理由再停在靠人记得那一档**——
> 所以按**可重建的自己做并做成自动的**这条规矩，直接接进了每次部署。
>
> 第一次真跑就抓到这个演练自己的两个毛病（都已修、都有反例）：
>
> | 症状 | 真因 | 反例 |
> |---|---|---|
> | 远端那份不见了 → 抛 botocore 回溯，stdout 上没有结构化结果 | 没包 `download_file` | 把 object_key 改成不存在的键 → `SNAPSHOT_MISSING_FROM_STORE` |
> | 一个**空的**合法 SQLite 也报 PASS | `_counts` 把缺的表悄悄省掉键，且没人比对内容 | 把**一条内容都没有就判红**改反 → 真数据上立刻变红 |
>
> 第二条不是假想：同一天生产上就躺着一个 0 字节的同名运行库
> （见 `check_no_decoy_runtime_db_on_production.py`）——备份哪天对着那个路径拍一张，
> 这个演练原来会绿着说「取回来了」。
>
> ### 另外两格也量完了，也接上了
>
> 先量再决定，量出来的数字没给**靠人记得**那一档留余地：
>
> | 演练 | 实测代价 | 处置 |
> |---|---|---|
> | `restore_private_database_drill.py` | **2 秒** | 每次部署全跑 |
> | `disaster_recovery_drill.py` | 1.3 秒/制品，全量 552 个约 **12 分钟** | 每次部署抽 **25 个（32 秒）** |
>
> 三个加起来一次 **50 秒**。
>
> **抽样这件事必须说清，否则它就是一句假话。** `--limit N` 原来是
> `ids[: N]`——确定性地取头 N 个。接进每次部署那一刻这一点变致命：552 个制品里
> 永远只有同样的 25 个被验过，另外 527 个一次也不会被碰到，而日志上写着 **25/25 全过**。
> 现在起点由 `--offset` 决定并环形绕回（部署按版本号取，每发一版挪一格），
> 报告里把窗口和总数一起打出来：`这次验的是 552 个里的 25 个（窗口 498–523）——不是全量`。
>
> ### 第三份副本：那句**只有 Owner 能授权**是错的
>
> 8.69 步现在**三份都真取一次**（实测各 193 条）。它此前一直报
> `GITHUB_COPY_NOT_VERIFIED`，而查清之后，两个原因都在我们自己这边、
> 没有一个跟权限有关：
>
> | 表面现象 | 真因 |
> |---|---|
> | 第三份没有收据 | **比错了对照物**：三份写齐只发生在每天 03:28 那次备份服务里，而这里一律取 15 分钟一份的最新那批 |
> | 「缺少 gh 或 GitHub 令牌」 | **拿错了令牌**：`.env` 指的 `/run/secrets/github_token` 是容器内路径，宿主机上没有；按文件名回退正好落到另一把**看不见那个仓**的令牌 |
>
> 同一台机器上的 `github_markdown_token` 对那个仓是 **ADMIN**——备份服务自己
> 就是靠 `LoadCredential` 映射到它才写得成的。判据现在照抄那个单元的映射，
> 取不到映射就明说，**不许再猜一把令牌**。

## **改到那条路时** 这一档取消了

它原来是这张表最弱的一格：靠人判断「我这次改动碰到哪条链了」，
而判断错的代价是那条链这一版整个没有证据。**我自己就漏判过一次**
（改了弹窗和侧边栏，只想起来跑连接面板那个）。

零参数化做完之后这件事变成了一条命令：

```bash
python scripts/run_all_drills.py
```

14 个演练，实测 4 分 42 秒，已接进 `deploy_to_production.sh`——**发布前自动全跑**。
判断不再需要。下面清单里那一列保留，是为了说清每个演练在验什么，
不再是"要不要跑"的依据。

恢复类那三个**本机**仍然跑不了（远端凭据只在生产机上），
`run_all_drills.py` 的输出里会明说没跑它们，**不让人以为全覆盖了**——
但它们不再**靠人记得**：三个都挂在部署第 8.69 步上，在生产机上真跑。


## 提交前那道门（2026-08-12 才真正装上）

`scripts/git-hooks/pre-commit` 早就写好了，它的文件头写着「『下次注意』不是修复，
这个 hook 是修复」。**而它从来没有被装上过**：`.git/hooks/pre-commit` 那个位置上
装的是另一个守卫（铁律 2 的主树保护），它在 worktree 里第一件事就是 `exit 0`。

没有任何东西装它、没有任何判据验它装没装、README 和 AGENTS.md 一个字没提它。
**一个没被装上的守卫不是守卫**——当天我七次在文档判据红着的情况下提交，
一次都没被拦住，就是它。

```bash
bash scripts/install_git_hooks.sh          # 装（会把原来那个守卫链上，不踩掉）
bash scripts/install_git_hooks.sh --check  # 只看装没装
```

**链，不是盖**：`.git/hooks` 整个仓库共享，那个主树守卫是活的且重要，
所以安装脚本把它搬到 `pre-commit.chained`，新 hook 第一件事就是调用它——
它说不行就不行，轮不到发布门说话。

三种情形都验过：主树 main 上仍被铁律 2 拦住（退出 1）；worktree 里门绿放行
（退出 0，36 道）；故意造一处文档违规当场拦住（退出 1，并打印红在哪）。
