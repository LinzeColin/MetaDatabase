# REA：使用方式与价值判断

日期：2026-10-10。当前交付状态：源码接入（SOURCE_ONLY）。

## 项目来源与落位

- 上游：[morluto/rea](https://github.com/morluto/rea)。
- 自有 fork：[LinzeColin/rea](https://github.com/LinzeColin/rea)。
- 母仓入口：`LinzeColin/MetaDatabase/REA`，采用 Git 子模块，保留独立 fork、MIT 许可和上游更新关系。
- 本次源码及 npm 发布版本均为 `6.3.0`；npm 包名为 `rea-agents`。
- 本机路径：`~/Documents/Codex/GithubProject/MetaDatabase/REA`。

本次交付包含源码、项目登记和使用说明。REA 安装、智能体 MCP 配置、分析引擎和实际目标分析属于运行接入阶段。

## REA 能做什么

REA 把应用分析工具接到智能体，也提供 CLI。它可以从 JavaScript/Electron 应用目录或 ASAR 文件生成模块关系、入口、导入、路由和 IPC 线索；原生程序分析可接 Hopper、Ghidra 或 IDA。网站、Android APK、.NET 等目标各有自己的依赖与支持范围。

典型交付是：某个按钮对应哪个入口、经过哪些模块、在哪里读配置或写文件、结论来自哪些源码位置，以及哪些行为仍需实际观察。智能体可以据此设计自己的实现和修复方案。静态分析所得的调用关系与实际运行行为分别记录。

官方说明：[中文 README](https://github.com/morluto/rea/blob/main/README_zh.md)、[Electron 分析指南](https://rea.tools/guides/javascript/)。

## 当前运行条件

本机观察到 Node `25.7.0`、npm `11.10.1`。REA `6.3.0` 声明的 Node 范围为 `^22.19.0 || ^24.11.0 || >=26.0.0`。运行接入时选择符合范围的 Node；建议先采用 24.x LTS、版本至少 24.11。

另一项关键条件是 Owner 当前的“禁止任何哈希、SHA、检验”规则。原版 REA 的 JavaScript 分析会生成制品与 Evidence 摘要，源码 `src/artifacts/ArtifactHash.ts` 使用 SHA-256；官方 JavaScript 分析文档也明确写出 Evidence hashing。`integrity_policy=record-and-continue` 表示保留矛盾后继续分析，摘要计算仍属于该流程。

因此当前运行状态为 SOURCE_ONLY。后续运行接入需要先确定摘要规则：Owner 若为 REA 内置证据标识授予例外，可以采用上游流程；维持当前规则时，需要另行设计兼容的证据标识与完整分析流程。当前源码已原样保留，便于评估这个取舍。

## 标准使用流程

以下是上游的标准操作示例，适用于上述运行条件已经满足的环境。

### 1. 取出本仓登记的源码

```bash
cd ~/Documents/Codex/GithubProject/MetaDatabase
git pull --ff-only
git submodule update --init REA
```

此命令展开 REA 的登记版本。原生分析的额外工具按所选目标单独准备。

### 2. 接入智能体

```bash
npx rea-agents@6.3.0 setup --client codex
```

设置程序会展示配置变更计划，确认后添加本地 MCP 和配套工作流指引，并备份既有配置。完成后重启或重新连接 Codex。Claude Code 可改用 `--client claude_code`。提供方的配置另见[官方安装说明](https://github.com/morluto/rea/blob/main/docs/installation.md)。

`npx rea-agents@6.3.0` 使用上游发布的 npm 包。`REA/` 保存自有 fork 的源码；今后对 fork 的功能修改需要走源码构建与独立发布流程，才能成为运行版本。

### 3. 先做一个明确的 Electron 功能调查

给智能体的任务示例：

> 使用 REA 分析我指定的 DSH 应用目录或 app.asar，追踪模型设置从界面到配置保存的完整路径。输出入口、IPC 通道、处理器、配置字段和对应源码位置，标明静态推断与实际观察。提出与现有 Harness 状态协议兼容的实现方案。

直接使用 CLI 的上游示例：

```bash
npx -y rea-agents@6.3.0 analyze-javascript-application \
  /absolute/path/to/app.asar --json
```

目标路径应指向所选应用的 JavaScript 目录或 ASAR。完整结果可能很大，工作流先保留结果，再提取摘要或目标模块，减少反复读取和上下文成本。具体命令见[官方 CLI 指南](https://github.com/morluto/rea/blob/main/docs/cli.md)。

## 针对现有项目，价值从哪里来

| 顺序 | 场景 | 具体产出 | 价值来源 |
|---|---|---|---|
| 1 | DSH / Kimi / Harness 的安装包与已有源码之间出现行为差异 | 模型设置、流式输出、皮肤切换等功能的入口和调用链；对应的兼容修复方案 | 缩短升级后的故障定位时间，提高三端协作稳定性 |
| 2 | 有授权的业务客户端存在重复导出或数据迁移需求 | 导出入口、字段格式、可用接口与迁移适配方案 | 减少人工重复操作，把业务软件输出接入既有资料流水线 |
| 3 | 有明确需求的应用功能研究与技术服务 | 可复现的调查材料、接口适配或自有功能实现 | 按故障定位、迁移适配或交付功能收费，形成可复用服务能力 |

第一项最适合先做：现有桌面项目、配置协议和维护需求已经存在，Electron 静态分析的工具依赖也较少。已有清晰源码的问题可以直接沿源码处理；REA 的增量价值更集中在安装包与源码不一致、编译打包后的结构、跨进程调用关系等位置。

经营资料归档、投标文档编排和报价表计算继续由各自的数据与文档工具承担。REA 的贡献是理解相关软件机制并形成适配方案。

建议用一个真实故障做首次价值评估，初次调查预算限定半天。交付目标是入口、调用链、证据位置和可执行修复点。记录实际节省的人工时间、模型费用和后续维护时间，再决定持续投入。

每月净价值可以这样计算：

`实际节省工时 × 内部小时成本 − 模型费用 − 工具维护工时折价`

例如，若每月四次排查各节省两小时，则节省八小时；这只是计算示例，实际收益以首次项目记录为准。先从 Electron 场景建立收益记录，再按明确需求配置原生分析引擎。

## 成果与更新管理

分析目标采用自有或已授权的软件。公开母仓保存源码和说明；应用包、HAR、含账号信息的配置、实际分析结果等运行/业务资料按照母仓数据规则归入私有 `Private-MetaDatabase` 的 `REA` domain，临时结果走工作目录。REA 的分析在本机执行，智能体接收到的分析结果仍适用其模型服务的数据政策。

REA fork 的开发使用独立 worktree。上游同步到 fork 后，在 MetaDatabase 独立 worktree 更新 REA 子模块登记版本，通过 PR 合入；主树随后 `git pull --ff-only` 和 `git submodule update --init REA`。源码和运行时配置各按自己的发布边界管理。
