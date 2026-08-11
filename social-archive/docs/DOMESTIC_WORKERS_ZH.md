# 东方平台 Worker —— 这条路已作废（v0.0.0.7 / T03）

> **不要照着这份文档的旧内容操作。** 它当时让你运行 `scripts/start_workers.sh`
> 与 `scripts/stop_workers.sh`，这两个脚本连同 `compose.workers.yaml` 已经删除。
> 照着做只会得到「命令不存在」；就算把它们恢复回来，结果也仍然是 0 条。

## 为什么删

那三个隔离 Worker（XHS-Downloader / DouK / 快手）是按「服务端跑上游工具的 HTTP API」
设计的。实测证伪：**它们的 HTTP API 里根本没有收藏枚举接口。**

- `XHS-Downloader` 暴露的是 `/xhs/detail` —— 单篇详情
- `DouK` 只有 detail / account / mix / live / comment / search —— 同样没有收藏
- 连最成熟的小红书工具都不是从服务端 Cookie 去列收藏的，它是在浏览器里列的

也就是说，把它们按那份 compose 起起来、接上去，拿到的还是单篇详情，
一次同步下来**依然是 0 条**——而界面会显示成功。这正是 v0.0.0.6
「点了同步是 0」的其中一条成因。

详见 `CONFLICT_ORDER.md` 的 SUPERSEDED 表与 `evidence/T00/CURRENT_TRUTH.json`。
防止它被加回来的守卫在 `tests/focused/test_superseded_paths_stay_removed.py`
（判据打在「`python main.py api` 这个启动形态」上，不只看文件名）。

## 现在国内三源怎么取数

在 **Owner 自己的浏览器里，拦截平台自己发出的收藏列表 API 响应**，
服务端只负责解析与入库。

- 扩展在 MAIN world 注入 `net-observer.js`，把 `window.fetch` 与
  `XMLHttpRequest` 包一层；页面自己请求自己的收藏接口时抄一份响应体
- **不合成请求**：签名（小红书 x-s/x-t、抖音 a_bogus）全由页面自己完成
- **不修改请求或响应**：页面拿到的东西和我们不存在时一模一样
- **不读 Cookie**：一个字节都不读。国内平台的登录态一步都不离开浏览器
  （INV-DOMESTIC-COOKIE-STAYS）

比 DOM 抓取强在：拿到的是 API 原始 JSON，字段全、翻页游标现成、
平台改版只要接口没动就不受影响；而 DOM 抓取依赖类名和结构，改一次版就静默变空。

## 还没跑通的部分

只有 B站的收藏接口前缀有据可依（`api.bilibili.com/x/v3/fav/resource/list`，
三处独立来源互相印证）。小红书与抖音的前缀**尚未实测**，
因此代码里写的是 `null` 而不是一个看着像的值 ——
装一个前缀为空的观察器等于永远拦不到，而界面会显示「已连接」。

取得它们的正当途径是 T09 **抓到即固化**：第一次真实响应原样落盘成 fixture，
解析器测试由它生成。

## 那条边界没有变

无论走哪条路，本产品都不复制 GPL 源码、不接收平台账号密码、
不绕过验证码与设备风控、不使用住宅代理。

原文档最后那句仍然成立，只是主语换了：拦截器与解析器同样是可单独启停、
可熔断的旁路，不把第三方代码或登录态带进 Core。
