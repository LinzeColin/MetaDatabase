# PFI

Personal Financial Intelligence：把本人的**支付宝账单**和 **CBA（Commonwealth Bank）流水**导入，
自动分类，算出**每月收入 / 支出 / 退款 / 结余 / 类别排行 / 环比趋势**，输出 Markdown 报告，或在本地 Streamlit 界面里看。

> 命名陷阱：仓里的 `LinzeDatabase/PFI/` 是旧数据目录的路牌，和本项目 `PFI/` 不是同一个东西。

## 做什么

| 步骤 | 代码 | 说明 |
|---|---|---|
| 导入 | `src/pfi_os/importers.py` | 支付宝 CSV/ZIP（UTF-8 或 GB18030，自动跳过导出头尾说明）；CBA NetBank CSV（无表头 `日期,金额,描述,余额`，或带 Date/Amount、Debit/Credit 表头）。递归扫描数据目录，跨文件去重（支付宝按交易订单号）。|
| 分类 | `src/pfi_os/classify.py` | 每笔定性质：`expense` 消费 / `income` 收入 / `refund` 退款 / `transfer` 自有账户搬运与还款 / `investment` 基金·余额宝·券商·黄金 / `excluded` 交易关闭或方向未知。类别：支付宝用自带“交易分类”，CBA 用关键词。数据目录下可放 `rules.json` 覆盖。|
| 月报 | `src/pfi_os/report.py` | 按月、按币种（CNY / AUD 分开，不做汇率换算）汇总；净支出 = 支出 − 退款，结余 = 收入 − 净支出；转账、还款、投资不计收支，投资净流单列。|
| 界面 | `src/pfi_os/ui.py` | 月度图表、类别明细、流水表、只看需复核。|

`rules.json` 例子（命中即用，优先于内置规则）：

```json
[{"match": "transfer to landlord", "kind": "expense", "category": "住房物业"}]
```

## 怎么跑

Windows / macOS / Linux 相同，Python ≥ 3.10：

```bash
pip install -e "PFI[app]"                         # 只要命令行报告可不带 [app]
export PFI_DATA_DIR=~/.pfi/data                   # 真实流水所在目录（仓外）

python -m pfi_os report                           # 打印月度收支报告
python -m pfi_os report --out ~/.pfi/月报.md       # 写文件
python -m pfi_os ledger --out ~/.pfi/ledger.csv   # 导出逐笔分类结果，便于复核
python -m pfi_os app                              # 本地界面 http://127.0.0.1:8501
# 等价：PFI_DATA_DIR=... streamlit run PFI/src/pfi_os/ui.py
```

macOS 可双击 `StartPFI.command`，它只调用 `python -m pfi_os app`（`PFI_DATA_DIR` 可写在 `~/.pfi/env`）。

先用仓内样例试：`PFI_DATA_DIR=PFI/examples/data python -m pfi_os report`。

测试（Linux 全量，CI：`.github/workflows/pfi-tests.yml`）：

```bash
pip install -e "PFI[test]" && cd PFI && python -m pytest -q
```

## 数据在哪

- **真实流水不进本仓**。支付宝 4 年账单（4 份原始 CSV，约 8,815 条）在私有仓
  `LinzeColin/Private-Database` 的 `Private-MetaDatabase/`，domain `LinzeDatabase-alipay`。禁止 clone 私有仓。
- 拉到本机（需要本机 `gh auth login` 且对私有仓有读权限；客户端用本仓 `EEI/scripts/private_db_client.py`，
  或 `KMOS/KMDatabase/machine/tools/private_db_client.py` 的同协议实现）：

```bash
export PFI_DATA_DIR=~/.pfi/data
python -m pfi_os pull --client EEI/scripts/private_db_client.py
# 等价手工两步：
python3 EEI/scripts/private_db_client.py list Private-MetaDatabase --prefix objects/ | grep '_alipay_20'
python3 EEI/scripts/private_db_client.py get  Private-MetaDatabase objects/<xx>/<sha256>_alipay_<起>-<止>_<hash>.csv "$PFI_DATA_DIR/alipay/<同名>.csv"
```

  `pull` 只拉 `alipay_YYYYMMDD-YYYYMMDD_*.csv` 原始账单，不拉旧的 processed 汇总表（否则会重复计数）。
- CBA 流水：在 NetBank 导出 CSV，放进 `$PFI_DATA_DIR/cba/`。新导出的账单直接放进数据目录即可，重叠区间会自动去重。
- 仓内只有 `examples/data/` 的手工样例（无真实个人信息），测试用它逐项核对月报数字。
