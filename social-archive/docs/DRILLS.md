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
| `pwa_render_drill.py` | 改到那条路时 | 页面上那两段话真的显示出来了吗 |
| `forget_button_render_drill.py` | **每次发布**（deploy 第 8.65 步） | **从公开域名取回来的那份前端**，在真 Chrome 里画不画得出这次发的界面（0.0.0.29 实测：/health 报新版，而 CDN 给的 app.js 还是旧的、少了「删除并清空」） |
| `from_zero_drill.py` | **每次发布**（deploy 第 8.68 步） | **在刚部署的那个镜像上**从空库走到能用：连账号 → 同步 → 看得见（标题/作者都对）→ 删除并清空 → 又空了 → 重连 → 再同步。跑在一次性容器的 tmpfs 上，**碰不到他的库** |
| `disaster_recovery_drill.py` | 定期 | 只用远端三份副本，能不能把档案馆重建出来 |
| `restore_private_database_drill.py` | 定期 | Private-Database 的 fact 包取得回来吗，哈希逐条对得上吗 |
| `restore_runtime_db_drill.py` | 定期 | 运行库快照取回来之后，真的打得开吗 |

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

恢复类那三个仍然要人跑（它们要真实的备份清单，参数是题目本身），
`run_all_drills.py` 的输出里会明说没跑它们，**不让人以为全覆盖了**。

