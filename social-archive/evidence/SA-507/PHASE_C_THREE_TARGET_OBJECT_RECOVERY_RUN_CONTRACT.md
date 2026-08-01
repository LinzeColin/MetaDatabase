# SA-507 Phase C — 真实三目标对象恢复 Run Contract

## Goal

对同一条已完成、非用户数据的生产 canary 对象，分别从 R2、OCI 和
GitHub Private Draft Release 恢复 age 密文；每次都在全新的隔离目录中
解密并重新计算明文 SHA-256。三次结果都必须与该对象的已验证收据一致。

## In scope

- 只读生产 Runtime Journal 中该 canary 的 artifact 与三条 `verified` 收据；
- 一个可重复、fail-closed 的对象恢复 CLI：只接受三条一致收据、受限凭据、
  空目标目录和配置的 age identity；
- R2、OCI 与 GitHub Draft Release 的真实下载、密文 SHA-256、age 解密和
  明文 SHA-256 验证；
- 脱敏的本地/生产证据，以及对精确临时恢复目录的清理验证。

## Explicitly out of scope

- Private-Database facts sync 或 cold-backup；
- 新对象采集、R2/OCI/GitHub 上传、Release 创建、timer enablement；
- 镜像发布、完整生产部署 smoke、来源/目的地平台 canary；
- Git stage、commit、tag、push、merge、源码 Release、额外 worktree；
- 删除或修改生产 Runtime、原始对象、远端对象或现有 Draft asset。

## Preconditions

1. Phase A 的持久 non-user-data canary 仍有 R2、OCI、GitHub 三条同密文
   `verified` 收据，且 GitHub Release 仍为 private Draft。
2. 生产机的 R2、OCI、Vault token 和 age identity 仍可通过各自最小权限路径
   使用；不得读取、输出、复制或复用任何 secret。
3. 恢复目标是每次新建的、与 Runtime/数据根不同的空目录。

## Validation

1. 聚焦单元测试覆盖：收据结构与三副本一致性、空目标拒绝、R2/OCI 密文
   校验、GitHub Draft pack 清单/资产校验、解密后明文 SHA-256。
2. 若恢复 CLI 改动功能源码，为新候选运行一次完整应用测试；随后运行静态、
   secret/brand 与 frozen task-pack compatibility 验证。
3. 生产上对 R2、OCI、GitHub 各运行一次恢复；三次均返回 `PASS`，并且
   原始/密文 SHA-256 与同一 artifact 收据一致。
4. 精确恢复目录和临时下载目录在验证后不存在；生产 Runtime 与远端对象计数
   没有被本阶段修改。

## Risk, rollback, stop conditions

- 任何收据不一致、GitHub 非 private/Draft、密钥缺失、下载/解密失败、目标
  非空或目标落在运行数据面时，立即停止并记录 `DEGRADED`；不绕过检查。
- 代码回滚仅限恢复入口及其测试/文档的本地未提交改动；生产恢复不覆盖既有
  数据，因此没有数据回滚动作。
- 本 phase 不以“已有上传回读”替代真实恢复，也不在三目标全数通过前声称
  SA-507 或任务包完成。
