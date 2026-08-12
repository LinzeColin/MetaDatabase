"""adp-cloud 部署的判断逻辑（不做 IO，好让反例打得红）。

背景（2026-08-12，WeReadPort）：照仓里的 wrangler 配置裸跑 `wrangler deploy`，
把线上 8 个 plain_text 变量全清了，站点当场断了 3 分钟。
根因是 **`wrangler deploy` 用配置文件的内容替换线上 vars，不是合并**；
secret 会自动保留，plain_text 不会 —— 这个不对称最容易漏。

adp-cloud 今天线上是 0 个 plain_text、0 个 secret（只有 D1 + R2，且都写在
wrangler_cloud.jsonc 里），所以裸跑**目前**不会丢东西。但
「今天没有」不等于「以后也不会有」：哪天有人在 dashboard 上加一个变量，
下一次裸跑就会把它清掉，而且不会有任何报错。这里把守卫先立上。
"""

from __future__ import annotations

import hashlib
import re

#: BUILD 常量那一行；build_id 是抠掉这一行之后对源码算的 sha256 前 12 位。
BUILD_LINE = re.compile(r"^const BUILD = \{.*?\};$", re.M)


def compute_build_id(worker_source: str) -> tuple[str, str]:
    """返回 (build_id, source_sha256)。

    抠掉 BUILD 行本身再算，避免自指：同一份源码永远算出同一个 id，
    而任何一处改动都必然让它变。跟着版本号走会被「改了却忘升版」绕开。
    """
    matches = BUILD_LINE.findall(worker_source)
    if len(matches) != 1:
        raise ValueError(f"worker 源码里应恰好有 1 行 BUILD 常量，实际 {len(matches)} 行")
    neutral = BUILD_LINE.sub("const BUILD = <SELF>;", worker_source)
    digest = hashlib.sha256(neutral.encode("utf-8")).hexdigest()
    return digest[:12], digest


def render_build_line(build_id: str, source_sha256: str, built_at: str) -> str:
    return (
        f"const BUILD = {{ build_id: '{build_id}', source_sha256: '{source_sha256}', "
        f"schema_version: 'cn_v0_3', built_at: '{built_at}' }};"
    )


def current_build_id(worker_source: str) -> str:
    """读出 BUILD 行里当前写着的 build_id（读不出来返回空串）。"""
    matches = BUILD_LINE.findall(worker_source)
    if len(matches) != 1:
        return ""
    found = re.search(r"build_id:\s*'([0-9a-f]+)'", matches[0])
    return found.group(1) if found else ""


def stamp_build(worker_source: str, built_at: str) -> tuple[str, str]:
    """把 BUILD 行改成与当前源码一致；返回 (新源码, build_id)。

    **只按 build_id 判断要不要改。** 第一版把 built_at 也一起重写，于是代码一个字
    没动、只是换了一天，脚本就报「BUILD 与源码不一致」把部署拦下 —— 一道每天早上
    必红一次的门等于没有门。日期只在 build_id 真的变了时才跟着更新。
    """
    build_id, source_sha256 = compute_build_id(worker_source)
    if current_build_id(worker_source) == build_id:
        return worker_source, build_id
    stamped = BUILD_LINE.sub(
        lambda _: render_build_line(build_id, source_sha256, built_at), worker_source
    )
    return stamped, build_id


def collect_plain_text_vars(bindings) -> dict[str, str]:
    """从某个 worker 版本的 bindings 里取出 plain_text 变量。"""
    out: dict[str, str] = {}
    for binding in bindings or []:
        if not isinstance(binding, dict) or binding.get("type") != "plain_text":
            continue
        name = binding.get("name")
        if isinstance(name, str) and name:
            out[name] = binding.get("text") or ""
    return out


def pick_current_deployment(deployments) -> str:
    """挑当前正在跑的版本。

    别用 [0] 也别用 [-1]：`wrangler deployments list` 打印是升序（最老在前），
    而 REST API 返回是降序（最新在前）。按 created_on 排，不依赖任一端的顺序约定。
    """
    rows = []
    for item in deployments or []:
        versions = (item or {}).get("versions") or []
        if not versions or not versions[0].get("version_id"):
            continue
        rows.append((item.get("created_on") or "", versions[0]["version_id"]))
    if not rows:
        raise ValueError("取不到当前线上版本 id。")
    rows.sort(reverse=True)
    return rows[0][1]


def vars_to_carry(live_vars: dict[str, str], declared_in_config: set[str]) -> list[tuple[str, str]]:
    """线上有、而 wrangler 配置里没有的 plain_text 变量 —— 这些必须显式带回去。

    配置里已声明的不用带（wrangler 自己会写），带了反而可能和配置冲突。
    """
    return sorted(
        (name, value) for name, value in live_vars.items() if name not in declared_in_config
    )


def assert_no_empty_carry(carry: list[tuple[str, str]]) -> None:
    """线上变量存在但值为空 —— 拒绝部署，空值等于没有。"""
    empty = [name for name, value in carry if not str(value).strip()]
    if empty:
        raise ValueError(f"线上变量为空：{'、'.join(empty)}。不部署。")


def check_live_build(build_json, expected_build_id: str) -> list[str]:
    """部署后回读 /build.json：线上跑的必须就是刚构建的这份源码。"""
    problems: list[str] = []
    live = str((build_json or {}).get("build_id") or "").strip()
    if not live:
        problems.append("/build.json 没有 build_id")
    elif live != expected_build_id:
        problems.append(f"/build.json 的 build_id 是 {live}，不是刚部署的 {expected_build_id}")
    return problems


def redact(text: str, secrets) -> str:
    """任何要打印的文本先过这里：变量值一律不进日志。"""
    output = str(text or "")
    for name, value in secrets:
        if isinstance(value, str) and len(value) >= 4:
            output = output.replace(value, f"<{name}>")
    return output
