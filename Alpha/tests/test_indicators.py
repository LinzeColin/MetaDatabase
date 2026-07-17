"""ALPHA-LIVE-030:指标手工复算对照(每个断言的期望值都能用白盒公式笔算)。"""

import math

import pytest

from backend.app.strategies.indicators import (
    atr,
    ibs,
    realized_vol_annual_pct,
    rsi_wilder,
    sma,
    trailing_return,
)


def test_sma_hand_check():
    assert sma([1, 2, 3, 4], 2) == 3.5          # (3+4)/2
    assert sma([1, 2, 3, 4], 4) == 2.5
    assert sma([1, 2, 3], 4) is None            # 数据不足不填充


def test_trailing_return_hand_check():
    closes = [100.0, 105.0, 110.0, 121.0]
    assert trailing_return(closes, 2) == pytest.approx(121.0 / 105.0 - 1)  # P/P[-2] - 1
    assert trailing_return(closes, 3) == pytest.approx(0.21)
    assert trailing_return(closes, 4) is None   # 需要 lookback+1 个点


def test_rsi2_wilder_hand_check():
    """手算:closes [10, 11, 10.5, 10.2, 10.1]
    ups [1,0,0,0] downs [0,.5,.3,.1]
    avg_u: .5 -> .25 -> .125 ; avg_d: .25 -> .275 -> .1875
    RS = .125/.1875 = 2/3 ; RSI = 100 - 100/(5/3) = 40
    """
    assert rsi_wilder([10, 11, 10.5, 10.2, 10.1], 2) == pytest.approx(40.0)


def test_rsi_all_up_is_100_all_down_near_0():
    assert rsi_wilder([1, 2, 3, 4, 5], 2) == 100.0
    assert rsi_wilder([5, 4, 3, 2, 1], 2) == pytest.approx(0.0)


def test_ibs_hand_check():
    assert ibs(high=12.0, low=10.0, close=10.4) == pytest.approx(0.2)  # (10.4-10)/2
    assert ibs(high=12.0, low=10.0, close=12.0) == 1.0
    assert ibs(high=10.0, low=10.0, close=10.0) is None  # 无定义


def test_atr_hand_check():
    """手算(period=2):
    TR1 = max(.7, 1.0, .3) = 1.0 ; TR2 = max(.5, .2, .3) = .5 ; ATR = .75
    """
    h, l, c = [10.0, 10.5, 10.4], [9.0, 9.8, 9.9], [9.5, 10.2, 10.0]
    assert atr(h, l, c, 2) == pytest.approx(0.75)


def test_realized_vol_hand_check():
    """closes [100,110,99] window=2:
    rets = ln(1.1), ln(0.9) ; 样本方差(除 n-1) ; 年化 = sd*sqrt(252)*100
    """
    r1, r2 = math.log(1.1), math.log(0.9)
    mean = (r1 + r2) / 2
    sd = math.sqrt((r1 - mean) ** 2 + (r2 - mean) ** 2)  # /(2-1)
    expect = sd * math.sqrt(252) * 100
    assert realized_vol_annual_pct([100, 110, 99], 2) == pytest.approx(expect)


def test_indicators_deterministic():
    closes = [100 + (i % 7) * 0.5 for i in range(60)]
    assert rsi_wilder(closes, 2) == rsi_wilder(closes, 2)
    assert realized_vol_annual_pct(closes, 20) == realized_vol_annual_pct(closes, 20)
