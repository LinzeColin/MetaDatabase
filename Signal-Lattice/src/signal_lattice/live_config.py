"""V2 真实运行时配置。观察宇宙覆盖美股、A 股、港股与场外基金。"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import List

from .marketdata.models import Instrument
from .version import VERSION


APP_VERSION = VERSION


def default_universe() -> List[Instrument]:
    return [
        Instrument("usSPY", "SPDR S&P 500 ETF", "US", "ETF", "America/New_York", "gb_spy", None, "usSPY", None, "usSPY", True, "SPY"),
        Instrument("usQQQ", "Invesco QQQ Trust", "US", "ETF", "America/New_York", "gb_qqq", None, "usQQQ", None, "usSPY", True, "QQQ"),
        Instrument("usAAPL", "Apple", "US", "STOCK", "America/New_York", "gb_aapl", None, "usAAPL", None, "usSPY", True, "AAPL"),
        # S1 多周期动量轮动需要完整的八标的资产池（来源 Alpha configs/strategies/s1_momentum.yaml）；
        # 缺任何一只，S1 会判 CONFIGURED_UNIVERSE_INCOMPLETE 并拒绝出结论。
        Instrument("usIWM", "iShares 罗素2000 ETF", "US", "ETF", "America/New_York", "gb_iwm", None, "usIWM", None, "usSPY", True, "IWM"),
        Instrument("usEFA", "iShares MSCI 欧澳远东 ETF", "US", "ETF", "America/New_York", "gb_efa", None, "usEFA", None, "usSPY", True, "EFA"),
        Instrument("usEEM", "iShares MSCI 新兴市场 ETF", "US", "ETF", "America/New_York", "gb_eem", None, "usEEM", None, "usSPY", True, "EEM"),
        Instrument("usGLD", "SPDR 黄金 ETF", "US", "ETF", "America/New_York", "gb_gld", None, "usGLD", None, "usSPY", True, "GLD"),
        Instrument("usTLT", "iShares 20年期以上美国国债 ETF", "US", "ETF", "America/New_York", "gb_tlt", None, "usTLT", None, "usSPY", True, "TLT"),
        Instrument("usBIL", "SPDR 1-3月美国国债 ETF", "US", "ETF", "America/New_York", "gb_bil", None, "usBIL", None, "usSPY", True, "BIL"),
        Instrument("sh000300", "沪深300", "CN", "INDEX", "Asia/Shanghai", "sh000300", "sh000300", "sh000300", None, "sh000300"),
        Instrument("sh600000", "浦发银行", "CN", "STOCK", "Asia/Shanghai", "sh600000", "sh600000", "sh600000", None, "sh000300"),
        Instrument("sh510300", "沪深300 ETF", "CN", "ETF", "Asia/Shanghai", "sh510300", "sh510300", "sh510300", None, "sh000300"),
        Instrument("hk02800", "盈富基金", "HK", "ETF", "Asia/Hong_Kong", "hk02800", "hk02800", "hk02800", None, "hk02800"),
        Instrument("hk00700", "腾讯控股", "HK", "STOCK", "Asia/Hong_Kong", "hk00700", "hk00700", "hk00700", None, "hk02800"),
        Instrument("fund110022", "易方达消费行业股票", "CN", "MUTUAL_FUND", "Asia/Shanghai", None, None, None, "110022", "sh000300", False),
    ]


@dataclass(frozen=True)
class LiveSettings:
    state_dir: Path
    web_dir: Path
    host: str
    port: int
    loop_seconds: int
    quote_max_age_seconds: int
    bar_max_age_days: int
    public_url: str
    sina_quote_url: str
    sina_us_kline_url: str
    sina_cn_kline_url: str
    tencent_quote_url: str
    tencent_kline_url: str
    eastmoney_fund_url: str
    universe: List[Instrument]

    @classmethod
    def from_env(cls, project_root: Path) -> "LiveSettings":
        state_dir = Path(os.environ.get("SIGNAL_LATTICE_STATE_DIR", "/var/lib/signal-lattice-v2")).resolve()
        web_dir = Path(os.environ.get("SIGNAL_LATTICE_WEB_DIR", str(project_root / "web"))).resolve()
        if os.environ.get("SIGNAL_LATTICE_ENABLE_TRADING", "0") == "1":
            raise ValueError("AUTOMATIC_TRADING_IS_PERMANENTLY_DISABLED")
        return cls(
            state_dir=state_dir,
            web_dir=web_dir,
            host=os.environ.get("SIGNAL_LATTICE_HOST", "127.0.0.1"),
            # 8787 是 Cloudflare 隧道（面板托管的 ingress）固定指向的端口，v2 必须监听它才能接管公网流量。
            # 不要改回 8788：那个端口在生产机上被 weread-port 占用，撞上会打掉另一个在跑的服务。
            port=int(os.environ.get("SIGNAL_LATTICE_PORT", "8787")),
            loop_seconds=max(30, int(os.environ.get("SIGNAL_LATTICE_LOOP_SECONDS", "60"))),
            quote_max_age_seconds=max(30, int(os.environ.get("SIGNAL_LATTICE_QUOTE_MAX_AGE_SECONDS", "180"))),
            bar_max_age_days=max(2, int(os.environ.get("SIGNAL_LATTICE_BAR_MAX_AGE_DAYS", "7"))),
            public_url=os.environ.get("SIGNAL_LATTICE_PUBLIC_URL", "https://signal-lattice.linzezhang.com"),
            sina_quote_url=os.environ.get("SIGNAL_LATTICE_SINA_QUOTE_URL", "https://hq.sinajs.cn/list="),
            sina_us_kline_url=os.environ.get("SIGNAL_LATTICE_SINA_US_KLINE_URL", "https://stock.finance.sina.com.cn/usstock/api/jsonp.php/var%20_=/US_MinKService.getDailyK?symbol={symbol}"),
            sina_cn_kline_url=os.environ.get("SIGNAL_LATTICE_SINA_CN_KLINE_URL", "https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData?symbol={symbol}&scale=240&ma=no&datalen=3000"),
            tencent_quote_url=os.environ.get("SIGNAL_LATTICE_TENCENT_QUOTE_URL", "https://qt.gtimg.cn/q="),
            tencent_kline_url=os.environ.get("SIGNAL_LATTICE_TENCENT_KLINE_URL", "https://web.ifzq.gtimg.cn/appstock/app/{kind}/get?param={symbol},day,,,2000,qfq"),
            eastmoney_fund_url=os.environ.get("SIGNAL_LATTICE_EASTMONEY_FUND_URL", "https://fund.eastmoney.com/pingzhongdata/{code}.js"),
            universe=default_universe(),
        )
