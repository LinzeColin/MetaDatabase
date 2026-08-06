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

## 为什么不全塞进发布门

发布门在每次提交前跑（约 5 秒）。这些演练每个都要起一个真 Chrome 或连远端，
一分钟起步。全塞进去等于逼人绕过它。所以分三档：

| 档 | 什么时候跑 | 谁触发 |
|---|---|---|
| 每次发布 | 发布前，包已经打好之后 | `scripts/deploy_to_production.sh` |
| 改到那条路时 | 改动碰到它验的那条链 | 人（改的人） |
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
| `extension_update_in_place_drill.py` | 每次发布 | 在原文件夹里覆盖再重载：ID 变不变、版本更不更新、已配对的凭据还在不在 |
| `list_shape_end_to_end_drill.py` | 改到那条路时 | 不知道接口地址，能不能从页面自己发的响应里认出收藏列表（`--platform` 逐个平台跑） |
| `bilibili_end_to_end_drill.py` | 改到那条路时 | 从连接账号到档案馆里真的出现条目，真 Chrome 里整条通不通 |
| `bilibili_acquisition_drill.py` | 改到那条路时 | B 站收藏夹取数路真的读得到吗（打真接口） |
| `extension_capture_drill.py` | 改到那条路时 | 「拦截 → 读懂」整条链 |
| `extension_capture_buffer_drill.py` | 改到那条路时 | 诊断按钮之后，两件最容易骗人的事 |
| `extension_save_page_drill.py` | 改到那条路时 | 「保存当前页面」那一下真的送到档案馆了吗 |
| `extension_routing_drill.py` | 改到那条路时 | 扩展的同步分流对不对 |
| `extension_platform_wiring_drill.py` | 改到那条路时 | 加一个平台时，四张表都接上了吗 |
| `extension_bridge_boundary_drill.py` | 改到那条路时 | 档案馆页面能给令牌，但不能改它往哪儿发 |
| `extension_install_page_drill.py` | 改到那条路时 | 装着旧插件的人能不能靠那一页更新掉 |
| `pwa_render_drill.py` | 改到那条路时 | 页面上那两段话真的显示出来了吗 |
| `disaster_recovery_drill.py` | 定期 | 只用远端三份副本，能不能把档案馆重建出来 |
| `restore_private_database_drill.py` | 定期 | Private-Database 的 fact 包取得回来吗，哈希逐条对得上吗 |
| `restore_runtime_db_drill.py` | 定期 | 运行库快照取回来之后，真的打得开吗 |

## **改到那条路时** 怎么才不变成一句空话

它现在确实还靠人判断。**这是这张表目前最弱的一格**，写在这里而不是藏着：
判据只能保证 **什么时候跑** 被写下来了，保证不了那一刻真的有人跑。

已经收紧的那一格是 **每次发布**——它有脚本调用方，判据会核。
把更多演练往那一档挪的代价是发布变慢，值不值得按那条路的出错历史决定，
不按感觉决定。
