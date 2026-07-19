# Third-Party Notices and Exclusion Register

当前 `xhs-douyin-2notion` 没有发布包，也没有复制或捆绑下列研究上游代码。`TSK.x2n.foundation.002` 为 Contract 开发新增 5 个冻结 Python Runtime registry packages，以及 TypeScript `7.0.2` 与 20 个同版本、按平台可选的 build-only packages；全部 npm install script 为 0。精确组件、依赖边和作用域见 `machine/sbom/stage_1_foundation_002.cdx.json`。Node、npm、Python 和 uv 仍是外部构建工具，不随产品分发；本文件不授权任何 Adapter、真实账号或平台执行。

## Contract Runtime / Build Dependencies

| Package | Version | License | Scope |
|---|---:|---|---|
| `pydantic` | `2.13.4` | MIT | Direct Contract runtime |
| `pydantic-core` | `2.46.4` | MIT | Transitive Contract runtime |
| `annotated-types` | `0.7.0` | MIT | Transitive Contract runtime |
| `typing-extensions` | `4.16.0` | PSF-2.0 | Transitive Contract runtime |
| `typing-inspection` | `0.4.2` | MIT | Transitive Contract runtime |
| `typescript` | `7.0.2` | Apache-2.0 | Direct build/check only |
| `@typescript/typescript-*` | `7.0.2` | Apache-2.0 | 20 lock-resolved optional platform build packages |

- Pydantic 与 transitives 只用于严格 JSON/Schema Contract validation；不提供网络、浏览器、数据库或平台能力。
- TypeScript 只用于 `tsc --noEmit` 类型对等检查，不进入 Companion Runtime；npm lock 中 registry component 共 21 个，均无 install script。
- 当前源码阶段通过 package manager 消费原包，没有将依赖源码复制进仓库。任何未来 Installer/Release 必须保留对应包内 License/NOTICE，并以 Release SBOM 重新验证实际打包集合。
- `package-lock.json` 与 `uv.lock` 是版本真源；SBOM 生成器对包集合、版本、License、作用域和 install-script 字段 Fail Closed。

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
