# Run Contract — Stage 0 / Phase 0.5

- Run ID：`RUN-X2N-S00-P05`
- Task：`TSK.x2n.discovery.005`
- Phase：`PH.X2N.0.5`
- 状态：治理设计 Run；不进入产品开发
- 允许写入：`xhs-douyin-2notion/**`、母仓 README 单一项目索引改名；Owner 下载目的地下 `X2N_DATA_ROOT` 隔离命名空间的空目录、私有 Owner 默认输入与临时只读研究快照
- 禁止：真实账号、浏览器控制、平台请求、媒体下载/处理、Notion/模型调用、Stage 1、push

## 目标与验收

完成六平台终态范围、Owner 默认输入、官方政策门禁、第三方许可证边界、ADR-001–010、DFD/STRIDE、停止/熔断登记及不少于 40 个纯合成治理用例。Phase 0.5 只可把以下 Acceptance 判为当前制品范围通过：

- `ACC.x2n.gov.003`：依赖、研究参考、License/NOTICE 边界可机器核验；
- `ACC.x2n.media.003`：SSRF/Path/恶意 URL 的设计策略与合成用例通过，产品实现仍为 `DOWNSTREAM_NOT_RUN`；
- `ACC.x2n.rel.003`：安全/供应链/发布设计门禁通过，发布制品仍为 `DOWNSTREAM_NOT_RUN`。

## 最小相关范围

1. 复核 Chrome、Chrome Web Store、Native Messaging、Notion 与六个平台的一手公开资料；
2. 固定 `ShilongLee/Crawler` 精确 Commit，仅作 clean-room 竞品研究；
3. 将终态范围从两平台改为六平台，修订 v0.0.0.1 Task DAG 与 Acceptance；
4. 产生机器可读治理登记、合成用例、Verifier、证据收据；
5. 清除临时竞品源码，只保留不可执行的摘要与 Hash；
6. 按 Owner 指令与 MetaDatabase 其他长期开发做 worktree 零重叠隔离，不触碰或记录外部改动内容。
7. 记录原始 taskpack 未指定本机绝对下载路径，并把 Owner 指定目的地解析为独立 x2n 命名空间；既有同级条目触碰数必须为 0。

## 验证命令

```bash
python3 -B scripts/verify_phase_0_1.py --verify-worktree --allow-external-main-dirty --verify-local-root
python3 -B scripts/verify_phase_0_2.py --verify-worktree --allow-external-main-dirty --verify-temp-cleanup --require-evidence
python3 -B scripts/verify_phase_0_5.py --verify-worktree --allow-external-main-dirty --validate-owner-input "$X2N_DATA_ROOT" --verify-temp-cleanup --write-evidence
python3 -B -m unittest discover -s tests -p 'test_*.py'
```

`--allow-external-main-dirty` 仅对应本次 Owner 明确授权的长期并行场景；默认不传参数时仍要求主树 clean。显式模式只允许外部 dirty path 计数大于零且 x2n overlap 为零，证据不得包含外部路径或内容。

## 风险、回滚与停止条件

- 风险：把“六平台支持”误解为无界通用爬虫；复制受限竞品代码；把政策未知误当授权；测试文件携带真实 URL/凭据；把并行隔离误解为可以修改外部主树。
- 回滚：仅回退本 Phase 治理制品；无产品代码、数据库迁移或真实数据需要恢复。
- 立即停止：需要绕过访问控制、自动滚动、代理轮换/指纹伪装、Cookie 导出、任意 URL 代理、未知/不兼容 License、真实账号/外部写入或私有数据进入仓库。

Stage 0 Gate `G0` 与远端上传保持 `NOT_RUN/FORBIDDEN_UNTIL_STAGE_GATE`；G0 必须在独立下一 Run 做全 Stage Review/Fix/Re-acceptance。
