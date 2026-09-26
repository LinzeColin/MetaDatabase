# Signal Lattice

## 做什么

永久只读的投研看板。每 60 秒从新浪 / 腾讯 / 天天基金免密钥接口取行情与日线，各分支独立给方向，按贡献度加权汇总成一个投资结论；行情超过 180 秒（按交易时段计）未推进即阻断，不拿旧结论冒充实时。不下单、不登录券商，`SIGNAL_LATTICE_ENABLE_TRADING=1` 会直接报错。

8 个分支中已实现 3 个：`s1_momentum`、`s2_meanrev`、`global-equity-lead-lag-atlas`（子集）；其余 5 个以 `UNIMPLEMENTED`、权重 0 标出。逐个说明见 `文档/01_产品需求.md`。

## 怎么跑

```bash
cd Signal-Lattice
PYTHONPATH=src python3 -m pytest -q -p no:cacheprovider tests      # 需 pytest、setuptools
sudo bash scripts/deploy_v2.sh                                       # 生产机：构建、安装、启动 systemd
```

线上核查、业务判据与回滚命令见 `文档/06_运维手册.md`。代码在 `src/signal_lattice/`（入口 `cli.py`），页面在 `web/`，systemd 单元在 `deploy/systemd-v2/`。`v19_release/` 与 `scripts/deploy_v19_15s.sh` 是已被取代的 v19 冻结 fixture 版本，不要用来部署。

## 数据在哪

- 运行状态：生产机 `/var/lib/signal-lattice-v2`（JSON 账本与行情缓存），不进仓库。
- v1 停机归档（2026-08-04，VPS-1，v2 不读取）：`LinzeColin/Private-Database` Release `signal-lattice-archive-20260804`。
- 股票 Skill 源码：`Stock_Skill/`（由 `stock-skill-validation.yml` 校验）。
