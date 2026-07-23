# 仓库布局与边界

## 公开代码仓

```text
LinzeColin/MetaDatabase/
├── .github/workflows/
│   ├── moomooau-ci.yml
│   ├── moomooau-ingest.yml
│   ├── moomooau-reprocess.yml
│   ├── moomooau-recovery-drill.yml
│   └── moomooau-release.yml
└── LinzeDatabase/MooMooAU/
    ├── AGENTS.md
    ├── README.md
    ├── VERSION
    ├── pyproject.toml
    ├── src/moomooau_archive/
    ├── tests/
    ├── schemas/
    ├── inventory/
    ├── evidence/
    ├── machine/
    └── 文档/
```

GitHub 只识别仓根 `.github/workflows`，因此工作流不放进项目子目录；用 `paths`、命名和测试限制到 MooMooAU。

## 唯一私有数据仓

私有仓名称不进入公开树。受保护配置只提供唯一 immutable Repository ID，运行时通过 GitHub API
解析当前名称；改名不改变身份，也不创建第二仓。

```text
MooMooAU/
├── Raw/
│   ├── messages/YYYY/MM/*.eml.age
│   └── objects/<prefix>/*.bin.age
├── Processed/
│   ├── document_envelopes/v1/*.jsonl.age
│   ├── statements/v1/*.jsonl.age
│   ├── analytics/v1/*.parquet.age
│   └── timeline_events/v1/*.jsonl.age
├── PrivateInventory/*.json.age
├── State/*.json.age
├── Manifests/*.json.age
└── Quarantine/*.age
```

固定 live Release：

```text
Tag: moomooau-live
Asset: timeline-latest.png.age
```

## 边界守卫

- 私有写入 path prefix 必须是 `MooMooAU/`；
- Release tag/asset 必须完全匹配固定值；
- GitHub App 只安装到受保护 Repository ID 对应的该私有仓；
- 工作流比较变更树，发现无关路径变化立即失败；
- 不创建第二私有仓、第二数据根或历史 Timeline Release；
- 私有仓中不新增源代码、Workflow、测试或 Agent Prompt。
