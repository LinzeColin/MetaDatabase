# Stop / Kill / Incident Register

`STOP` 阻止当前动作；`KILL_PLATFORM` 关闭单平台 Feature Flag；`KILL_GLOBAL` 停止所有采集/下载/外发；`INCIDENT` 还需隔离与处置。自动恢复只能发生在登记的可逆条件满足后。

| ID | 触发条件 | 动作 | 恢复条件 |
|---|---|---|---|
| SK-X2N-001 | CAPTCHA、验证码、设备验证或访问控制 | `STOP + KILL_PLATFORM` | Owner 手工恢复且 Health Check 通过；不绕过 |
| SK-X2N-002 | 429/平台限流或异常访问提示 | `STOP + KILL_PLATFORM` | 遵守 Retry-After，Owner 下次显式启动；不切代理 |
| SK-X2N-003 | Auth 过期/权限 Scope 缺失 | `STOP + KILL_PLATFORM` | Owner 重新授权；不得导出 Cookie |
| SK-X2N-004 | DOM/API/Schema Drift 或稳定 ID 不可证 | `STOP + KILL_PLATFORM` | 新 Fixture＋Contract Tests＋独立复核通过 |
| SK-X2N-005 | 当时有效政策/协议/接口授权未知 | `STOP + KILL_PLATFORM` | 一手证据登记并通过 Policy Gate |
| SK-X2N-006 | License 未知、不兼容或 Provenance 不清 | `STOP + KILL_GLOBAL` | 权利核验/书面授权/替换依赖＋SBOM 复核 |
| SK-X2N-007 | 自动滚动、账号状态变化、代理/指纹/绕过成为必要条件 | `STOP + KILL_PLATFORM` | 产品设计改变前不恢复；需 Owner 新 PRD |
| SK-X2N-008 | Secret/Cookie/Profile/私有正文泄漏 | `INCIDENT + KILL_GLOBAL` | 隔离、轮换、范围调查、清理证明、Owner 复核 |
| SK-X2N-009 | 平台 CDN URL 或原始媒体进入持久层/Artifact | `INCIDENT + KILL_GLOBAL` | 隔离/删除、Scanner 根因修复、全 Scope 零命中 |
| SK-X2N-010 | SSRF、私网/metadata 命中、Redirect/DNS rebinding | `INCIDENT + KILL_GLOBAL` | 网络隔离、规则修复、全部恶意 URL 用例通过 |
| SK-X2N-011 | Path traversal、任意路径/命令执行尝试 | `INCIDENT + KILL_GLOBAL` | 权限/契约修复、Fuzz 100% 拒绝 |
| SK-X2N-012 | 完整性 Receipt 缺失、空响应或不完整扫描 | `STOP` | 保留历史；成功完整重试和差异复核 |
| SK-X2N-013 | DB integrity、Migration、Backup/Restore 或幂等失败 | `KILL_GLOBAL` | 从已验证备份恢复并重跑数据门禁 |
| SK-X2N-014 | Temp Lease 超时未清理、资源预算超限、Parser hang | `KILL_GLOBAL` | 清理/隔离完成；Chaos/Resource Tests 通过 |
| SK-X2N-015 | Prompt Injection 影响分类/配置/工具 | `KILL_GLOBAL` | 模型隔离与 Red Team 全通过；人工复核受影响记录 |
| SK-X2N-016 | Notion 429/529/断网/权限不足 | `STOP_SINK_ONLY` | Canonical/Markdown 继续；Outbox 按 Retry-After/reconcile |
| SK-X2N-017 | AI 尝试创建/改名/删除一级分类 | `STOP_CLASSIFIER` | 恢复 Owner Registry；权限与回归 Gate 通过 |
| SK-X2N-018 | Changed scope 逃出子项目或 Main Worktree 变脏 | `STOP` | 撤销越界变化；Main 恢复 clean/main |
| SK-X2N-019 | Phase 中间 push 或 Stage Gate 未通过拟上传 | `STOP` | 完成独立全 Stage Review/Fix/Re-acceptance |
| SK-X2N-020 | 真实账号/媒体/Notion/模型在未授权 Phase 被触发 | `INCIDENT + KILL_GLOBAL` | 停止外部动作、核查副作用、Owner 新授权与对应 Gate |

所有事件最少记录：`event_id/run_id/platform/trigger/source_phase/observed_at/action/state_before/state_after/evidence_refs/redaction/owner_action_required/recovery_gate`。禁止在事件证据中保存 Secret、Cookie、原始媒体、平台 CDN URL 或真实本地绝对路径。
