# Public Artifact / Private Runtime Policy

## 一条规则

仓库与构建制品只保存可公开的专有代码、契约、合成 Fixture 和脱敏紧凑证据；Runtime、全部下载、浏览器状态、凭据、私人内容、原始媒体和本机路径只存在于仓库外的 `X2N_DATA_ROOT` 或 OS Keychain。

原始 taskpack 没有指定本机绝对下载路径。Owner 指定的下载目的地使用逻辑名 `X2N_DOWNLOAD_DESTINATION`，项目根固定为 `${X2N_DOWNLOAD_DESTINATION}/xhs-douyin-2notion`；目的地已有同级条目不属于本项目，仅允许不回显名称的聚合数量/元数据指纹审计，禁止读取内容、导入、移动、链接、修改或删除。下载父目录与上游软件同名不构成依赖或运行授权。实际绝对解析值只存在私有 marker，不进入 Git。

## 统一根布局

```text
X2N_DATA_ROOT/
├── downloads/
│   ├── xiaohongshu/runs/
│   ├── douyin/runs/
│   ├── bilibili/runs/
│   ├── kuaishou/runs/
│   ├── weibo/runs/
│   ├── taobao/runs/
│   └── external_research/runs/   # 仅临时匿名源码审计；不执行竞品、不接收产品数据
└── runtime/
    ├── canonical/                # Stage 1 前不得创建 DB
    ├── checkpoints/
    ├── temp_media/
    ├── browser_profiles/
    ├── library/
    ├── logs/
    ├── diagnostics/
    ├── backups/
    ├── models/
    ├── provider_cache/
    ├── owner_input_contract.local.json       # 0600；仅默认/私有引用，不含 Secret
    └── owner_recovery_attestation.local.json # 0600；默认不存在；只含闭合 Owner 恢复声明
```

所有 Adapter 的工作目录和输出必须解析到这个根下；不得采用自身默认下载目录。成功任务的原始媒体即时删除，失败 Lease 最长 24 小时。目录存在不代表相应功能已授权。

## 权限与备份

- Root 与目录：Owner-only（POSIX `0700`）；marker：`0600`。
- Root 禁止 Spotlight 索引。
- macOS 可能在私有根生成根级 `.DS_Store`；仅允许普通文件、Owner-only `0600`、不超过 64 KiB，且它不属于产品数据或证据。
- 目标策略是整个 `X2N_DATA_ROOT` 排除 Time Machine；任何子路径都不能作为第二耐久目的地，
  Private-MetaDatabase 的已验证 receipt 才能满足 durability/Release Gate。
- 当前只完成合同版本化，系统设置仍是历史逐子目录状态；不得声称整根已排除。
  `TSK.x2n.uxops.005` 必须在 Owner 明确授权后记录 pre-state、执行 macOS
  `tmutil addexclusion`、复验根和全部 required subpath，并保留前态/显式回滚证据。失败时保持
  exclusion 是更安全的状态；只有新的 Owner 动作才能回滚。非 macOS 或控制不可用时标记
  `UNSUPPORTED_OS_BACKUP_CONTROL` 并 Fail Closed。

## 耐久恢复与删除

- `Private-MetaDatabase` manifest/`verify` 是 area-global。x2n 只以精确
  `domain=xhs-douyin-2notion` 行及逐对象 `get`/hash/reassemble/SQLite integrity 作为 durability
  Gate；area-global `verify` 只可生成不含路径/名称的 advisory。其他 domain 缺对象不阻断 x2n，
  x2n domain 缺对象必须 Fail Closed。
- x2n 禁止 Private-Database `put/delete`。本项目的删除只作用于 active SQLite 和派生 Sink，并在
  最新 restore manifest 记录单调 `deletion_epoch` 与逻辑 tombstone；恢复拒绝旧 epoch、重放当前
  tombstone，防止 retained history 复活内容。
- durable hard erase 不属于本项目可声称的能力，状态固定为
  `UNSUPPORTED_OWNER_PRIVATE_DB_GOVERNANCE_REQUIRED`。本地 runtime wipe 不能冒充耐久删除。

## Git Allowlist

- 源代码、Schema、契约、迁移代码（不含真实 DB）。
- 明确合成且有 manifest 的 Fixture。
- 不含正文、Token、Cookie、URL Query、用户名和绝对路径的聚合/脱敏证据。
- Product Design、ADR、Run Contract、Task/Acceptance Registry。

## Git/Build/Release Denylist

- SQLite、WAL/SHM、浏览器 Profile、媒体、真实 Markdown/转录/OCR/关键帧。
- `.env`、Key、Token、Cookie、Session、Keychain 导出、Notion/模型 Secret。
- 平台媒体/头像/封面 CDN URL、签名参数、追踪参数。
- 本机用户名、绝对路径、私有根 marker、完整日志和诊断正文。

Owner 恢复回执属于仓库外的私有控制证据，不属于 Git Allowlist。即使验证通过，也只允许进入独立 Stage Review Resume；不能被解释为 G0 PASS、Stage 1 授权或上传授权。

## Fail Closed

- `.gitignore` 只是第一层；`scripts/verify_phase_0_1.py` 必须扫描实际项目树。
- 合成 Fixture 也必须登记来源、生成方式、字段和预期敏感模式命中数。
- Phase 0.1 只验证边界与空骨架；DB/Markdown/Notion/Release 等下游 Scope 均保持 NOT_RUN。
