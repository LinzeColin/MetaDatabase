# SA-507 Phase D｜生产候选部署与边缘 Smoke Run Contract

## 目标

把已经通过本开发周期唯一一次全量回归的 v0.0.0.4 候选，与现有 OVH 的
运行态做最小、可回滚的部署一致性收束，并留下不含秘密或用户数据的生产
smoke 证据。

## 候选边界

- 基线提交：`9fdf6de319d9d20be22c298c44bbef6b0f4d8320`
- 工作分支：`codex/sa-507-compat-tomllib-fix`
- 上一受控阶段已记录的唯一 application suite：`235 passed`（Phase C evidence）。
- 本阶段不得修改 `src/`、镜像构建输入或应用行为；新增的本 Contract 与最终
  evidence 不是 application-suite 候选变更。
- 本阶段不执行 Git stage/commit/tag/push/merge/Release，不创建 worktree，不启用
  replication 或 Private-Database sync timer。

## 已验证前置状态

生产根目录当前不是 Git checkout；因此候选一致性以精确 SHA-256 而非远端
commit 断言。预检已确认：

1. `compose.yaml`、`Dockerfile`、Systemd unit、恢复脚本与本地候选一致；
2. `core-api` 仅公开 `127.0.0.1:18765`，Core、Worker、CLI sidecar 健康；
3. Cloudflared 与隔离 status 服务运行，两个 loopback health probe 均为 200；
4. 仅 `scripts/install.sh` 与 `scripts/doctor.sh` 尚未包含 Private-Database/
   recovery 的当前静态合同，且两者不属于运行中的 Core 镜像输入差异。

## 最小变更与回滚

仅原子替换生产机的下列两个非秘密脚本：

- `scripts/install.sh`
- `scripts/doctor.sh`

替换前，root 在受限的 Social Archive 备份目录创建唯一备份并记录源/备份
SHA-256。传输先落入 root-only 临时 staging 文件，校验 SHA-256 后再 install；
任一校验、静态预检或 smoke 失败，立刻从该备份恢复这两个精确文件，停止
本阶段。不会复制 `.env`、`runtime/`、任何 Secret、SQLite、CAS 或用户内容。

不重建或重启 Docker：当前 Core 镜像的 compose/Dockerfile 输入与候选相同，
且本次静态脚本变更不会影响已运行容器。若发现这一前提不成立，停止而不是
临时扩大部署范围。

## 验证命令与通过条件

1. 生产端 `doctor.sh --self-test`、`install.sh --dry-run`、
   `prepare_systemd_host.sh --dry-run` 均 PASS；三者不得创建 runtime、配对码、
   Docker 网络或外部请求。
2. 生产 loopback Core health 与 status health 均 HTTP 200；Core bind 仍只显示
   loopback published port，replication 与 Private-Database sync timer 仍 disabled。
3. 无 Cookie、无 Bearer、无 Access assertion 的公网只读 probes：
   - private UI health 被 Access 阻断（302 或 401/403，绝不把未登录 UI 当作 200）；
   - extension API health 为 200，`GET /v1/status` 为 401，且不发生交互式登录跳转；
   - status projection health 和 JSON 路由均为 200。
4. UI 已登录的正向 Access assertion 与 Chrome/Owner pairing 不在本 phase 伪造；
   若没有不暴露凭据的真实观测，只能明确写为 `NOT_RUN`，不能以静态或伪 Header
   替代。

## 停止条件

出现秘密值/路径泄露、非 loopback Core 端口、UI 未登录可访问、API 遭 Access
交互跳转、无 Bearer 的业务路由非 401、状态投影失败、生产 SHA 漂移、任何
预检失败，或需要超出上述两个脚本的改动时，立即恢复精确备份（若已替换）并
停止。本 run 结束后不进入源码发布与本机资源清理；二者属于下一独立 phase。
