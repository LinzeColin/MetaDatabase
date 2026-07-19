# Run Contract — Stage 0 / Phase 0.2

## 目标

只执行 `TSK.x2n.discovery.004`：以官方 Git 仓库与官方平台文档为证据，登记三个上游候选的精确 Commit、License、依赖、Schema、能力和升级门禁。这里的“登记”不等于启用、捆绑或认可平台访问方式。

## 最小范围

- 允许修改：`xiaohongshu-douyin-2notion/**`。
- 允许临时写入：`${X2N_DATA_ROOT}/downloads/external_research/runs/RUN-X2N-S00-P02/upstreams/`，仅保存本轮浅 clone；验收后删除整个本轮目录。
- 允许网络读取：三个官方 GitHub 仓库及一手平台文档。
- 禁止：产品代码、真实账号、浏览器自动化、媒体下载、Notion 写入、旧目录读取/迁移、Phase 0.5、Stage Gate、push。

## 输入与输出

输入是 v0.0.0.1 Task Pack 指定的两个 Commit、MediaCrawler 本轮 `main`、官方文档和 Phase 0.1 路径/隐私契约。输出是 Dependency Registry、Commit Pins、Capability Matrix、文件哈希清单、SBOM dry run、NOTICE 和 Shadow-upgrade Plan。

## 验证

```bash
python3 -B scripts/verify_phase_0_2.py --source-root <private-run-upstreams> --verify-worktree
python3 -B -m unittest discover -s tests -p 'test_*.py'
python3 -B scripts/verify_phase_0_2.py --verify-worktree --verify-temp-cleanup
```

所有结论 Fail Closed：无法从仓库内 License 文件确认的许可证记为未核验；范围依赖或无 lock 的候选不得变成 runtime dependency；官方能力未明确覆盖个人点赞/收藏读取时记为 `UNKNOWN`，不得推断授权。

## 风险、回滚与停止条件

- 风险：上游漂移、README 与源码不一致、transitive dependency 未锁定、临时 clone 含认证 URL。
- 缓解：Commit + tree + blob + SHA-256 四层证据；remote URL 规范化；实际 runtime dependency 与审计候选分开；临时快照必须清理。
- 回滚：回退本 Phase 本地提交；保持候选关闭；不影响 Phase 0.1 私有根或任何真实数据。
- 停止：需要复制未核验/受限代码、需要真实凭据/账号、无法得到精确 Commit、或任何证据会进入公开仓库隐私边界。

## Acceptance 解释

- `ACC.x2n.gov.003`：仅对当前无产品包、无 runtime dependency 的制品范围验收；未来启用任何 Adapter 时必须重新生成 lock、许可证报告和 SBOM。
- `ACC.x2n.dy.003`：本 Phase 只验 pin、MIT NOTICE 与上游 Schema 基线。正常/缺字段/未知字段/错误退出/超时/Schema drift 的 Adapter Contract Tests 在 Adapter 存在后执行，当前为 `DOWNSTREAM_NOT_RUN`。

Stage 0 Gate 保持 `NOT_RUN`，远端上传保持禁止。
