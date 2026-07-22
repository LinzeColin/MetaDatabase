# 来源目录

- 生成时间: 2026-06-26T21:51:00+10:00
- 来源配置: `config/owner_controls.yaml`
- 配置版本: `owner-controls-v2`

## 板块

| 板块 ID | 启用 | 名称 | 权重 |
|---|---:|---|---:|
| `B1` | 是 | 研究前沿 | 25 |
| `B2` | 否 | 顶级期刊 | 20 |
| `B3` | 否 | 中国政策法规 | 25 |
| `B4` | 否 | 美国科技金融官方信号 | 20 |
| `B5` | 是 | 跨板块总览 | 10 |

## 来源

| 来源 ID | 板块 | 启用 | 名称 | 采集方式 | 层级 | 频率 | 权重 | 健康状态 |
|---|---|---:|---|---|---|---|---:|---|
| `SRC-ARXIV` | `B1` | 是 | arXiv Atom API | `official_atom_api` | `required` | `daily` | 100 | 已启用 (`active`) |
| `SRC-BIORXIV` | `B1` | 否 | bioRxiv public metadata API | `official_biorxiv_details_api` | `required` | `daily` | 0 | 影子测试 (`stage2_test`) |
| `SRC-MEDRXIV` | `B1` | 否 | medRxiv public metadata API | `official_medrxiv_details_api` | `required` | `daily` | 0 | 影子测试 (`stage2_test`) |
| `SRC-TOP-JOURNALS` | `B2` | 否 | Top journal public feeds | `planned_official_public_feeds` | `important` | `planned` | 0 | 规划中 (`planned`) |
| `SRC-CHINA-POLICY` | `B3` | 否 | China official policy sources | `planned_official_web_or_rss` | `required` | `planned` | 0 | 规划中 (`planned`) |
| `SRC-US-OFFICIAL` | `B4` | 否 | US official technology and finance signals | `planned_official_web_or_api` | `important` | `planned` | 0 | 规划中 (`planned`) |

## Cloudflare v1.2 来源救援补充面

本节由 [`config/cloudflare_source_candidates_v1_2.json`](../../config/cloudflare_source_candidates_v1_2.json) 生成，属于当前 Cloudflare 产品线，不改变上方旧本机 `owner_controls.yaml` 目录。任务为 `ADP-V12-S1-T001`；真实 live 路由仍由 [Worker registry](../../deploy/cloudflare/worker_cloud.js) 决定。

| 来源 ID | 板块 | 提供方 | 状态 | 重试/活动边界 |
|---|---|---|---|---|
| `gnews-us-tech` | `board4` | Bing News RSS | `active_live` | 当前单次 live 抓取保持不变 |
| `gnews-us-tech-google-candidate` | `board4` | Google News RSS | `candidate_not_live` | timeout/502/503/504 最多 3 次，1000/3000ms；redirect=`manual_fail_closed`，不接入 Worker、不部署 |

可执行预算从真实 Worker registry/常量推导：当前 daily live external 最坏 `32` 次；候选以后若获授权替换现有 Bing 单次路径，最多增加 2 次，投影 `34/50`，保留 16 次余量。手动 redirect 把每个 attempt 封顶为 1 个 subrequest。验收入口为 [候选实现](../../deploy/cloudflare/google_news_candidate.mjs) / [可执行验证](../../tools/verify_google_news_candidate.mjs)。
