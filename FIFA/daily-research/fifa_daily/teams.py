"""球队名归一：不同来源对同一支球队写法不同（"Arsenal FC" / "Arsenal" / "Arsenal F.C."）。

做法：先机械归一（去重音、去 FC/AFC/国家代码等），再用一张小别名表处理机械做不到的；
仍对不上的球队按「独立球队」处理（只会少一条跨来源联系，不会串队），并在状态里列出来。
"""

from __future__ import annotations

import re
import unicodedata
from collections import Counter, defaultdict

# 机械归一时丢弃的词
_STOP = {
    "fc", "afc", "cf", "sc", "ac", "as", "ssc", "sk", "fk", "kv", "kaa", "sv", "tsg", "vfb", "vfl", "fsv",
    "ud", "cd", "rc", "rcd", "sd", "ca", "club", "de", "the", "1", "krc", "ks", "nk", "bk", "if", "ik",
    "ff", "sf", "cfc", "afk", "gnk", "hnk", "ofi", "pae", "paok", "aek", "aris", "og", "ogc", "us", "ssd",
    "royale", "real",
}
_KEEP_REAL = True  # "real" 在 STOP 里只为处理 "Royale ..."；Real Madrid / Real Betis 的 real 必须保留

_SPECIAL = {"ø": "o", "ł": "l", "đ": "d", "ð": "d", "ß": "ss", "æ": "ae", "œ": "oe", "ı": "i"}


def _ascii(s: str) -> str:
    s = "".join(_SPECIAL.get(c, c) for c in s.lower())
    s = unicodedata.normalize("NFKD", s)
    return "".join(c for c in s if not unicodedata.combining(c))


def mechanical(name: str) -> str:
    s = _ascii(name).replace("&", " and ")
    s = re.sub(r"\b(?:[a-z]\.){2,}", lambda m: m.group(0).replace(".", ""), s)  # F.C. -> fc
    s = re.sub(r"\((?:[a-z]{3})\)", " ", s)      # (ESP)
    s = re.sub(r"\([^)]*\)", " ", s)             # (Azerbaijan)
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    toks = [t for t in s.split() if t not in _STOP or (t == "real" and _KEEP_REAL)]
    return " ".join(toks)


# 机械归一之后仍不同的写法 -> 统一键（值取联赛数据里的写法）。
ALIASES: dict[str, str] = {}


def _alias(canonical: str, *variants: str) -> None:
    for v in variants:
        ALIASES[mechanical(v)] = mechanical(canonical)


_alias("FC Bayern München", "Bayern Munich")
_alias("Como 1907", "Como")
_alias("Feyenoord Rotterdam", "Feyenoord")
_alias("FC Internazionale Milano", "Inter Milan", "Inter")
_alias("Racing Lens", "Lens", "RC Lens")
_alias("Lille OSC", "Lille")
_alias("Olympiakos Piraeus", "PAE Olympiakos SFP", "Olympiacos")
_alias("PSV", "PSV Eindhoven")
_alias("Real Betis Balompié", "Real Betis")
_alias("RB Salzburg", "FC Red Bull Salzburg", "Red Bull Salzburg")
_alias("Sporting Clube de Portugal", "Sporting CP")
_alias("SK Slavia Praha", "Slavia Prague")
_alias("AEK Athen", "AEK Athens")
_alias("Real Sociedad de Fútbol", "Real Sociedad")
_alias("Atlético Madrid", "Club Atlético de Madrid")
_alias("Sport Lisboa e Benfica", "Benfica", "SL Benfica")

# 中文名（键为归一后的球队键）。没有列到的球队页面显示英文名。
ZH: dict[str, str] = {
    # 英超
    "arsenal": "阿森纳", "aston villa": "阿斯顿维拉", "bournemouth": "伯恩茅斯", "brentford": "布伦特福德",
    "brighton and hove albion": "布莱顿", "chelsea": "切尔西", "coventry city": "考文垂", "crystal palace": "水晶宫",
    "everton": "埃弗顿", "fulham": "富勒姆", "hull city": "赫尔城", "ipswich town": "伊普斯维奇",
    "leeds united": "利兹联", "liverpool": "利物浦", "manchester city": "曼城", "manchester united": "曼联",
    "newcastle united": "纽卡斯尔联", "nottingham forest": "诺丁汉森林", "sunderland": "桑德兰",
    "tottenham hotspur": "热刺",
    # 西甲
    "athletic": "毕尔巴鄂竞技", "atletico madrid": "马德里竞技", "barcelona": "巴塞罗那", "celta vigo": "塞尔塔",
    "deportivo alaves": "阿拉维斯", "deportivo la coruna": "拉科鲁尼亚", "elche": "埃尔切",
    "espanyol barcelona": "西班牙人", "getafe": "赫塔菲", "levante": "莱万特", "malaga": "马拉加",
    "osasuna": "奥萨苏纳", "rayo vallecano madrid": "巴列卡诺", "real betis balompie": "皇家贝蒂斯",
    "real madrid": "皇家马德里", "real racing santander": "桑坦德竞技", "real sociedad futbol": "皇家社会",
    "sevilla": "塞维利亚", "valencia": "瓦伦西亚", "villarreal": "比利亚雷亚尔",
    # 德甲
    "07 elversberg": "埃尔弗斯贝格", "1899 hoffenheim": "霍芬海姆", "augsburg": "奥格斯堡",
    "bayer 04 leverkusen": "勒沃库森", "bayern munchen": "拜仁慕尼黑", "borussia dortmund": "多特蒙德",
    "borussia monchengladbach": "门兴格拉德巴赫", "eintracht frankfurt": "法兰克福", "freiburg": "弗赖堡",
    "hamburger": "汉堡", "koln": "科隆", "mainz 05": "美因茨", "paderborn 07": "帕德博恩",
    "rb leipzig": "RB 莱比锡", "schalke 04": "沙尔克 04", "stuttgart": "斯图加特", "union berlin": "柏林联合",
    "werder bremen": "云达不来梅",
    # 意甲
    "acf fiorentina": "佛罗伦萨", "atalanta bc": "亚特兰大", "bologna 1909": "博洛尼亚",
    "cagliari calcio": "卡利亚里", "como 1907": "科莫", "frosinone calcio": "弗罗西诺内", "genoa": "热那亚",
    "internazionale milano": "国际米兰", "juventus": "尤文图斯", "lecce": "莱切", "milan": "AC 米兰",
    "monza": "蒙扎", "napoli": "那不勒斯", "parma calcio 1913": "帕尔马", "roma": "罗马",
    "sassuolo calcio": "萨索洛", "ss lazio": "拉齐奥", "torino": "都灵", "udinese calcio": "乌迪内斯",
    "venezia": "威尼斯",
    # 法甲
    "aj auxerre": "欧塞尔", "angers sco": "昂热", "es troyes": "特鲁瓦", "le havre": "勒阿弗尔",
    "le mans": "勒芒", "lille osc": "里尔", "lorient": "洛里昂", "monaco": "摩纳哥", "nice": "尼斯",
    "olympique lyonnais": "里昂", "olympique marseille": "马赛", "paris": "巴黎 FC",
    "paris saint germain": "巴黎圣日耳曼", "racing lens": "朗斯", "stade brestois 29": "布雷斯特",
    "stade rennais 1901": "雷恩", "strasbourg alsace": "斯特拉斯堡", "toulouse": "图卢兹",
    # 欧冠其他球队
    "athen": "AEK 雅典", "bodo glimt": "博德闪耀", "brugge": "布鲁日", "fenerbahce": "费内巴切",
    "feyenoord rotterdam": "费耶诺德", "galatasaray": "加拉塔萨雷", "lask": "林茨竞技", "porto": "波尔图",
    "psv": "埃因霍温", "sabah": "沙巴", "shakhtar donetsk": "顿涅茨克矿工", "slavia praha": "布拉格斯拉维亚",
    "slovan bratislava": "布拉迪斯拉发斯洛文", "sporting clube portugal": "葡萄牙体育", "viking": "维京",
    "benfica": "本菲卡", "sport lisboa e benfica": "本菲卡", "rb salzburg": "萨尔茨堡红牛",
}


def key(name: str) -> str:
    m = mechanical(name)
    return ALIASES.get(m, m)


class Registry:
    """记录每个键出现过的写法，选最短的当展示名。"""

    def __init__(self) -> None:
        self._raw: dict[str, Counter] = defaultdict(Counter)

    def add(self, name: str) -> str:
        k = key(name)
        clean = re.sub(r"\s*\([A-Z]{3}\)\s*", "", name).strip()
        self._raw[k][clean] += 1
        return k

    def display(self, k: str) -> str:
        raws = self._raw.get(k)
        if not raws:
            return k
        best = sorted(raws, key=lambda r: (len(re.sub(r"\b(FC|AFC|CF|SC)\b\.?", "", r)), len(r), r))[0]
        best = re.sub(r"^(FC|AFC|1\. FC|1\. FSV)\s+", "", best)
        return re.sub(r"\s+(FC|AFC)$", "", best).strip()

    def zh(self, k: str) -> str | None:
        return ZH.get(k)
