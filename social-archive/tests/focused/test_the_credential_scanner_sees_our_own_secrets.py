"""查明文凭据那道门，得认得出**这个项目自己持有的**那几种（v0.0.0.7 / T18）。

## 抓到它的那一刻

2026-08-05 在验另一件事时，随手拿 `GITHUB_TOKEN = "ghp_…"` 造了 25 处泄漏，
它报 **0 处命中**。挨个试了一遍部署时挂着的那 12 个密钥的形状：

    GitHub 经典 ghp_… / 细粒度 github_pat_… / Notion secret_… /
    Obsidian REST / R2 与 OCI 访问密钥        —— 这道门全部认不出
    X 的 auth_token 等浏览器 Cookie            —— 只有这一类认得

**但先把话说准**：仓里还有第二道密钥扫描门 `scripts/secret_scan.py`，
它认得 GitHub 令牌（ghp_ / github_pat_）、PEM 私钥、AKIA 访问密钥 ID
和 Bearer 头。我最初只看了一道门就说「这个项目查不出 GitHub 令牌」——
**那句话是错的**，另一道门查得出。

两道门**都**认不出的，是这四种：

    Notion secret_/ntn_ · Obsidian REST 令牌 · R2/OCI 的私密访问密钥 ·
    **age 私钥（AGE-SECRET-KEY-1…）**

最后那一把最要紧：它是全机唯一一把能解开 R2/OCI/GitHub 上所有异地备份的钥匙，
而且它还挂着一件只有 Owner 能定的事（要不要存第二份）。

## 更坏的那一处：占位符过滤把真密钥吃掉了

`PLACEHOLDER` 原来是 `^(?:…|0+|A+|x+|…)`，一个只有 `^` 锚点的 match——
`0+|A+|x+` 这几支于是按**前缀**匹配。凡是以 a / A / x / X / 0 开头的值，
一律被当成占位符跳过：

    a1b2c3…（Obsidian 令牌的形状）      被跳过
    AGE-SECRET-KEY-1…（**每一把 age 私钥**） 被跳过
    x7f3b9…                            被跳过

**age 私钥永远以 AGE- 开头**，而它是全机唯一一把能解开所有异地备份的钥匙。
"""

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCANNER = ROOT / "scripts/scan_plaintext_credentials.py"

_spec = importlib.util.spec_from_file_location("_credential_scanner", SCANNER)
_scan = importlib.util.module_from_spec(_spec)
sys.modules["_credential_scanner"] = _scan
_spec.loader.exec_module(_scan)


def _flags(line: str) -> bool:
    return bool(_scan.scan_text("sample.py", line))


# **样例在运行时拼出来，不写成字面量。**
#
# 第一版把这些形状直接写进文件，于是**另一道密钥扫描门（secret_scan.py）
# 当场把这个判据文件报成泄漏**——而它报得对：一个仓里躺着形状完好的
# GitHub 令牌和 PEM 私钥头，本身就是坏味道，哪怕是假的。
# 拼出来既躲开那道门，也不给以后的人留下「照着复制一个真的」的模板。
# **一条字面量都不留。**
#
# 第一版只把 GitHub / age / PEM 那几个拼起来（为了躲 secret_scan.py），
# Notion / Obsidian / R2 仍是字面量——于是**我刚加宽的这道门当场抓了自己的
# 判据文件**，5 处。抓得对。
#
# 本来可以把这个文件加进 SELF 豁免（那里已经有两个判据文件）。**没有那么做**：
# 豁免是门变瞎的方式，今天已经拆过一张纯装饰的白名单。全部拼出来，
# 一条豁免都不用加。
_KEY = "-KEY-1"
_A = "AGE-SECRET" + _KEY
_VALUE = "9f3b00c7d1e5a8b2f6c4d9e7a1b3"


def _assign(name: str, value: str) -> str:
    """把 `名字 = "值"` 拼出来——源码里不出现完整的赋值形状。"""
    return f'{name} = "{value}"'


LEAKS = [
    ("GitHub 经典令牌", _assign("github_token", "gh" + "p_" + "16C7e42F292c6912E7710c838347Ae178B4a")),
    ("GitHub 细粒度令牌",
     _assign("SOCIAL_ARCHIVE_GITHUB_TOKEN",
             "github" + "_pat_" + "11ABCDE0Y0aBcDeFgHiJkL_mNoPqRsTuVwXyZ123456")),
    ("Notion 集成密钥",
     _assign("NOTION_TOKEN", "sec" + "ret_" + "pYcVfBpTPGrGjBpFdEeXsRRr8YcBLhNfKcCgQpXbDeFgH")),
    ("Obsidian REST 令牌",
     _assign("OBSIDIAN_REST_TOKEN", "a1b2c3d4e5f60718293a4b5c6d7e8f90123456789abcdef0")),
    ("R2 访问密钥",
     _assign("SOCIAL_ARCHIVE_R2_SECRET_ACCESS_KEY", "wJalrXUtnFEMIK7MDENGbPxRfiCYzEXAMPLEKEY1")),
    ("age 私钥", _A + "QQPQZRFR8ZLZTPXQZLQ5TGWXVQHTMZP0FLZ4WRQWJTFV9YQZ5RQ2SQZ8XMPQ"),
    ("PEM 私钥块", "-----BEGIN OPENSSH PRIVATE" + " KEY-----"),
    ("X 的 auth_token", _assign("auth_token", _VALUE)),
]


def test_every_secret_this_project_holds_is_detected() -> None:
    """**部署时挂着 12 个密钥，这道门原来只认其中一类。**"""
    missed = [name for name, line in LEAKS if not _flags(line)]
    assert not missed, f"这几种泄漏它认不出来：{missed}"


def test_the_age_private_key_is_not_swallowed_as_a_placeholder() -> None:
    """**age 私钥永远以 AGE- 开头，而占位符过滤原来按前缀吃掉 A 开头的值。**

    它是全机唯一一把能解开 R2/OCI/GitHub 上所有备份的钥匙。这道门要是
    看不见它，它泄漏出去也不会有人被提醒。
    """
    assert not _scan._is_placeholder(_A + "QQPQZRFR8ZLZTPX")
    assert _flags(_A + "QQPQZRFR8ZLZTPXQZLQ5TGWXVQHTMZP0FLZ4WRQWJTFV9YQZ5RQ2SQZ8XMPQ")


def test_a_value_starting_with_a_or_x_or_zero_is_not_assumed_to_be_a_placeholder() -> None:
    """**`0+|A+|x+` 那几支原来按前缀匹配**，于是 1/36 左右的随机密钥被静默吞掉。"""
    for value in ("a1b2c3d4e5f60718293a4b5c6d7e8f90", "x7f3b9abcdef0123456789",
                  "A9f3b00c7d1e5a8b2f6c4d9e7a1b3c5", "0f3b00c7d1e5a8b2f6c4d9e7a1b3c5"):
        assert not _scan._is_placeholder(value), f"{value} 被当成占位符跳过了"


def test_real_placeholders_are_still_ignored() -> None:
    """**反面同样重要**：把示例值报成泄漏，这道门很快就没人看了。"""
    for value in ("xxxxxxxxxxxxxxxx", "AAAAAAAAAAAAAAAA", "00000000000000",
                  "REDACTED_VALUE_HERE", "fixture-abc123"):
        assert _scan._is_placeholder(value), f"{value} 是占位符，却没被跳过"


def test_a_group_name_is_not_a_secret() -> None:
    """**一道见谁都喊的安全门，很快就没人看了。**

    第一版让关键词出现在名字任意位置，于是
    `SECRETS_GROUP="socialarchive-secrets"`（一个**用户组名**）被报成明文凭据——
    全仓两处命中全是它。关键词现在必须落在名字末尾。
    """
    assert not _flags('SECRETS_GROUP="socialarchive-secrets"')
    assert not _flags("SOCIAL_ARCHIVE_GITHUB_TOKEN_FILE=/run/secrets/github_token"), (
        "指向密钥文件的**路径**不是密钥本身"
    )


def test_the_repo_is_clean_right_now() -> None:
    """加宽之后全仓仍是 0 命中——**否则这道门等于要求人天天忽略它**。"""
    import subprocess

    done = subprocess.run([sys.executable, str(SCANNER), "--all"],
                          cwd=ROOT, capture_output=True, text=True, check=False)
    assert done.returncode == 0, done.stdout + done.stderr


def test_it_still_refuses_to_pass_when_it_scanned_nothing() -> None:
    """扫描面为 0 和「没问题」长得一样——原有的那条空转判断不许丢。"""
    source = SCANNER.read_text(encoding="utf-8")
    assert "扫描面为 0 个文件" in source, "空转判断没了"


def test_a_truncated_hit_list_says_so() -> None:
    """列到第 20 条就不说了，读的人会以为看全了。少列一条就可能少堵一个泄漏点。"""
    source = SCANNER.read_text(encoding="utf-8")
    assert "还有 {len(hits) - len(shown)} 处没列出来" in source


def test_removing_a_secret_is_not_reported_as_leaking_one() -> None:
    """**这道门不许拦住你清理密钥。**

    diff 里既有 `+`（要加进去的）也有 `-`（要删掉的）。整段拿去扫的话，
    **正在被删掉的**密钥也会被报成命中——越想把它删干净，它越不让你提交。

    这不是假想：改这批判据时把样例换成运行时拼装（正是为了不留字面量），
    暂存之后一扫，报的全是那几行被删掉的旧样例。
    """
    source = SCANNER.read_text(encoding="utf-8")
    assert 'line.startswith("+")' in source, "diff 还是整段扫的，删密钥会被拦住"
    assert 'not line.startswith("+++")' in source, "文件头 +++ 会被当成内容"


def test_no_secret_shaped_literal_survives_in_this_file() -> None:
    """**判据自己也不许留字面量。**

    本来可以把这个文件加进 SELF 豁免（那里已经有两个判据文件）。没有那么做——
    豁免是门变瞎的方式，今天已经拆过一张纯装饰的白名单。全部拼出来，
    一条豁免都不用加。
    """
    text = Path(__file__).read_text(encoding="utf-8")
    hits = _scan.scan_text("self", text)
    assert not hits, f"这个判据文件自己就有形状完好的密钥：{hits[:2]}"


def test_the_production_scan_never_prints_the_value() -> None:
    """**一个把密钥打给你看的泄漏检查器，自己就是下一个泄漏点。**"""
    source = (ROOT / "scripts/scan_production_for_leaked_secrets.py").read_text(encoding="utf-8")
    assert '"value_len": h["value_len"]' in source, "没有只报长度"
    for leak in ('h["value"]', "hit['value']", '"value":'):
        assert leak not in source, f"它会把值本身打出来：{leak}"


def test_the_production_scan_refuses_to_pass_on_an_empty_sweep() -> None:
    """**什么都没扫到和「干净」长得一样。** 路径写错、没权限，现象都是 0。"""
    source = (ROOT / "scripts/scan_production_for_leaked_secrets.py").read_text(encoding="utf-8")
    assert "NOTHING_WAS_SCANNED" in source
    assert "这不是通过" in source


def test_the_production_scan_reuses_the_one_scanner() -> None:
    """远端跑的是**送过去的同一个扫描器**，不在那边再抄一份判定逻辑。

    抄第二份的话，两份必然漂开——这一天已经在别处吃过这个亏。
    """
    source = (ROOT / "scripts/scan_production_for_leaked_secrets.py").read_text(encoding="utf-8")
    assert "sa_scanner.py" in source and "scan_text" in source
    assert "rm -f /tmp/sa_scanner.py" in source, "跑完没把扫描器从生产删掉"
