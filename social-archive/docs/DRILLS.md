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

## 清单

| 演练 | 什么时候跑 | 它回答的问题 |
|---|---|---|
| `shipped_package_drill.py` | 每次发布 | 他下载的那个 zip，和我一直在测的是同一个东西吗；权限没给时它说得对吗 |
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
