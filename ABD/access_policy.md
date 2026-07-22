# ABD Cloudflare Access 策略合同（S04/P02）

本文件是离线、拒绝优先的配置合同，不是 Cloudflare 账户、DNS、Tunnel 或 Access 已配置的证明。所有占位值只能在仓库外由明确授权的发布流程替换；本 Phase 不读取凭证，也不调用 Cloudflare API、Dashboard 或 `cloudflared`。

<!-- ABD_ACCESS_POLICY_JSON_START -->
{
  "schema_version": "1.0.0",
  "contract_id": "AC-S04-P02",
  "application": {
    "type": "SELF_HOSTED",
    "hostname": "abd.example.invalid",
    "status": "NOT_CREATED_OR_INSPECTED"
  },
  "enforcement": {
    "default_action": "DENY",
    "allow_policies": [
      {
        "action": "ALLOW",
        "include": {
          "selector": "EMAIL",
          "value": "${ABD_OWNER_EMAIL}",
          "exact_owner_count": 1
        },
        "require": {
          "mfa": true,
          "mfa_mode": "INDEPENDENT_OR_IDP_MFA_MUST_BE_VERIFIED"
        },
        "session_duration": "1h"
      }
    ],
    "forbidden_actions": [
      "BYPASS",
      "SERVICE_AUTH"
    ],
    "everyone_selector_allowed": false,
    "email_domain_wildcard_allowed": false,
    "audit_logging_required": true
  },
  "network_boundary": {
    "origin_service": "http://127.0.0.1:8080",
    "origin_business_inbound_required": false,
    "tunnel_connector_direction": "OUTBOUND_ONLY",
    "catch_all_action": "HTTP_404",
    "metrics_bind": "127.0.0.1:49312"
  },
  "activation": {
    "requested": false,
    "status": "BLOCKED_EXTERNAL_PREREQUISITES_NOT_VERIFIED",
    "prerequisites": {
      "cloudflare_account_entitlement": "NOT_INSPECTED",
      "zero_trust_organization": "NOT_INSPECTED",
      "owner_identity_and_mfa": "NOT_INSPECTED",
      "named_tunnel_and_credentials": "NOT_CREATED_OR_READ",
      "dns_hostname": "NOT_CONFIGURED_OR_INSPECTED",
      "access_application_and_policy": "NOT_CREATED_OR_INSPECTED",
      "ovh_connector_runtime": "NOT_ACCESSED_OR_EXECUTED",
      "end_to_end_access_test": "NOT_EXECUTED"
    }
  },
  "claims": {
    "ordinary_global_network_chinese_ui": "CONFIGURATION_INTENT_ONLY_NOT_RUNTIME_VERIFIED",
    "mainland_china_acceleration_availability_or_reach": "NOT_IN_ZERO_CASH_SCOPE_NO_CLAIM",
    "ovh_7x24": "UNVERIFIED_REQUIRES_RUNTIME_EVIDENCE",
    "returns": "UNVERIFIED_NOT_GUARANTEED"
  },
  "budget": {
    "incremental_cash_aud": "0.00",
    "paid_upgrade_allowed": false,
    "china_network_subscription_allowed": false,
    "automatic_overage_allowed": false
  }
}
<!-- ABD_ACCESS_POLICY_JSON_END -->

## 激活前人工核对

1. 在仓库外确认现有 Cloudflare 免费能力、账户权限、域名和 Zero Trust 组织；任何付费升级或超额都必须保持关闭。
2. 创建 Named Tunnel 后，将真实 Tunnel UUID、凭据文件与主机名只注入 OVH 上受限路径；不得提交到 Git、日志、截图或模型上下文。
3. 创建自托管 Access 应用，只允许唯一账户持有人的精确身份，并验证 MFA；禁止 `Everyone`、通配邮箱域、`Bypass` 与 `Service Auth`。
4. OVH 防火墙不得开放 ABD 业务入站端口；仅允许 `cloudflared` 所需的出站连接。实际端口、协议、DNS、Access 日志和端到端访问必须在后续显式激活合同中留证。
5. 普通 Cloudflare 全球网络上的中文页面不等于中国大陆境内加速、可用性或可达性保证。Cloudflare China Network 是 Enterprise 单独订阅且有 ICP 等前置条件，不属于 A$0 范围。

任一前置条件未知、失败、需要新增现金或无法审计时，保持入口未激活并停止新建议。
