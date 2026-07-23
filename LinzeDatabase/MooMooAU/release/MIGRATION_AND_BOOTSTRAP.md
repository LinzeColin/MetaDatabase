# Bootstrap、私有仓改名与历史回填

## 一次性 Bootstrap 顺序

1. Codex 开发线程验证任务包并建立公开项目；
2. 创建/配置 Gmail OAuth，唯一 Scope 为 `gmail.modify`；
3. 安装最小权限 GitHub App 到唯一私有数据仓；
4. 记录目标私有仓 Repository ID，运行时解析当前名称；
5. 创建受保护 GitHub Environment；
6. 临时生成 age Identity、保存 Secret、提交 Recipient、一次性交付 Recovery Key；
7. 完成合成 Recovery Drill；
8. Alpha/Beta 后才运行历史回填；
9. 完成 M3 Canary 后启用日常 04:30。

## 私有仓改名

程序不以名称作为身份主键，也不在公开树保存当前或目标名称；只以受保护 immutable Repository ID
和 GitHub App 安装范围定位。改名时不新建、不复制、不双写，仅在同一仓中新增/更新
`MooMooAU/` 和固定 live Release Asset，其他内容不动。

## 历史回填

- 范围：Gmail 当前仍可访问的全部已验证 Moomoo 入站消息，包括 Trash/Spam；
- 不访问 Moomoo Portal；
- 分批、可暂停、幂等；
- 第一次回填先 Raw-only；
- 远端恢复后再按 Mutation Budget 执行 M3；
- 已在 Trash 的消息只归档和记录；
- 未验证新发件人保持原样；
- 回填完成后 Full Reconcile 差异必须为 0。

## 人类一次性动作

仅两项不可代理：

1. 邮箱所有者完成一次 Google OAuth 同意；
2. 用户下载一次 `MooMooAU-Recovery-Key.agekey`。

开发线程应在同一个部署会话中集中完成，不在开发中途反复阻塞。
