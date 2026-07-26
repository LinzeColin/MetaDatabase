# CB-000 Fixed-Source Baseline

## Result

P0.1 使用三个历史仓库的精确 commit 作为一次性输入。每个 commit 只在隔离的
临时 bare repository 中按 SHA 获取一次；取证后临时仓配置的 remote 数为 `0`。
导入内容为普通文件，不含 `.git`、`.gitmodules`、submodule 或 symlink。

固定输入不构成持续 upstream、支持、同步、自动更新或 endorsement 关系。

## Locked identities

| Source | Commit | Git tree | Commit date | Package / Node | Imported path |
|---|---|---|---|---|---|
| `WenXiaoWendy/cyberboss` | `373ab17d283f1e3b304a6a36e17e9e8d44f1acfc` | `d175d890153fc753895a0ebcf11b5eb65d83a5ad` | `2026-06-05T07:09:36+08:00` | `cyberboss@0.1.0`; `>=22` | `CyberBoss/app/` |
| `WenXiaoWendy/timeline-for-agent` | `62e1fa8db26f7a9147ad96579fc4077a39b94c8b` | `cd1fbe0e5fac50ca3b446afc04d3656f871c9b4b` | `2026-06-05T07:08:07+08:00` | `timeline-for-agent@0.1.0`; `>=22` | `CyberBoss/vendor/timeline-for-agent/` |
| `WenXiaoWendy/whereabouts-mcp` | `e36cb307f082f747327fd3a5d406fd9718a1428d` | `cc22811b03ab4d411379421894e3408eb1964c14` | `2026-04-22T22:52:00+08:00` | `whereabouts-mcp@0.1.0`; `>=22` | `CyberBoss/vendor/whereabouts-mcp/` |

没有任何来源提供独立 tag、author 或 standalone copyright metadata；因此只保留
可证明的仓库身份、commit、源码和许可证，不推测作者或版权声明。

## Deterministic bundle hashes

Bundle hash 定义为：按相对路径排序的逐文件 SHA-256 manifest 本身的 SHA-256。
`node_modules/` 不属于 source bundle。

| Source | Locked files | Locked manifest hash | Current files | Current manifest hash |
|---|---:|---|---:|---|
| CyberBoss | 122 | `62daccaf1f18a167e2865d114287de9f671d91a9ba1709b765ffb92991591dbb` | 123 | `ddab31c724f4b8d97a6196d6d7f71a7347b7f715aa6a3db5fe54815c6fbbadd9` |
| timeline-for-agent | 83 | `9ab9bb47b5b7a0222ebb9cda56d96839e37d780e77359dff6a3cfc081de40986` | 83 | `9ab9bb47b5b7a0222ebb9cda56d96839e37d780e77359dff6a3cfc081de40986` |
| whereabouts-mcp | 17 | `13f55a13f1891cc859fde7f8b5177a85b9e01904a555265479c2d9c92d8ffe2c` | 17 | `13f55a13f1891cc859fde7f8b5177a85b9e01904a555265479c2d9c92d8ffe2c` |

完整 manifests 位于 `manifests/`，机器事实位于
`CyberBoss/machine/source-lock.json`。

## Lockfiles

| Source | Locked lockfile | Locked SHA-256 | Current SHA-256 | State |
|---|---|---|---|---|
| CyberBoss | `package-lock.json` | `a33cf82a6e117bf5284f0c805494d22ed9dcbc87d73e108b325c84c3b4395c00` | `0932f1d169965da5453e0a5803457988840200b2489e914e3ace5238f714f555` | Rebuilt for local `file:` bundles |
| timeline-for-agent | `package-lock.json` | `13b247c63c0a985ea32412d6c9b3d0051336e558b120ec6184574c5c589fb13a` | same | Preserved exactly |
| whereabouts-mcp | none | `null` | `null` | Locked source contains no lockfile |

## Current modifications from the locked CyberBoss source

新增：

- `.npmrc`：固定 `install-links=true`，使本地 package 以普通复制包安装。

修改：

- `.gitignore`：精确放行 `src/adapters/runtime/**` 应用源码，避免被
  `CyberBoss/.gitignore` 的 deploy-local `runtime/` 规则误排除；
- `package.json`：两个 moving Git dependency 改为本地 `file:`；增加
  `node --test`。
- `package-lock.json`：重锁为本地 file packages，不含 Git URL 或 branch。
- `src/adapters/runtime/codex/rpc-client.js`：移除当前 App Server schema 不支持的
  `thread/start {input}` 与 wire-level `accessMode`。
- `test/codex-rpc-client.test.js`：增加当前协议与安全策略回归。
- `test/sticker-service.test.js`：测试 fixture 从作者机器绝对路径改为动态项目根。

两个 vendor bundle 与锁定 commit 逐文件完全一致。详细集合差异见
`source-bundle-diff.json`。

## Separation proof

- 应用安装只解析 npm registry 的 integrity-locked 包和两个本地 `file:` package；
- package manifests/lockfile 不含 `git+`、`github:`、`#main` 或 `#master`；
- source/runtime scripts 不含 GitHub `clone/fetch/pull` 或运行时源码下载；
- 三个 bundle 均没有 Git metadata、remote 或 submodule；
- 四个已验证的来源文件保留原始 whitespace 字节；`.gitattributes` 的例外精确到
  文件，不放宽其他文件的 `git diff --check`；
- 后续任何历史来源更新必须由新的 Owner Change Event 发起。
