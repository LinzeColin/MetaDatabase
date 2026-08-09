# Requirement → Acceptance → Test → Evidence → Artifact

| Requirement / invariant | Acceptance | Test / Oracle | Evidence | Artifact |
|---|---|---|---|---|
| `USABILITY-01` 零技术门槛 | A-10 | 桌面/移动浏览器事务；生产登录；网页 Key 配置 | browser evidence + AI settings route | Templates/CSS/onboarding/settings |
| `TRUTH-01` 不猜高影响事实 | A-02,A-05,A-06 | Analyzer；未知条件→Needs user；AI 不新增事实 | pytest + job detail | analyzer/Profile/Pack |
| `SAFETY-01` 无第三方登录/自动提交 | A-04,A-06 | 无 credential 字段；Applied 要证据 | route tests + live settings | importer/status routes |
| `EVIDENCE-01` 严格投递状态 | A-06,A-07 | 无证据 Applied 被拒；有证据后重启读回 | route + HTTP/browser golden | JobEvent/status workflow |
| `DATA-01` 私有与加密 | A-01,A-03,A-08,A-09,A-11 | Auth/CSRF；SQLite、对象名、export、backup、迁移、Key 加密 | pytest + target storage gate | auth/db_types/migration/canonical/backup/models |
| `RUNTIME-01` 云端独立运行 | A-07,A-09 | Docker doctor、ready、重启、Compose restart | target acceptance | Compose/Traefik/systemd |
| `AI-AUTHORITY-01` AI 不覆盖硬规则 | A-05,A-06,A-12 | 冲突 fixture 中 suggested_action 不能改变 rule result | `tests/test_ai_provider.py` | ai_provider/analyzer/jobs |
| `AI-PRIVACY-01` 最小脱敏发送 | A-11,A-12 | 捕获 Mock 请求；姓名/邮箱/电话/链接不存在；Key 不在 body/log/export | AI tests + canonical tests | redaction gateway/provider config |
| `COST-01` 模型非单点依赖 | A-05,A-06,A-12 | 无 Key、401/402/429/500/503/超时仍完成规则路径 | AI tests + HTTP golden | deterministic analyzer + fallback |
| `NS-CANDIDATE-01` 候选人闭环 | A-02–A-08 | 资料→简历→岗位→申请包→证据→读回 | HTTP + browser golden | 完整应用 |
| DeepSeek secure BYOK | A-11 | 保存/验证/末四位/撤销；无真实 Key fixture | AI settings tests + live verification | settings + encrypted config |
| 长期同步诚实 | A-08,A-12 | 未配置显示 not_configured；Provider Key 不导出 | tests + sync output | sync scripts/UI/canonical |
| 发布可逆 | A-09 | 部署前恢复点、真实 previous image、rollback、隔离 restore | target evidence | deploy scripts |

机器可读版本：`acceptance_contract.json`。任何实现变化必须继续映射同一 Oracle，不得由当前代码反向降低 Acceptance。
