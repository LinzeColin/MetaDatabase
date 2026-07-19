# Third-Party Notices and Exclusion Register

当前 `xiaohongshu-douyin-2notion` 没有发布包、没有第三方 runtime dependency，也没有复制或捆绑下列上游代码。此文件是 Phase 0.2 的 notice/exclusion 基线，不代表已授权启用 Adapter。

## douyin-downloader

- Upstream: `jiji262/douyin-downloader`
- Commit: `ef3ad18c2b50e38e534f72aabe2b3fbb0b3fadd7`
- License: MIT
- Copyright: Copyright (c) 2026 jiji262
- Current scope: audited candidate, disabled, not bundled, not a runtime dependency.
- Future distribution gate: preserve the upstream MIT copyright and permission notice in distributed copies/substantial portions; generate exact lock, transitive license report and SBOM first.

## xiaohongshu-exporter

- Upstream: `zhulin025/xiaohongshu-exporter`
- Commit: `130b3ceb156278597c16f7e7e98d93ff42acaadf`
- License state: `UNVERIFIED_MISSING_LICENSE_FILE` at this tree; README claim alone is insufficient.
- Current scope: clean-room behavior/UX reference only; copied files and bundled code: 0.

## MediaCrawler

- Upstream: `NanmiCoder/MediaCrawler`
- Commit: `0625e01a6bc717a3fc9c96d3dac7fb8957043838`
- License: `NON-COMMERCIAL LEARNING LICENSE 1.1` (non-SPDX, restricted).
- Current scope: external non-commercial research only, disabled, not core, not bundled, not a runtime dependency.

任何未来实际引入都必须在独立 Run 重新核验当时 Commit、License、NOTICE、lock、SBOM 与分发边界。
