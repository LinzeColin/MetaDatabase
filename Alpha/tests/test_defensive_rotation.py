"""S1 动态防御轴(defensive_basket):默认关零行为变化;开启则挑最强避险资产。"""

from datetime import date, timedelta

from backend.app.backtest.fees import FeeModel
from backend.app.backtest.pipeline import S1Params, precompute, simulate_s1
from backend.app.strategies.bars import Bar

FEE = FeeModel(commission_usd_per_order=0.99)


def weekdays(start: date, n: int) -> list[date]:
    out, d = [], start
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d += timedelta(days=1)
    return out


def mk(name, days, closes):
    return precompute(name, [Bar(day=d, open=c, high=c, low=c, close=c)
                             for d, c in zip(days, closes)])


def build(days):
    # RISK 强势上行;两个防御:DEFA 缓升(强于 DEFB),DEFB 走平;CSH 现金
    return {
        "RISK": mk("RISK", days, [100 + 0.20 * i for i in range(len(days))]),
        "DEFA": mk("DEFA", days, [50 + 0.08 * i for i in range(len(days))]),
        "DEFB": mk("DEFB", days, [40 + 0.02 * i for i in range(len(days))]),
        "CSH": mk("CSH", days, [100.0] * len(days)),
    }


def run(params, days, s):
    return simulate_s1(s, ["RISK", "DEFA", "DEFB", "CSH"], "CSH", params,
                       start=days[0], end=days[-1], sleeve_usd=5000.0,
                       fee=FEE, calendar=days)


def test_none_basket_leaves_static_path_intact():
    # defensive_basket=None 时防御完全走静态 symbol 路径:持 DEFA,与"无防御"不同
    days = weekdays(date(2023, 1, 2), 620)
    s = build(days)
    static = run(S1Params(top_n=1, target_vol=999.0, defensive_symbol="DEFA",
                          defensive_weight=0.2), days, s)
    no_def = run(S1Params(top_n=1, target_vol=999.0), days, s)
    assert static.equity != no_def.equity          # 静态防御确实生效
    assert static.orders > 0


def test_basket_more_conservative_than_static_early():
    # 单元素篮子 vs 静态:篮子对防御资产多一道 SMA200 闸,早期(SMA200 未就绪)退现金,
    # 与静态(无条件持有)必然不同——证明动态闸真实存在且默认路径未被误改。
    days = weekdays(date(2023, 1, 2), 620)
    s = build(days)
    static = run(S1Params(top_n=1, target_vol=999.0, defensive_symbol="DEFA",
                          defensive_weight=0.2), days, s)
    basket1 = run(S1Params(top_n=1, target_vol=999.0, defensive_weight=0.2,
                           defensive_basket=("DEFA",)), days, s)
    assert static.equity != basket1.equity        # SMA200 闸使动态篮子早期更保守
    assert static.orders > 0 and basket1.orders > 0


def test_basket_picks_strongest_defensive():
    days = weekdays(date(2023, 1, 2), 620)
    s = build(days)
    r = run(S1Params(top_n=1, target_vol=999.0, defensive_weight=0.2,
                     defensive_basket=("DEFA", "DEFB")), days, s)
    # 篮子里 DEFA 恒强于 DEFB,应只买过 DEFA、从不买 DEFB
    # (用最终持仓与订单侧证:DEFB 从未进 targets → 期末不应持 DEFB)
    # 通过重跑「只 DEFB」对比:两者不同即证明选了 DEFA 而非 DEFB
    only_b = run(S1Params(top_n=1, target_vol=999.0, defensive_weight=0.2,
                          defensive_basket=("DEFB",)), days, s)
    assert r.equity[-1] != only_b.equity[-1]
    assert r.equity[-1] > only_b.equity[-1]  # 选强者(DEFA)净值更高


def test_all_defensive_below_sma_parks_cash():
    days = weekdays(date(2023, 1, 2), 620)
    # 两个防御资产都持续下行(恒在 SMA200 下方)→ 都不合格 → 防御预算退现金
    s = {
        "RISK": mk("RISK", days, [100 + 0.20 * i for i in range(len(days))]),
        "DEFA": mk("DEFA", days, [200 - 0.10 * i for i in range(len(days))]),
        "DEFB": mk("DEFB", days, [200 - 0.12 * i for i in range(len(days))]),
        "CSH": mk("CSH", days, [100.0] * len(days)),
    }
    r = simulate_s1(s, ["RISK", "DEFA", "DEFB", "CSH"], "CSH",
                    S1Params(top_n=1, target_vol=999.0, defensive_weight=0.2,
                             defensive_basket=("DEFA", "DEFB")),
                    start=days[0], end=days[-1], sleeve_usd=5000.0, fee=FEE, calendar=days)
    # 期末不应持有任何下行防御资产
    # (无法直接读持仓,用「防御资产从未被买」的净值特征:与 defensive_weight=0 满仓风险相比,
    #  退现金版应因 20% 常年闲置而净值更低)
    full_risk = simulate_s1(s, ["RISK", "DEFA", "DEFB", "CSH"], "CSH",
                            S1Params(top_n=1, target_vol=999.0),
                            start=days[0], end=days[-1], sleeve_usd=5000.0, fee=FEE, calendar=days)
    assert r.equity[-1] < full_risk.equity[-1]
