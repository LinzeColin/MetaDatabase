# MooMooAU Archive 开发任务包 v1.0.7

- Package ID：`MMAU-ARCHIVE-TP-2026-07-24-V1.0.7`
- 目标代码位置：`LinzeColin/MetaDatabase/LinzeDatabase/MooMooAU`
- 产品契约：原样继承 v1.0.1 的 34 RQ、34 AC、58-task DAG 与十条不变量
- 直接前序：v1.0.6 Manifest 字节不可变；更早控制包继续由其谱系固定
- 唯一当前状态：`machine/status/latest.json`
- 发布状态：`CONTROLLED_BETA_DELIVERY_NOT_FINAL`

## 本版本唯一范围

v1.0.7 只补齐 T0703 的受保护执行入口，不执行 T0703：

1. 新增独立 `ProtectedM3Bootstrap`，只装配 Raw、Processed、远端恢复、第二次发件人验证与
   `users.messages.trash`；不依赖 schedule、Blue-Green、Timeline、GA 或本地状态；
2. 每次最多处理一个 verified candidate，M3 source mutation budget 固定为 1；
3. Processed complete 或 explicit safe-deferred 必须先完成并经同一私有仓远端恢复，随后才允许
   exact source-message Trash；失败时保留 Gmail 原件并 fail closed；
4. 新增 main-only、owner/actor-bound、GitHub-hosted、workflow attempt 1 的
   `.github/workflows/moomooau-m3.yml`；
5. workflow 只引用八个精确 Secret 名，不枚举、不输出、不持久化 Secret；
6. 首个无 Secret job 绑定 exact main SHA、T0702 protected PASS receipt、同树代码/测试摘要与当前
   `machine/stages/S7/contracts/run_contract.json`；
7. 当前 Run Contract 保持 `m3_authorized=false`，因此 workflow 默认禁用并必定在 Secret 读取前停止；
8. 本地合成端到端已验证 Processed 远端恢复先于唯一 exact-message Trash，age ciphertext-only 写入
   与 tmpfs/credential cleanup；这不能替代 protected Oracle；
9. 真实 Gmail、私有数据仓、Secret、Processed、M3、Timeline、workflow dispatch 与发布计数均为 0；
10. T0702/S7AC-002 的既有 protected PASS 不变，T0703/S7AC-003、最终 Acceptance、生产健康、
    Stage 7 完成与最终发布仍未通过。

## 验证入口

1. `python -m pytest -q tests/tasks/test_t0701.py tests/tasks/test_t0702.py tests/tasks/test_t0703.py`
2. `python -m ruff format --check src tests machine/stages/S7/tools`
3. `python -m ruff check --no-cache src tests machine/stages/S7/tools`
4. `python -m mypy --no-incremental src machine/stages/S7/tools`
5. `python machine/stages/S7/tools/validate_stage7.py --governance-root <固定外部检出> --preflight`
6. `python machine/tools/validate_package.py`
7. `python machine/tools/validate_delivery_status.py`
8. `python machine/tools/validate_publication.py`

## 准确停止条件

当前工作停在“受保护 T0703 入口本地就绪、执行未授权”。不得 dispatch M3，不得读取或配置 M3
Secret，不得执行 Gmail mutation、Processed/Timeline 写入或发布。未来只有新的明确 T0703 Run
Contract 将 `m3_authorized` 置为 true、预算仍精确为 1 且 exact-main 全部门通过后，才可执行唯一一次
protected M3 first attempt。
