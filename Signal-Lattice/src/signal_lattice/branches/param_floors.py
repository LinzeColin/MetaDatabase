"""远端参数只许收紧、不许放宽：各分支 validate_params 在 schema 校验之外，再核对「关键门槛」不低于仓库内的默认值。

为什么：参数是从 GitHub 远端拉的，远端被改坏（或被人误改）时，schema 校验只看形状与取值范围，
一个「合法但更宽松」的参数（例如把发布门槛从 75 改成 10）会悄悄生效。仓库内默认值是随代码发布、经过评审的，
远端只能在它之上收紧。

规则种类：
  min    值不得低于默认（阈值越高越严的门槛）
  max    值不得高于默认（阈值越低越严的门槛，如增发同比阈值）
  subset 列表必须是默认列表的子集（只许少认，不许多认，如允许触发 PASS 的事件类）
"""

from __future__ import annotations

from typing import Any, Callable, Dict, Mapping, Tuple

Floors = Mapping[str, Tuple[str, Any]]


def _dig(params: Mapping, path: str) -> Any:
    value: Any = params
    for part in path.split("."):
        if not isinstance(value, Mapping) or part not in value:
            raise KeyError(path)
        value = value[part]
    return value


def floors_from_defaults(defaults: Mapping, rules: Mapping[str, str]) -> Dict[str, Tuple[str, Any]]:
    """rules：{路径: "min"|"max"|"subset"}；界限取自默认值。路径末尾是 * 表示该字典下的每一项。"""
    floors: Dict[str, Tuple[str, Any]] = {}
    for path, kind in rules.items():
        if path.endswith(".*"):
            base = path[:-2]
            for key in _dig(defaults, base):
                floors["%s.%s" % (base, key)] = (kind, _dig(defaults, "%s.%s" % (base, key)))
        else:
            floors[path] = (kind, _dig(defaults, path))
    return floors


def enforce_not_looser(params: Mapping, floors: Floors, error: Callable[[str], Exception], skill: str) -> None:
    for path, (kind, limit) in floors.items():
        try:
            value = _dig(params, path)
        except KeyError:
            raise error("%s：缺少关键门槛 %s" % (skill, path)) from None
        if kind == "subset":
            if not isinstance(value, list) or not set(value) <= set(limit):
                raise error("%s 参数放宽了门槛：%s = %s 超出仓库默认 %s（只允许收紧，不允许放宽）" % (skill, path, value, sorted(limit)))
            continue
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise error("%s：%s 必须是数字" % (skill, path))
        if (kind == "min" and value < limit) or (kind == "max" and value > limit):
            raise error("%s 参数放宽了门槛：%s = %s %s 仓库默认 %s（只允许收紧，不允许放宽）" % (
                skill, path, value, "低于" if kind == "min" else "高于", limit))
