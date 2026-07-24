# 机器可执行 Task Graph（人类视图）

权威源：`machine/contracts/task_graph.json`。

Stage 0 使用 `machine/contracts/stage_acceptance_contract.json` 的 S0AC-* 作为局部完成门；
原 AC-* 继续承担最终追踪，并在其所属实现阶段及最终复审中强制通过。

## S0 — 产品契约与开发入口冻结

### P0.1 — 导入与事实冻结

#### T0001 — 读取任务包并建立实现分支

- 目标：导入 PACKAGE_MANIFEST、Canonical Facts、非目标和追踪矩阵；不改真实数据。
- 依赖：无
- Acceptance：AC-008, AC-009, AC-034
- Stage Acceptance：S0AC-001（已完成）
- 测试：`python -m pytest -q tests/tasks/test_t0001.py && python machine/tools/validate_evidence.py evidence/tasks/T0001.json`
- 证据：evidence/tasks/T0001.json
- 回滚：关闭本任务相关 Feature Flag，恢复上一已验证 Commit/Digest；Raw 永不覆盖。
- Stop：出现不可逆风险; 需要超出冻结范围的权限; 验收 Oracle 无法执行; 公开面出现敏感数据

#### T0002 — 建立不变量漂移检查

- 目标：将 04:30、单一私有仓、消息级 M3、单 Timeline 等写成机器检查。
- 依赖：T0001
- Acceptance：AC-006, AC-009, AC-023, AC-028
- Stage Acceptance：S0AC-002（已完成）
- 测试：`python -m pytest -q tests/tasks/test_t0002.py && python machine/tools/validate_evidence.py evidence/tasks/T0002.json`
- 证据：evidence/tasks/T0002.json
- 回滚：关闭本任务相关 Feature Flag，恢复上一已验证 Commit/Digest；Raw 永不覆盖。
- Stop：出现不可逆风险; 需要超出冻结范围的权限; 验收 Oracle 无法执行; 公开面出现敏感数据

### P0.2 — Baseline 与证伪计划

#### T0003 — 建立合成与脱敏基线

- 目标：记录当前自动化为 0、真实样本形态和 octet-stream PDF 事实。
- 依赖：T0002
- Acceptance：AC-003, AC-014, AC-031
- Stage Acceptance：S0AC-003（已完成）
- 测试：`python -m pytest -q tests/tasks/test_t0003.py && python machine/tools/validate_evidence.py evidence/tasks/T0003.json`
- 证据：evidence/tasks/T0003.json
- 回滚：关闭本任务相关 Feature Flag，恢复上一已验证 Commit/Digest；Raw 永不覆盖。
- Stop：出现不可逆风险; 需要超出冻结范围的权限; 验收 Oracle 无法执行; 公开面出现敏感数据

#### T0004 — 冻结收益成本与 Kill Criteria

- 目标：把收益区间、维护成本、容量和停止条件写入 machine facts。
- 依赖：T0003
- Acceptance：AC-031, AC-032, AC-034
- Stage Acceptance：S0AC-004（已完成）
- 测试：`python -m pytest -q tests/tasks/test_t0004.py && python machine/tools/validate_evidence.py evidence/tasks/T0004.json`
- 证据：evidence/tasks/T0004.json
- 回滚：关闭本任务相关 Feature Flag，恢复上一已验证 Commit/Digest；Raw 永不覆盖。
- Stop：出现不可逆风险; 需要超出冻结范围的权限; 验收 Oracle 无法执行; 公开面出现敏感数据

### P0.3 — 治理与双平面

#### T0005 — 接入现有 MetaDatabase 双平面治理

- 目标：遵循仓库现行 Governance，不复制或重建额外治理系统。
- 依赖：T0004
- Acceptance：AC-008
- Stage Acceptance：S0AC-005（已完成）
- 测试：`python -m pytest -q tests/tasks/test_t0005.py && python machine/tools/validate_evidence.py evidence/tasks/T0005.json`
- 证据：evidence/tasks/T0005.json
- 回滚：关闭本任务相关 Feature Flag，恢复上一已验证 Commit/Digest；Raw 永不覆盖。
- Stop：出现不可逆风险; 需要超出冻结范围的权限; 验收 Oracle 无法执行; 公开面出现敏感数据

#### T0006 — 验证七文件和机器事实一致

- 目标：生成并校验双平面七文件、预算、中文和事实一致性。
- 依赖：T0005
- Acceptance：AC-008, AC-031
- Stage Acceptance：S0AC-006（已完成）
- 测试：`python -m pytest -q tests/tasks/test_t0006.py && python machine/tools/validate_evidence.py evidence/tasks/T0006.json`
- 证据：evidence/tasks/T0006.json
- 回滚：关闭本任务相关 Feature Flag，恢复上一已验证 Commit/Digest；Raw 永不覆盖。
- Stop：出现不可逆风险; 需要超出冻结范围的权限; 验收 Oracle 无法执行; 公开面出现敏感数据

### P0.4 — 一次性人类动作前置

#### T0007 — 生成一次性部署清单

- 目标：将 Gmail OAuth、GitHub App、Environment Secret、Recovery Key 下载集中到部署前。
- 依赖：T0006
- Acceptance：AC-012, AC-018, AC-019
- Stage Acceptance：S0AC-007（已完成）
- 测试：`python -m pytest -q tests/tasks/test_t0007.py && python machine/tools/validate_evidence.py evidence/tasks/T0007.json`
- 证据：evidence/tasks/T0007.json
- 回滚：关闭本任务相关 Feature Flag，恢复上一已验证 Commit/Digest；Raw 永不覆盖。
- Stop：出现不可逆风险; 需要超出冻结范围的权限; 验收 Oracle 无法执行; 公开面出现敏感数据

## S1 — Walking Skeleton 与公共代码骨架

### P1.1 — 项目骨架

#### T0101 — 创建公开项目目录和包结构

- 目标：创建 src/tests/schemas/inventory/evidence/machine/文档，私有仓不放代码。
- 依赖：T0007
- Acceptance：AC-008, AC-009
- 测试：`python -m pytest -q tests/tasks/test_t0101.py && python machine/tools/validate_evidence.py evidence/tasks/T0101.json`
- 证据：evidence/tasks/T0101.json
- 回滚：关闭本任务相关 Feature Flag，恢复上一已验证 Commit/Digest；Raw 永不覆盖。
- Stop：出现不可逆风险; 需要超出冻结范围的权限; 验收 Oracle 无法执行; 公开面出现敏感数据

#### T0102 — 创建 CLI 与纯函数边界

- 目标：提供 discover、classify、archive、process、timeline、m3、reconcile 子命令，仅供 Actions。
- 依赖：T0101
- Acceptance：AC-010, AC-034
- 测试：`python -m pytest -q tests/tasks/test_t0102.py && python machine/tools/validate_evidence.py evidence/tasks/T0102.json`
- 证据：evidence/tasks/T0102.json
- 回滚：关闭本任务相关 Feature Flag，恢复上一已验证 Commit/Digest；Raw 永不覆盖。
- Stop：出现不可逆风险; 需要超出冻结范围的权限; 验收 Oracle 无法执行; 公开面出现敏感数据

### P1.2 — 合成 Gmail Walking Skeleton

#### T0103 — 建立 RFC EML 与附件 Fixture 工厂

- 目标：生成 MIME、RAW、internalDate、标签、认证和恶意样本。
- 依赖：T0102
- Acceptance：AC-013, AC-014, AC-020
- 测试：`python -m pytest -q tests/tasks/test_t0103.py && python machine/tools/validate_evidence.py evidence/tasks/T0103.json`
- 证据：evidence/tasks/T0103.json
- 回滚：关闭本任务相关 Feature Flag，恢复上一已验证 Commit/Digest；Raw 永不覆盖。
- Stop：出现不可逆风险; 需要超出冻结范围的权限; 验收 Oracle 无法执行; 公开面出现敏感数据

#### T0104 — 完成内存端到端 Skeleton

- 目标：合成 RAW → 验证 → age → 私有测试远端 → 恢复 → 公开 Evidence。
- 依赖：T0103
- Acceptance：AC-011, AC-013, AC-027, AC-031
- 测试：`python -m pytest -q tests/tasks/test_t0104.py && python machine/tools/validate_evidence.py evidence/tasks/T0104.json`
- 证据：evidence/tasks/T0104.json
- 回滚：关闭本任务相关 Feature Flag，恢复上一已验证 Commit/Digest；Raw 永不覆盖。
- Stop：出现不可逆风险; 需要超出冻结范围的权限; 验收 Oracle 无法执行; 公开面出现敏感数据

### P1.3 — Schema 与验证器

#### T0105 — 实现 JSON Schema 与 Pandera 契约

- 目标：实现 Message、Document、Transaction、Timeline、Lineage、Evidence 契约。
- 依赖：T0104
- Acceptance：AC-015, AC-029, AC-031
- 测试：`python -m pytest -q tests/tasks/test_t0105.py && python machine/tools/validate_evidence.py evidence/tasks/T0105.json`
- 证据：evidence/tasks/T0105.json
- 回滚：关闭本任务相关 Feature Flag，恢复上一已验证 Commit/Digest；Raw 永不覆盖。
- Stop：出现不可逆风险; 需要超出冻结范围的权限; 验收 Oracle 无法执行; 公开面出现敏感数据

#### T0106 — 实现任务包和仓库验证器

- 目标：检查需求唯一、AC 唯一、DAG 无环、追踪完整和禁止项。
- 依赖：T0105
- Acceptance：AC-008, AC-034
- 测试：`python -m pytest -q tests/tasks/test_t0106.py && python machine/tools/validate_evidence.py evidence/tasks/T0106.json`
- 证据：evidence/tasks/T0106.json
- 回滚：关闭本任务相关 Feature Flag，恢复上一已验证 Commit/Digest；Raw 永不覆盖。
- Stop：出现不可逆风险; 需要超出冻结范围的权限; 验收 Oracle 无法执行; 公开面出现敏感数据

### P1.4 — 基础 CI

#### T0107 — 建立无 Secret 公共 CI

- 目标：Lint、type、unit、schema、package、dual-plane、secret scan。
- 依赖：T0106
- Acceptance：AC-021, AC-033
- 测试：`python -m pytest -q tests/tasks/test_t0107.py && python machine/tools/validate_evidence.py evidence/tasks/T0107.json`
- 证据：evidence/tasks/T0107.json
- 回滚：关闭本任务相关 Feature Flag，恢复上一已验证 Commit/Digest；Raw 永不覆盖。
- Stop：出现不可逆风险; 需要超出冻结范围的权限; 验收 Oracle 无法执行; 公开面出现敏感数据

## S2 — 身份、加密与供应链

### P2.1 — Gmail OAuth 和端点守卫

#### T0201 — 实现单 OAuth 凭证加载

- 目标：使用受保护 Secret 和 gmail.modify，日志永不输出 Token。
- 依赖：T0107
- Acceptance：AC-018, AC-022
- 测试：`python -m pytest -q tests/tasks/test_t0201.py && python machine/tools/validate_evidence.py evidence/tasks/T0201.json`
- 证据：evidence/tasks/T0201.json
- 回滚：关闭本任务相关 Feature Flag，恢复上一已验证 Commit/Digest；Raw 永不覆盖。
- Stop：出现不可逆风险; 需要超出冻结范围的权限; 验收 Oracle 无法执行; 公开面出现敏感数据

#### T0202 — 实现 Gmail Endpoint Guard

- 目标：只允许 messages.list/get、history.list、filters.list、messages.trash。
- 依赖：T0201
- Acceptance：AC-006, AC-018, AC-034
- 测试：`python -m pytest -q tests/tasks/test_t0202.py && python machine/tools/validate_evidence.py evidence/tasks/T0202.json`
- 证据：evidence/tasks/T0202.json
- 回滚：关闭本任务相关 Feature Flag，恢复上一已验证 Commit/Digest；Raw 永不覆盖。
- Stop：出现不可逆风险; 需要超出冻结范围的权限; 验收 Oracle 无法执行; 公开面出现敏感数据

### P2.2 — GitHub App 私有仓访问

#### T0203 — 实现 Repository ID 解析与改名兼容

- 目标：基于目标 Repository ID 解析当前名称并锁定 MooMooAU 命名空间。
- 依赖：T0202
- Acceptance：AC-009, AC-019
- 测试：`python -m pytest -q tests/tasks/test_t0203.py && python machine/tools/validate_evidence.py evidence/tasks/T0203.json`
- 证据：evidence/tasks/T0203.json
- 回滚：关闭本任务相关 Feature Flag，恢复上一已验证 Commit/Digest；Raw 永不覆盖。
- Stop：出现不可逆风险; 需要超出冻结范围的权限; 验收 Oracle 无法执行; 公开面出现敏感数据

#### T0204 — 实现短时 Installation Token 客户端

- 目标：限制目标私有仓 Contents/Release 权限与网络目的地。
- 依赖：T0203
- Acceptance：AC-019, AC-027
- 测试：`python -m pytest -q tests/tasks/test_t0204.py && python machine/tools/validate_evidence.py evidence/tasks/T0204.json`
- 证据：evidence/tasks/T0204.json
- 回滚：关闭本任务相关 Feature Flag，恢复上一已验证 Commit/Digest；Raw 永不覆盖。
- Stop：出现不可逆风险; 需要超出冻结范围的权限; 验收 Oracle 无法执行; 公开面出现敏感数据

### P2.3 — age 与恢复钥匙

#### T0205 — 实现流式 age 加密接口

- 目标：所有敏感对象在进入持久层前加密，临时明文仅内存/tmpfs。
- 依赖：T0204
- Acceptance：AC-010, AC-011, AC-022
- 测试：`python -m pytest -q tests/tasks/test_t0205.py && python machine/tools/validate_evidence.py evidence/tasks/T0205.json`
- 证据：evidence/tasks/T0205.json
- 回滚：关闭本任务相关 Feature Flag，恢复上一已验证 Commit/Digest；Raw 永不覆盖。
- Stop：出现不可逆风险; 需要超出冻结范围的权限; 验收 Oracle 无法执行; 公开面出现敏感数据

#### T0206 — 实现部署时 Recovery Key 交付流程

- 目标：临时生成 identity、Secret 注入、公开 Recipient、一次性下载，不生成在任务包中。
- 依赖：T0205
- Acceptance：AC-012
- 测试：`python -m pytest -q tests/tasks/test_t0206.py && python machine/tools/validate_evidence.py evidence/tasks/T0206.json`
- 证据：evidence/tasks/T0206.json
- 回滚：关闭本任务相关 Feature Flag，恢复上一已验证 Commit/Digest；Raw 永不覆盖。
- Stop：出现不可逆风险; 需要超出冻结范围的权限; 验收 Oracle 无法执行; 公开面出现敏感数据

### P2.4 — 供应链锁定

#### T0207 — 固定依赖、Action SHA 与容器 Digest

- 目标：生成锁文件、SBOM、CodeQL、依赖和 Secret 扫描。
- 依赖：T0206
- Acceptance：AC-021, AC-033
- 测试：`python -m pytest -q tests/tasks/test_t0207.py && python machine/tools/validate_evidence.py evidence/tasks/T0207.json`
- 证据：evidence/tasks/T0207.json
- 回滚：关闭本任务相关 Feature Flag，恢复上一已验证 Commit/Digest；Raw 永不覆盖。
- Stop：出现不可逆风险; 需要超出冻结范围的权限; 验收 Oracle 无法执行; 公开面出现敏感数据

## S3 — Gmail 发现、验证与 Canonical Raw

### P3.1 — 候选发现

#### T0301 — 实现全标签消息级发现

- 目标：includeSpamTrash=true，分页覆盖 All Mail/Inbox/Spam/Trash。
- 依赖：T0207
- Acceptance：AC-003, AC-025
- 测试：`python -m pytest -q tests/tasks/test_t0301.py && python machine/tools/validate_evidence.py evidence/tasks/T0301.json`
- 证据：evidence/tasks/T0301.json
- 回滚：关闭本任务相关 Feature Flag，恢复上一已验证 Commit/Digest；Raw 永不覆盖。
- Stop：出现不可逆风险; 需要超出冻结范围的权限; 验收 Oracle 无法执行; 公开面出现敏感数据

#### T0302 — 实现 History 增量与 Full Reconciliation

- 目标：水位失效、404、周日和差异时回退全量。
- 依赖：T0301
- Acceptance：AC-023, AC-025, AC-026
- 测试：`python -m pytest -q tests/tasks/test_t0302.py && python machine/tools/validate_evidence.py evidence/tasks/T0302.json`
- 证据：evidence/tasks/T0302.json
- 回滚：关闭本任务相关 Feature Flag，恢复上一已验证 Commit/Digest；Raw 永不覆盖。
- Stop：出现不可逆风险; 需要超出冻结范围的权限; 验收 Oracle 无法执行; 公开面出现敏感数据

### P3.2 — 发件人注册表与验证

#### T0303 — 建立版本化 verified sender 注册表

- 目标：注册表初始只允许经一手证据确认的 Moomoo AU 官方地址；未证实候选保持 UNKNOWN，不进入 verified set；第三方需精确规则。
- 依赖：T0302
- Acceptance：AC-004, AC-005
- 测试：`python -m pytest -q tests/tasks/test_t0303.py && python machine/tools/validate_evidence.py evidence/tasks/T0303.json`
- 证据：evidence/tasks/T0303.json
- 回滚：关闭本任务相关 Feature Flag，恢复上一已验证 Commit/Digest；Raw 永不覆盖。
- Stop：出现不可逆风险; 需要超出冻结范围的权限; 验收 Oracle 无法执行; 公开面出现敏感数据

#### T0304 — 实现双重分类验证器

- 目标：完整 Raw 前和 M3 前分别验证 sender、认证对齐和业务指纹。
- 依赖：T0303
- Acceptance：AC-001, AC-004, AC-005
- 测试：`python -m pytest -q tests/tasks/test_t0304.py && python machine/tools/validate_evidence.py evidence/tasks/T0304.json`
- 证据：evidence/tasks/T0304.json
- 回滚：关闭本任务相关 Feature Flag，恢复上一已验证 Commit/Digest；Raw 永不覆盖。
- Stop：出现不可逆风险; 需要超出冻结范围的权限; 验收 Oracle 无法执行; 公开面出现敏感数据

### P3.3 — Canonical Raw 与附件

#### T0305 — 获取并保存 Gmail RAW EML

- 目标：Base64url 解码后字节哈希，完整 RFC 2822 为 Canonical。
- 依赖：T0304
- Acceptance：AC-013
- 测试：`python -m pytest -q tests/tasks/test_t0305.py && python machine/tools/validate_evidence.py evidence/tasks/T0305.json`
- 证据：evidence/tasks/T0305.json
- 回滚：关闭本任务相关 Feature Flag，恢复上一已验证 Commit/Digest；Raw 永不覆盖。
- Stop：出现不可逆风险; 需要超出冻结范围的权限; 验收 Oracle 无法执行; 公开面出现敏感数据

#### T0306 — 实现附件安全识别和隔离

- 目标：Magic Bytes、大小、超时、嵌套和恶意格式限制。
- 依赖：T0305
- Acceptance：AC-014, AC-020
- 测试：`python -m pytest -q tests/tasks/test_t0306.py && python machine/tools/validate_evidence.py evidence/tasks/T0306.json`
- 证据：evidence/tasks/T0306.json
- 回滚：关闭本任务相关 Feature Flag，恢复上一已验证 Commit/Digest；Raw 永不覆盖。
- Stop：出现不可逆风险; 需要超出冻结范围的权限; 验收 Oracle 无法执行; 公开面出现敏感数据

### P3.4 — Raw 私有提交

#### T0307 — 实现内容寻址与幂等 Raw Commit

- 目标：Raw append-only、附件对象去重、私有优先 Saga。
- 依赖：T0306
- Acceptance：AC-011, AC-026, AC-027
- 测试：`python -m pytest -q tests/tasks/test_t0307.py && python machine/tools/validate_evidence.py evidence/tasks/T0307.json`
- 证据：evidence/tasks/T0307.json
- 回滚：关闭本任务相关 Feature Flag，恢复上一已验证 Commit/Digest；Raw 永不覆盖。
- Stop：出现不可逆风险; 需要超出冻结范围的权限; 验收 Oracle 无法执行; 公开面出现敏感数据

## S4 — Processed 数据产品与公开契约

### P4.1 — 文档分类和通用信封

#### T0401 — 实现所有 Moomoo 邮件类型分类

- 目标：覆盖报表、交易、资金、税务、安全、KYC、客服、营销和 VERIFIED_UNKNOWN。
- 依赖：T0307
- Acceptance：AC-002
- 测试：`python -m pytest -q tests/tasks/test_t0401.py && python machine/tools/validate_evidence.py evidence/tasks/T0401.json`
- 证据：evidence/tasks/T0401.json
- 回滚：关闭本任务相关 Feature Flag，恢复上一已验证 Commit/Digest；Raw 永不覆盖。
- Stop：出现不可逆风险; 需要超出冻结范围的权限; 验收 Oracle 无法执行; 公开面出现敏感数据

#### T0402 — 实现统一 Document Envelope

- 目标：保留来源、分类、标签、时间、附件、认证和处理状态。
- 依赖：T0401
- Acceptance：AC-015, AC-029
- 测试：`python -m pytest -q tests/tasks/test_t0402.py && python machine/tools/validate_evidence.py evidence/tasks/T0402.json`
- 证据：evidence/tasks/T0402.json
- 回滚：关闭本任务相关 Feature Flag，恢复上一已验证 Commit/Digest；Raw 永不覆盖。
- Stop：出现不可逆风险; 需要超出冻结范围的权限; 验收 Oracle 无法执行; 公开面出现敏感数据

### P4.2 — 报表 Parser

#### T0403 — 实现 Daily/Monthly/Contract Note Parser

- 目标：先 Golden Fixture，再受保护 Canary，字段冲突不猜测。
- 依赖：T0402
- Acceptance：AC-014, AC-015, AC-029
- 测试：`python -m pytest -q tests/tasks/test_t0403.py && python machine/tools/validate_evidence.py evidence/tasks/T0403.json`
- 证据：evidence/tasks/T0403.json
- 回滚：关闭本任务相关 Feature Flag，恢复上一已验证 Commit/Digest；Raw 永不覆盖。
- Stop：出现不可逆风险; 需要超出冻结范围的权限; 验收 Oracle 无法执行; 公开面出现敏感数据

#### T0404 — 实现 FY Summary 与通用表格 Parser

- 目标：只处理邮件中实际附件，不访问 Moomoo Portal。
- 依赖：T0403
- Acceptance：AC-015, AC-034
- 测试：`python -m pytest -q tests/tasks/test_t0404.py && python machine/tools/validate_evidence.py evidence/tasks/T0404.json`
- 证据：evidence/tasks/T0404.json
- 回滚：关闭本任务相关 Feature Flag，恢复上一已验证 Commit/Digest；Raw 永不覆盖。
- Stop：出现不可逆风险; 需要超出冻结范围的权限; 验收 Oracle 无法执行; 公开面出现敏感数据

### P4.3 — 密码延迟与重处理

#### T0405 — 实现 WAITING_FOR_PDF_PASSWORD 状态

- 目标：密码缺失不阻塞 Raw/M3，正确 Secret 后受保护重处理。
- 依赖：T0404
- Acceptance：AC-017
- 测试：`python -m pytest -q tests/tasks/test_t0405.py && python machine/tools/validate_evidence.py evidence/tasks/T0405.json`
- 证据：evidence/tasks/T0405.json
- 回滚：关闭本任务相关 Feature Flag，恢复上一已验证 Commit/Digest；Raw 永不覆盖。
- Stop：出现不可逆风险; 需要超出冻结范围的权限; 验收 Oracle 无法执行; 公开面出现敏感数据

#### T0406 — 实现 Parser Blue-Green 和 current 指针

- 目标：新版本并行对比，旧 Processed 不覆盖。
- 依赖：T0405
- Acceptance：AC-015, AC-032
- 测试：`python -m pytest -q tests/tasks/test_t0406.py && python machine/tools/validate_evidence.py evidence/tasks/T0406.json`
- 证据：evidence/tasks/T0406.json
- 回滚：关闭本任务相关 Feature Flag，恢复上一已验证 Commit/Digest；Raw 永不覆盖。
- Stop：出现不可逆风险; 需要超出冻结范围的权限; 验收 Oracle 无法执行; 公开面出现敏感数据

### P4.4 — 公开 Inventory/Schema/Evidence

#### T0407 — 实现严格公开脱敏发布器

- 目标：只发布桶化状态、版本和 Opaque Root。
- 依赖：T0406
- Acceptance：AC-016, AC-031
- 测试：`python -m pytest -q tests/tasks/test_t0407.py && python machine/tools/validate_evidence.py evidence/tasks/T0407.json`
- 证据：evidence/tasks/T0407.json
- 回滚：关闭本任务相关 Feature Flag，恢复上一已验证 Commit/Digest；Raw 永不覆盖。
- Stop：出现不可逆风险; 需要超出冻结范围的权限; 验收 Oracle 无法执行; 公开面出现敏感数据

## S5 — M3 与最新 Timeline

### P5.1 — M3 Gate 和消息级变更

#### T0501 — 实现远端重取解密校验 Gate

- 目标：密文远端存在、解密 Raw SHA 一致、Processed 完成或显式延迟。
- 依赖：T0407
- Acceptance：AC-007, AC-017, AC-027
- 测试：`python -m pytest -q tests/tasks/test_t0501.py && python machine/tools/validate_evidence.py evidence/tasks/T0501.json`
- 证据：evidence/tasks/T0501.json
- 回滚：关闭本任务相关 Feature Flag，恢复上一已验证 Commit/Digest；Raw 永不覆盖。
- Stop：出现不可逆风险; 需要超出冻结范围的权限; 验收 Oracle 无法执行; 公开面出现敏感数据

#### T0502 — 实现精确 messages.trash 与确认

- 目标：二次验证、Mutation Budget、Trash 标签确认、已在 Trash 幂等。
- 依赖：T0501
- Acceptance：AC-002, AC-006, AC-026
- 测试：`python -m pytest -q tests/tasks/test_t0502.py && python machine/tools/validate_evidence.py evidence/tasks/T0502.json`
- 证据：evidence/tasks/T0502.json
- 回滚：关闭本任务相关 Feature Flag，恢复上一已验证 Commit/Digest；Raw 永不覆盖。
- Stop：出现不可逆风险; 需要超出冻结范围的权限; 验收 Oracle 无法执行; 公开面出现敏感数据

### P5.2 — Timeline 事实模型

#### T0503 — 实现 Timeline Event 生成

- 目标：internalDate UTC、Sydney 展示、报表日期、标签和 M3 生命周期。
- 依赖：T0502
- Acceptance：AC-029, AC-030
- 测试：`python -m pytest -q tests/tasks/test_t0503.py && python machine/tools/validate_evidence.py evidence/tasks/T0503.json`
- 证据：evidence/tasks/T0503.json
- 回滚：关闭本任务相关 Feature Flag，恢复上一已验证 Commit/Digest；Raw 永不覆盖。
- Stop：出现不可逆风险; 需要超出冻结范围的权限; 验收 Oracle 无法执行; 公开面出现敏感数据

#### T0504 — 实现美国市场交易日延迟

- 目标：周末、休市和未知预期安全处理。
- 依赖：T0503
- Acceptance：AC-029, AC-030
- 测试：`python -m pytest -q tests/tasks/test_t0504.py && python machine/tools/validate_evidence.py evidence/tasks/T0504.json`
- 证据：evidence/tasks/T0504.json
- 回滚：关闭本任务相关 Feature Flag，恢复上一已验证 Commit/Digest；Raw 永不覆盖。
- Stop：出现不可逆风险; 需要超出冻结范围的权限; 验收 Oracle 无法执行; 公开面出现敏感数据

### P5.3 — 单一 Timeline 渲染和替换

#### T0505 — 实现确定性 Timeline PNG

- 目标：固定容器/字体/排序，输入 Root 不变时不重绘。
- 依赖：T0504
- Acceptance：AC-028, AC-029
- 测试：`python -m pytest -q tests/tasks/test_t0505.py && python machine/tools/validate_evidence.py evidence/tasks/T0505.json`
- 证据：evidence/tasks/T0505.json
- 回滚：关闭本任务相关 Feature Flag，恢复上一已验证 Commit/Digest；Raw 永不覆盖。
- Stop：出现不可逆风险; 需要超出冻结范围的权限; 验收 Oracle 无法执行; 公开面出现敏感数据

#### T0506 — 实现 live Release Asset 串行替换与确定性修复

- 目标：只保留 timeline-latest.png.age，不写 Git、不留 Artifact/Cache。
- 依赖：T0505
- Acceptance：AC-011, AC-022, AC-028
- 测试：`python -m pytest -q tests/tasks/test_t0506.py && python machine/tools/validate_evidence.py evidence/tasks/T0506.json`
- 证据：evidence/tasks/T0506.json
- 回滚：关闭本任务相关 Feature Flag，恢复上一已验证 Commit/Digest；Raw 永不覆盖。
- Stop：出现不可逆风险; 需要超出冻结范围的权限; 验收 Oracle 无法执行; 公开面出现敏感数据

### P5.4 — 04:30 生产工作流

#### T0507 — 实现日常/周日/手动 Workflow

- 目标：04:30 Australia/Sydney；周日 full reconcile；workflow_dispatch。
- 依赖：T0506
- Acceptance：AC-023, AC-025
- 测试：`python -m pytest -q tests/tasks/test_t0507.py && python machine/tools/validate_evidence.py evidence/tasks/T0507.json`
- 证据：evidence/tasks/T0507.json
- 回滚：关闭本任务相关 Feature Flag，恢复上一已验证 Commit/Digest；Raw 永不覆盖。
- Stop：出现不可逆风险; 需要超出冻结范围的权限; 验收 Oracle 无法执行; 公开面出现敏感数据

## S6 — 安全、模型、压力与混沌保证

### P6.1 — 软件正确性流水线

#### T0601 — 补齐单元/属性/Fuzz/Contract 测试

- 目标：覆盖 MIME、时间、幂等、Schema、公开脱敏和端点守卫。
- 依赖：T0507
- Acceptance：AC-013, AC-014, AC-016, AC-018, AC-026
- 测试：`python -m pytest -q tests/tasks/test_t0601.py && python machine/tools/validate_evidence.py evidence/tasks/T0601.json`
- 证据：evidence/tasks/T0601.json
- 回滚：关闭本任务相关 Feature Flag，恢复上一已验证 Commit/Digest；Raw 永不覆盖。
- Stop：出现不可逆风险; 需要超出冻结范围的权限; 验收 Oracle 无法执行; 公开面出现敏感数据

#### T0602 — 执行端到端与跨仓故障测试

- 目标：测试私有优先、恢复、M3 Gate 和 Release Asset。
- 依赖：T0601
- Acceptance：AC-007, AC-027, AC-028
- 测试：`python -m pytest -q tests/tasks/test_t0602.py && python machine/tools/validate_evidence.py evidence/tasks/T0602.json`
- 证据：evidence/tasks/T0602.json
- 回滚：关闭本任务相关 Feature Flag，恢复上一已验证 Commit/Digest；Raw 永不覆盖。
- Stop：出现不可逆风险; 需要超出冻结范围的权限; 验收 Oracle 无法执行; 公开面出现敏感数据

### P6.2 — Abuse 与安全红队

#### T0603 — 执行输入攻击红队

- 目标：Prompt Injection、路径、CSV、PDF、宏、压缩炸弹和外联。
- 依赖：T0602
- Acceptance：AC-020
- 测试：`python -m pytest -q tests/tasks/test_t0603.py && python machine/tools/validate_evidence.py evidence/tasks/T0603.json`
- 证据：evidence/tasks/T0603.json
- 回滚：关闭本任务相关 Feature Flag，恢复上一已验证 Commit/Digest；Raw 永不覆盖。
- Stop：出现不可逆风险; 需要超出冻结范围的权限; 验收 Oracle 无法执行; 公开面出现敏感数据

#### T0604 — 执行权限与供应链红队

- 目标：OAuth、GitHub App、Secret、Action SHA、依赖和日志。
- 依赖：T0603
- Acceptance：AC-018, AC-019, AC-021, AC-022
- 测试：`python -m pytest -q tests/tasks/test_t0604.py && python machine/tools/validate_evidence.py evidence/tasks/T0604.json`
- 证据：evidence/tasks/T0604.json
- 回滚：关闭本任务相关 Feature Flag，恢复上一已验证 Commit/Digest；Raw 永不覆盖。
- Stop：出现不可逆风险; 需要超出冻结范围的权限; 验收 Oracle 无法执行; 公开面出现敏感数据

### P6.3 — 模型能力与安全流水线

#### T0605 — 建立 Codex System Card 与 Evals

- 目标：证明开发线程和 Auto 不接触真实数据、不索取 Secret、不越权。
- 依赖：T0604
- Acceptance：AC-024, AC-033
- 测试：`python -m pytest -q tests/tasks/test_t0605.py && python machine/tools/validate_evidence.py evidence/tasks/T0605.json`
- 证据：evidence/tasks/T0605.json
- 回滚：关闭本任务相关 Feature Flag，恢复上一已验证 Commit/Digest；Raw 永不覆盖。
- Stop：出现不可逆风险; 需要超出冻结范围的权限; 验收 Oracle 无法执行; 公开面出现敏感数据

#### T0606 — 执行不同模型独立互审

- 目标：实现者与审查者分别检查范围、证据、失败诚实性和回滚。
- 依赖：T0605
- Acceptance：AC-033
- 测试：`python -m pytest -q tests/tasks/test_t0606.py && python machine/tools/validate_evidence.py evidence/tasks/T0606.json`
- 证据：evidence/tasks/T0606.json
- 回滚：关闭本任务相关 Feature Flag，恢复上一已验证 Commit/Digest；Raw 永不覆盖。
- Stop：出现不可逆风险; 需要超出冻结范围的权限; 验收 Oracle 无法执行; 公开面出现敏感数据

### P6.4 — 负载、容量和混沌

#### T0607 — 执行全量压力与边界测试

- 目标：大邮箱、500 页分页、超大附件、并发、Git/LFS 配额。
- 依赖：T0606
- Acceptance：AC-003, AC-022, AC-026, AC-031
- 测试：`python -m pytest -q tests/tasks/test_t0607.py && python machine/tools/validate_evidence.py evidence/tasks/T0607.json`
- 证据：evidence/tasks/T0607.json
- 回滚：关闭本任务相关 Feature Flag，恢复上一已验证 Commit/Digest；Raw 永不覆盖。
- Stop：出现不可逆风险; 需要超出冻结范围的权限; 验收 Oracle 无法执行; 公开面出现敏感数据

#### T0608 — 执行主动混沌与恢复演练

- 目标：注入 429/5xx/中断/冲突/损坏/错误 Secret/取消。
- 依赖：T0607
- Acceptance：AC-025, AC-027, AC-032
- 测试：`python -m pytest -q tests/tasks/test_t0608.py && python machine/tools/validate_evidence.py evidence/tasks/T0608.json`
- 证据：evidence/tasks/T0608.json
- 回滚：关闭本任务相关 Feature Flag，恢复上一已验证 Commit/Digest；Raw 永不覆盖。
- Stop：出现不可逆风险; 需要超出冻结范围的权限; 验收 Oracle 无法执行; 公开面出现敏感数据

## S7 — 安全发布、运维与交接

执行覆盖：Owner 已取消 T0703/T0704 的固定自然日等待。为保持 v1.0.1 机器 Task Graph 的不可变
谱系与哈希，`machine/contracts/task_graph.json` 不改；当前执行门以
`machine/stages/S7/contracts/stage7_acceptance_contract.json` 与 `semantic_gate.json` 为准。

### P7.1 — Alpha/Beta

#### T0701 — Alpha 合成发布

- 目标：所有功能仅合成数据，Feature Flags 默认关闭写和 M3。
- 依赖：T0608
- Acceptance：AC-021, AC-032, AC-033
- 测试：`python -m pytest -q tests/tasks/test_t0701.py && python machine/tools/validate_evidence.py evidence/tasks/T0701.json`
- 证据：evidence/tasks/T0701.json
- 回滚：关闭本任务相关 Feature Flag，恢复上一已验证 Commit/Digest；Raw 永不覆盖。
- Stop：出现不可逆风险; 需要超出冻结范围的权限; 验收 Oracle 无法执行; 公开面出现敏感数据

#### T0702 — Beta 真实 Raw-only Canary

- 目标：少量真实已验证邮件，M3/Parser/Timeline 仍关闭。
- 依赖：T0701
- Acceptance：AC-001, AC-004, AC-007
- 测试：`python -m pytest -q tests/tasks/test_t0702.py && python machine/tools/validate_evidence.py evidence/tasks/T0702.json`
- 证据：evidence/tasks/T0702.json
- 回滚：关闭本任务相关 Feature Flag，恢复上一已验证 Commit/Digest；Raw 永不覆盖。
- Stop：出现不可逆风险; 需要超出冻结范围的权限; 验收 Oracle 无法执行; 公开面出现敏感数据

### P7.2 — M3 与 Timeline Canary

#### T0703 — M3 Mutation Budget 1 Canary

- 目标：逐封远端恢复后 Trash；一次有界受保护运行内确定性证据完整，失败自动关闭。
- 依赖：T0702
- Acceptance：AC-006, AC-007, AC-026
- 测试：`python -m pytest -q tests/tasks/test_t0703.py && python machine/tools/validate_evidence.py evidence/tasks/T0703.json`
- 证据：evidence/tasks/T0703.json
- 回滚：关闭本任务相关 Feature Flag，恢复上一已验证 Commit/Digest；Raw 永不覆盖。
- Stop：出现不可逆风险; 需要超出冻结范围的权限; 验收 Oracle 无法执行; 公开面出现敏感数据

#### T0704 — Parser/Timeline Blue-Green Canary

- 目标：同次有界受保护运行对比旧/新结构与单一最新图片；不设自然日等待。
- 依赖：T0703
- Acceptance：AC-015, AC-028, AC-029, AC-030
- 测试：`python -m pytest -q tests/tasks/test_t0704.py && python machine/tools/validate_evidence.py evidence/tasks/T0704.json`
- 证据：evidence/tasks/T0704.json
- 回滚：关闭本任务相关 Feature Flag，恢复上一已验证 Commit/Digest；Raw 永不覆盖。
- Stop：出现不可逆风险; 需要超出冻结范围的权限; 验收 Oracle 无法执行; 公开面出现敏感数据

### P7.3 — GA 与 Codex 入口

#### T0705 — 启用 GA 04:30 运行

- 目标：全部 Pass Gate 后开启发现、Raw、Processed、M3、Timeline。
- 依赖：T0704
- Acceptance：AC-002, AC-023, AC-031, AC-032
- 测试：`python -m pytest -q tests/tasks/test_t0705.py && python machine/tools/validate_evidence.py evidence/tasks/T0705.json`
- 证据：evidence/tasks/T0705.json
- 回滚：关闭本任务相关 Feature Flag，恢复上一已验证 Commit/Digest；Raw 永不覆盖。
- Stop：出现不可逆风险; 需要超出冻结范围的权限; 验收 Oracle 无法执行; 公开面出现敏感数据

#### T0706 — 配置简单 Codex Automation

- 目标：普通被动健康检查；用户仍只使用开发线程。
- 依赖：T0705
- Acceptance：AC-024
- 测试：`python -m pytest -q tests/tasks/test_t0706.py && python machine/tools/validate_evidence.py evidence/tasks/T0706.json`
- 证据：evidence/tasks/T0706.json
- 回滚：关闭本任务相关 Feature Flag，恢复上一已验证 Commit/Digest；Raw 永不覆盖。
- Stop：出现不可逆风险; 需要超出冻结范围的权限; 验收 Oracle 无法执行; 公开面出现敏感数据

### P7.4 — 恢复、回滚和长期运维

#### T0707 — 执行 Recovery Key 真恢复演练

- 目标：从私有密文恢复随机 EML/Processed/Timeline 并比对摘要。
- 依赖：T0706
- Acceptance：AC-012, AC-032
- 测试：`python -m pytest -q tests/tasks/test_t0707.py && python machine/tools/validate_evidence.py evidence/tasks/T0707.json`
- 证据：evidence/tasks/T0707.json
- 回滚：关闭本任务相关 Feature Flag，恢复上一已验证 Commit/Digest；Raw 永不覆盖。
- Stop：出现不可逆风险; 需要超出冻结范围的权限; 验收 Oracle 无法执行; 公开面出现敏感数据

#### T0708 — 交付运维与补丁生命周期

- 目标：Runbook、自愈、Kill、容量、依赖补丁、停止和回滚。
- 依赖：T0707
- Acceptance：AC-021, AC-031, AC-032, AC-034
- 测试：`python -m pytest -q tests/tasks/test_t0708.py && python machine/tools/validate_evidence.py evidence/tasks/T0708.json`
- 证据：evidence/tasks/T0708.json
- 回滚：关闭本任务相关 Feature Flag，恢复上一已验证 Commit/Digest；Raw 永不覆盖。
- Stop：出现不可逆风险; 需要超出冻结范围的权限; 验收 Oracle 无法执行; 公开面出现敏感数据
