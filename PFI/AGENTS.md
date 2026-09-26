# PFI Agent Contract

- 产品范围：支付宝 / CBA 流水导入 → 分类 → 月度收支与趋势 → 报告 / 本地界面。代码只在 `src/pfi_os/`，说明见 `README.md`，现状与卡点见 `HANDOFF.md`。
- 真实流水只从 `$PFI_DATA_DIR` 读，来源是 Private-Database（`python -m pfi_os pull`）；禁止把真实流水、导出件、SQLite 提交进本仓，测试只用 `examples/data/` 的手工样例。
- 路径一律走环境变量或相对项目根；不写 `/Users/...`、`~/Downloads`、macOS 专属命令。`StartPFI.command` 只能调用 `python -m pfi_os app`。
- 测试只验证行为（导入、分类、月报数字、CLI、界面能渲染），不写只校验文档 / 哈希 / 流程的合同测试。Linux 上 `cd PFI && python -m pytest -q` 必须全绿。
- 不自动交易、不连券商、不做支付。
- 改了 `machine/facts/*` 之后跑 `python3 PFI/machine/tools/render_human.py --root PFI` 并确认
  `python3 PFI/machine/tools/check_dual_plane_ci.py --root . --projects PFI --require-projects` 通过。
