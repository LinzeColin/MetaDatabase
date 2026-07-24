# Codex Automation 最小稳定规格

## 定位

Codex Automation 不是用户入口，不是数据面，不是修复器，不是工作流编排器。用户始终回到 Codex 开发线程。

## 唯一任务

普通每日计划：`04:30 Australia/Sydney`。

Prompt 语义：

```text
Read only the latest completed public MooMooAU health evidence in the public MetaDatabase repository.
Do not access Gmail, private repositories, secrets, encrypted data, workflow inputs, or source-message content.
Do not trigger workflows and do not modify code.
If the evidence is healthy and not older than 48 hours, take no action.
If it is unhealthy or stale, create or update the single GitHub issue labeled moomooau-ops with the public evidence reference, failure code, and the development-thread repair prompt.
Do not return to or continue any existing conversation.
```

## 权限

只读公开仓证据；若平台支持 Issue 写入，可仅更新唯一 Ops Issue。不得授予 Gmail、私有仓、Actions Dispatch、Secrets 或代码写入权限。

## 故障行为

Auto 失败、停用或重复执行不影响 04:30 GitHub Actions。重复异常必须幂等更新同一 Issue，不创建 Issue 洪泛。

## 开发线程设置方式

使用 Codex 产品普通 Automation UI/自然语言设置即可；不开发自定义 SDK、Webhook、回调、线程恢复或特殊 Agent 状态机。设置和验证属于 `T0706`，不是生产上线前的阻塞依赖。
