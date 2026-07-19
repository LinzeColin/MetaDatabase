# Third-Party Notices and Exclusion Register

当前 `xhs-douyin-2notion` 没有发布包、没有第三方 runtime/build package，也没有复制或捆绑下列上游代码。Stage 1 foundation scaffold 的 npm/uv locks 只包含本地 workspace，registry package、install script 与 runtime dependency 均为 0；Node、npm、Python 和 uv 是外部构建工具，不随产品分发。此文件汇总 Phase 0.2 依赖审计、Phase 0.5 竞品排除与 foundation.001 零依赖结论，不代表已授权启用 Adapter。

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
- Current scope: fixed-Commit audit reference only；不安装、不运行、不作为产品 Adapter、不接收其输出，not bundled, not a runtime dependency.

任何未来实际引入或执行都必须由新的 Owner Change Event 授权，并在独立 Run 重新核验当时 Commit、License、NOTICE、lock、SBOM、平台政策与分发边界；现有 Task Pack 不提供该授权。

## ShilongLee/Crawler（竞品研究，排除）

- Upstream: `ShilongLee/Crawler`
- Commit: `765207310a90a81c615c0ba2df124543b424af89`
- License: custom `Non-Commercial Use License 1.0` / `LicenseRef-ShilongLee-NON-COMMERCIAL-1.0`，禁止商业用途和商业竞争。
- Current scope: research-only clean-room idea reference；disabled, not bundled, not a runtime dependency；copied/vendored files: 0。
- Forbidden: 复制、修改、合并、翻译、Vendor、运行、容器化打包其源码，或移植其签名 JavaScript、Cookie/URL/Header/参数模板。
- Future gate: 必须先取得权利人书面商业授权，再进行独立 License、Provenance、Security、SBOM 和平台政策复核；否则永久排除。
