# PFI Handoff

## 现状（2026-09-26）

- 新核心 v0.3.0：`src/pfi_os/{importers,classify,report,ui,__main__}.py`，约 700 行。支付宝 / CBA 导入 → 分类 → 月度收支报告 / 本地界面，全部走 `PFI_DATA_DIR`，入口 `python -m pfi_os`。
- 样例端到端（`examples/data/`）：月报每个数字与手算一致，新测试 42 条在 Linux 全部通过；`python -m pfi_os app` 在 Linux 上实测起得来。
- `.github/workflows/deploy-pfi.yml` 已删除（它只部署一张说明页，还依赖 CodexProject 的 reusable workflow）；新增 `.github/workflows/pfi-tests.yml`。
- 旧 v0.2.5 树（`src/pfi_v02/`、`src/pfi_os/` 下其余子包、283 个合同 / 阶段测试、`reports/` 145MB、`docs/`、`config/`、`scripts/`、`systems/`、`web/`、`macos/` 等）**尚未删除**：本轮删除操作被权限拦下，需主会话或 Owner 执行（命令见下）。完整旧状态在提交 `ee80b41ff`。

## 卡点

1. 删除旧树（主会话或 Owner，在本仓 worktree 根目录执行）：

   ```bash
   cd PFI
   git rm -r -q CHANGELOG.md MetaDatabase PRODUCT.md StopPFI.command VERSION assets config data docs \
     macos reports requirements.lock review_queue scripts shared systems web \
     功能清单.md 开发记录.md 模型参数文件.md machine/runs src/pfi_v02
   git ls-files src/pfi_os | grep -vE '^src/pfi_os/(__init__|__main__|importers|classify|report|ui)\.py$' | xargs git rm -q
   git ls-files tests | grep -vE '^tests/test_(importers|classify|end_to_end|ui|pull)\.py$' | xargs git rm -q
   python3 machine/tools/render_human.py --root .     # machine/runs 删除后 05 需重渲染
   python -m pytest -q                                # 期望全绿
   ```

   删除后可从 `machine/facts/glossary.json` 去掉“旧版运行记录用词”那 13 条术语，再重渲染。
2. 业务判据（Owner 本机）：`python -m pfi_os pull --client EEI/scripts/private_db_client.py` → `python -m pfi_os report`。
   旧版记录是 8,815 条原始、8,808 条入账；新核心按交易订单号跨文件去重，报告第二行会给出原始 / 去重 / 入账数，用来核对。
3. Coolify 上的 `pfi-public` 应用（uuid `h2p7mvhj7095gma9r9g9otjo`，pfi.linzezhang.com）需 Owner 在 Coolify 停掉并删除，DNS 记录一并移除。

## 已知限制

- 分类规则是关键词 + 支付宝自带“交易分类”，CBA 的 `Transfer to ...` 一律当自有账户转账；给人转账付房租之类要写进 `$PFI_DATA_DIR/rules.json`。
- 不做汇率换算，CNY 与 AUD 分开。
- 没有在真实账单上跑过新核心（本环境无权访问私有数据），支付宝真实导出里可能有样例没覆盖到的“收/支”取值；遇到会计入“方向未知 / 需复核”，不会静默丢。

## 下一步：并入 Serenity-Alipay 与 QBVS（本轮未动）

- `Serenity-Alipay/`（支付宝基金筛选打分）→ `src/pfi_os/funds/`，CLI 子命令 `python -m pfi_os funds`；它的公开基金参考 CSV 留作样例，生成的报告与邮件草稿走 Private-Database（domain `Serenity`）。
- `QBVS/`（策略批量回测，33/33）→ `src/pfi_os/backtest/`，子命令 `python -m pfi_os backtest`；原测试原样迁入 `tests/backtest/`。
- 顺序：先迁 QBVS（最干净、无私有数据），再迁 Serenity；每次迁移一个 PR，迁完删原顶层目录并从 `dual-plane.yml` 注册表移除。
