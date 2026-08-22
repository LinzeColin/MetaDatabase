# 2026-08-23：DSH 更新持久化与统一发布

## 更新目标

更新器从当前运行 DSH Desktop 的 process.execPath 推导 App Bundle 目标。这样用户从自己的 Applications 位置启动时，更新始终替换同一份 App，不会改写另一条安装路径。

## 安全切换流程

安装桥和更新器先把候选 Bundle 放入用户目录的 staging，赋予当前用户写权限，注入 Harness UI 桥接与外置图标，再重新签名。完成后原子替换正式 Bundle，并把旧 Bundle 放入以 .rollback 结尾的回滚目录。

## 皮肤稳定性

DSH 背景层保留已显示素材 URL。相同 URL 的轮询结果不会再次预加载或重写 CSS 变量；异步加载采用 revision 保证，只有最新选择可以落地。

## 三端治理

DSH 官方安装器镜像和 Harness UI 桥接与 Kimi、Harness UI 共同受 desktop-suite/COMPATIBILITY_CONTRACT.json 约束。正式资产由 desktop-app-suite-release workflow 在同一个 GITHUB_SHA 发布。

GitHub 仓库级 Actions Workflow permissions 保持 `Read and write permissions`，使 DSH 发布 job 的最小 `contents: write` 授权能够更新正式 tag 与镜像资产；三端发布由此维持同一 commit 边界。

## 本机数据边界

DSH 配置、会话、外置图标、Harness UI 状态和素材目录留在用户目录，发布包只包含可公开的桥接源码与官方版本镜像流程。
