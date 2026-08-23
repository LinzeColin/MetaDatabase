# 2026-08-23：Harness UI 素材恢复与原生 GUI 验收

## 根因

旧 GUI helper 与后台 `3099` 服务来自不同构建。后台服务能读取本地 catalog，却没有当前 GUI helper 的 macOS SMB 授权上下文，因此刷新收敛到本地旧目录，状态长期停在 `partial`，SMB 计数为 0。浏览器素材页和旧 helper 继续存活时，用户看到的刷新按钮也无法触发完整 SMB 部署。

## 正确恢复路径

1. 安装统一 Release 的 Harness UI `1.0.0`，让 App 内 `HarnessSMBMounter`、原生窗口和 `3099` 服务使用同一份实现。
2. GUI helper 持有 SMB mount 能力，后台服务负责 catalog/state/API；刷新由 `sourceOwner=harness-app` 完成。
3. 素材同步以 SMB 为源、`~/.harness-ui` 为本机运行副本，业务目录变化后再发布 catalog generation。
4. 完整素材库由 Harness UI 独立原生窗口显示，Kimi 和 DSH 菜单只负责聚焦同一窗口。

## 本机验收记录

- 完整刷新结果：SMB `408`、本机 `408`、catalog `408`、缺失 `0`，状态 `ready`。
- 原生完整素材库显示 `408 / 408`，并展示三端当前共享皮肤。
- 原生窗口 `Cmd+R` 刷新、`Cmd+W` 关闭窗口并保留服务、`Cmd+Q` 退出 GUI helper 并保留 `3099` 后台服务。
- `~/.harness-ui` 已形成一份本机完整快照，并从该静态快照复制到 SMB 备份目录。
- SMB 会自动生成 Finder 的 `._*` 元数据；备份核对聚焦真实业务文件，并排除 `.DS_Store` 与 `._*`，避免 Finder 元数据影响一致性判断。

## 持续规则

- `3099` 负责共享状态，`3100` 负责原生 GUI；二者版本随同一 Harness UI Bundle 发布。
- 刷新回执必须同时报告 SMB、本机、catalog、缺失数和 source owner。
- 备份顺序固定为“运行目录到本机静态快照，再从静态快照到 SMB”，让运行服务与跨设备备份互不争用。
- 正式安装路径只保留一个 Harness UI，完整素材库持续使用原生 GUI。
