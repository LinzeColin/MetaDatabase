"""赛事、数据源与模型常量。所有「为什么这样选」写在这里，报告页直接引用。"""

from __future__ import annotations

REPORT_TZ = "Australia/Sydney"  # 报告日、开球时间都按悉尼时间展示（Owner 在澳洲）

# 报告覆盖的赛事：code -> (中文名, 英文名, 官方开球时间所用时区, 选它的理由)
REPORT_COMPS: dict[str, dict] = {
    "en.1": {
        "zh": "英超", "en": "Premier League", "tz": "Europe/London",
        "why": "澳洲最受关注的联赛，赛程覆盖澳洲的凌晨到上午时段。",
    },
    "uefa.cl": {
        "zh": "欧冠", "en": "UEFA Champions League", "tz": "Europe/Paris",
        "why": "跨联赛的最高水平赛事，也是把各国联赛强度连起来的唯一桥梁。",
    },
    "es.1": {"zh": "西甲", "en": "La Liga", "tz": "Europe/Madrid", "why": "五大联赛之一，欧冠球队主要来源。"},
    "de.1": {"zh": "德甲", "en": "Bundesliga", "tz": "Europe/Berlin", "why": "五大联赛之一，欧冠球队主要来源。"},
    "it.1": {"zh": "意甲", "en": "Serie A", "tz": "Europe/Rome", "why": "五大联赛之一，欧冠球队主要来源。"},
    "fr.1": {"zh": "法甲", "en": "Ligue 1", "tz": "Europe/Paris", "why": "五大联赛之一，欧冠球队主要来源。"},
}

# 只用来估计球队实力、不出预测的联赛：让「刚升级」的球队和欧冠里的外围球队有历史可依。
TRAIN_ONLY_COMPS: dict[str, str] = {
    "en.2": "英冠", "es.2": "西乙", "de.2": "德乙", "it.2": "意乙", "fr.2": "法乙",
    "nl.1": "荷甲", "pt.1": "葡超", "tr.1": "土超", "be.1": "比甲", "gr.1": "希腊超",
    "at.1": "奥甲", "sco.1": "苏超",
}

# 联赛官方开球时间所用时区（openfootball 记的是场地当地时间）
COMP_TZ: dict[str, str] = {
    "en.1": "Europe/London", "en.2": "Europe/London", "sco.1": "Europe/London",
    "es.1": "Europe/Madrid", "es.2": "Europe/Madrid",
    "de.1": "Europe/Berlin", "de.2": "Europe/Berlin",
    "it.1": "Europe/Rome", "it.2": "Europe/Rome",
    "fr.1": "Europe/Paris", "fr.2": "Europe/Paris",
    "nl.1": "Europe/Amsterdam", "pt.1": "Europe/Lisbon", "tr.1": "Europe/Istanbul",
    "be.1": "Europe/Brussels", "gr.1": "Europe/Athens", "at.1": "Europe/Vienna",
    "uefa.cl": "Europe/Paris",
}

# openfootball/football.json（CC0）各赛季可用的联赛文件
FOOTBALL_JSON_BASE = "https://raw.githubusercontent.com/openfootball/football.json/master"
FOOTBALL_JSON_SEASONS = ["2024-25", "2025-26", "2026-27"]
CL_TXT_BASE = "https://raw.githubusercontent.com/openfootball/champions-league/master"
CL_TXT_SEASONS = ["2023-24", "2024-25", "2025-26"]
CURRENT_SEASON = "2026-27"

WIKI_API = "https://en.wikipedia.org/w/api.php"
WIKI_CL_PAGE = "2026–27_UEFA_Champions_League_league_phase"
WIKI_CL_KO_PAGE = "2026–27_UEFA_Champions_League_knockout_phase"

USER_AGENT = "fifa-research-daily/1.0 (+https://github.com/LinzeColin/MetaDatabase; research-only, no betting)"

# 模型
HALF_LIFE_DAYS = 300.0      # 一年前的比赛权重约 0.43
RIDGE_TEAM_SD = 0.35        # 球队进攻/防守偏离联赛均值的先验标准差
RIDGE_GROUP_SD = 0.6        # 联赛整体强度偏移的先验标准差
HORIZON_DAYS = 14           # 报告展示未来多少天
RECENT_DAYS = 10            # 回看多少天的赛果
MAX_GOALS = 10
UNCERTAINTY_DRAWS = 400
BACKTEST_DAYS = 240
BACKTEST_STEP_DAYS = 14
MODEL_VERSION = "poisson-ridge-1"

# 页面「已过期」阈值（小时）：两次定时之间最长约 12 小时，再宽 30 小时容忍一次运行失败或服务器短暂停机
STALE_AFTER_HOURS = 30
