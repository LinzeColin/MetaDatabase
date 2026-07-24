# 一次性部署清单

开发应在无需真实 Secret 的前提下完成到 Beta 前 Gate，再集中执行以下步骤。

## Google OAuth

- 创建个人用途 OAuth 应用；
- 仅请求 `https://www.googleapis.com/auth/gmail.modify`；
- 完成邮箱所有者一次同意；
- Refresh Token 存 GitHub protected Environment Secret；
- 验证 Token 不在 Testing 短期失效模式；
- 运行 endpoint guard canary；
- 不授予 Drive、Contacts、Calendar 或完整 mail scope。

## GitHub App

- 只安装到唯一私有数据仓；
- 权限仅满足 Contents/Metadata 与固定 Release Asset 操作；
- App 私钥存 protected Environment Secret；
- 工作流生成短时 Installation Token；
- 验证不能访问其他仓或无关路径；
- 记录 Repository ID，名称改动不影响定位。

## age

- 在临时受保护 Runner 生成 X25519 Identity；
- Identity 写 Environment Secret；
- Public Recipient 提交公开配置；
- 生成一次性 `MooMooAU-Recovery-Key.agekey` 下载；
- 用户保存后执行随机对象恢复；
- Runner 清理明文；
- 未完成恢复不得启用 M3。

## Moomoo PDF Password

可暂时不配置。若用户以后提供最终 8 字符密码，只写 GitHub protected Secret，并通过受保护 Fixture 测试；不得保存手机号或证件号组件。

## 仓库设置

- Public Repo Actions 权限最小化；
- Production Environment 保护；
- Secrets 不向 Fork PR 暴露；
- 日志保留设为平台允许的短周期；
- Actions Cache 不用于本项目；
- 固定 live Release 创建由部署 Workflow 完成；
- Codex Automation 最后设置，且非阻塞。
