#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
render_human.py —— 从机器平面渲染人类平面七文件

双平面原则：
- 机器平面 machine/facts/*.json 是唯一事实源。
- 人类平面 文档/ 是渲染产物，不是手写产物。
- 例外：文档/01_产品需求.md 和 文档/03_口径字典.md 是 Owner 手写区，
  本渲染器只读、绝不覆盖。渲染时会校验它们存在且非空。

为什么人类平面必须渲染而不能手写（见 交接给ClaudeCode.md）：
  「功能清单里没有功能」的根因是它允许被手写。任何允许 agent 手写的
  人类可读文件，最终必然退化成 append-only 日志。这是结构决定的。

事实源约定（每个渲染文件的头注释也声明了同一份映射）：
  00_我在哪.md      <- facts/status.json, facts/blockers.json, facts/roadmap.json
  02_系统架构.md    <- facts/features.json, facts/data_contract.yaml, facts/config.yaml
  04_操作流程.md    <- facts/flows.json
  05_执行与验收.md  <- facts/plan.json, facts/acceptance.json, runs/*.json
  06_运维手册.md    <- facts/config.yaml, facts/ops.json, facts/changelog.json

缺失的事实源不会让渲染崩溃：渲染出的对应章节标记为 `UNKNOWN`，
随后三道门（check_doc_budget / check_blocker_stop）据此判 FAIL。
「绿的门是假门」——事实没接通时，人类平面就应显示 UNKNOWN 并让门保持红。

用法:  python3 machine/tools/render_human.py [--root .] [--check]
  --check  只校验手写区存在与非空，不写文件（供 CI 用）
退出码: 0=渲染完成  1=手写区缺失或为空
"""
import argparse
import json
import sys
from pathlib import Path

GENERATED = (
    "<!-- 本文件由 machine/tools/render_human.py 生成。手写内容会在下次渲染时被覆盖。 -->"
)
HANDWRITTEN = {"01_产品需求.md", "03_口径字典.md"}
UNKNOWN = "`UNKNOWN`（事实源缺失，待机器平面接通）"

# 口径字典占位骨架。第六节预登记通用治理术语，使中文门对它们豁免。
# 这些是跨项目通用的治理词汇；项目专属术语由 Owner 在本文件补登。
GLOSSARY_SKELETON = """<!-- 手写区。render_human.py 只读此文件，不会覆盖。 -->
<!-- 这是全项目唯一裁定"一个数字是什么"的地方。有争议以本文件为准。 -->
<!-- 中文门规则：人类平面正文出现的任何英文术语，必须在本文件第六节有条目，否则渲染 FAIL。 -->

# 口径字典

> 状态：**待你（项目负责人）裁定**。以下为骨架，请逐条补全。

## 一、关键数字口径

| 项 | 裁定 | 状态 |
|---|---|---|
| — | 待裁定 | 待补 |

## 二、外部数据形态

| 来源 | 必须长什么样 | 状态 |
|---|---|---|
| — | 待裁定 | 待补 |

## 三、恒定为真的规则

| 规则 | 说明 |
|---|---|
| — | 待补 |

## 四、证据等级定义

| 等级 | 含义 |
|---|---|
| `已提取` | 从代码/配置提取并核对 |
| `已声明` | 只有文档说法，未核对 |

## 五、报告等级定义

| 等级 | 含义 |
|---|---|
| — | 待裁定 |

## 六、术语对照

> 人类平面正文出现的英文术语必须在此登记，否则中文门 FAIL。

| 英文 | 中文 | 说明 |
|---|---|---|
| Owner | 负责人 | 项目/产品的决策与验收责任人 |
| Stage | 阶段 | 路线图一级单元 |
| Phase | 步骤 | 阶段下的二级单元 |
| Task | 任务 | 步骤下的三级单元 |
| Roadmap | 路线图 | 阶段→步骤→任务的完整计划 |
"""


def load_json(path: Path, default):
    """读一个 JSON 事实源；缺失或损坏时返回 default（渲染成 UNKNOWN）。"""
    if not path.is_file():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return default


def load_yaml_or_json(path: Path, default):
    """config/data_contract 允许 yaml；无 yaml 库时退化为只读文本存在性。"""
    if not path.is_file():
        return default
    text = path.read_text(encoding="utf-8")
    try:
        import yaml  # noqa
        return yaml.safe_load(text) or default
    except Exception:
        # 没有 yaml 库也不阻塞渲染：返回原始文本，调用方只判存在性
        return {"_raw": text}


def table(rows, header):
    """把 [(a,b,...)] 渲染成 markdown 表。空 rows -> UNKNOWN 占位行。"""
    out = ["| " + " | ".join(header) + " |",
           "|" + "|".join(["---"] * len(header)) + "|"]
    if not rows:
        out.append("| " + " | ".join([UNKNOWN] + [""] * (len(header) - 1)) + " |")
    else:
        for r in rows:
            out.append("| " + " | ".join(str(c) for c in r) + " |")
    return "\n".join(out)


# ---------- 各文件渲染器 ----------

def render_00(facts: Path):
    status = load_json(facts / "status.json", {})
    blockers = load_json(facts / "blockers.json", [])
    roadmap = load_json(facts / "roadmap.json", {})
    src_commit = status.get("facts_commit", "未知（待本机渲染写入）")

    state_rows = [
        ("产品版本", f"`{status.get('version', 'UNKNOWN')}`"),
        ("当前阶段", f"`{status.get('stage', 'UNKNOWN')}`"),
        ("当前步骤", f"`{status.get('phase', 'UNKNOWN')}`"),
        ("当前任务", f"`{status.get('task', '无进行中任务')}`"),
        ("真实进度", status.get("real_progress", UNKNOWN)),
        ("报告等级", f"`{status.get('report_grade', 'UNKNOWN')}`"),
        ("业务判定", f"`{status.get('business_verdict', 'UNKNOWN')}`"),
        ("阻塞", f"{len(blockers)} 项" if blockers else "0 项"),
    ]
    blk_rows = [
        (b.get("id", "?"), b.get("内容", b.get("desc", "")),
         "**你（Owner）**" if b.get("owner_only") else b.get("owner", "?"),
         b.get("首次登记", b.get("since", "?")))
        for b in blockers
    ]
    rm_rows = [
        (s.get("id", "?"), s.get("name", ""), s.get("gate", ""), s.get("status", ""))
        for s in roadmap.get("stages", [])
    ]

    body = f"""{GENERATED}
<!-- 事实源：machine/facts/status.json、blockers.json、roadmap.json -->
<!-- 上限 120 行 -->

# 我在哪

**渲染时间：** {status.get('rendered_at', '待渲染')}　|　**事实源提交：** `{src_commit}`

## 一、当前状态

{table(state_rows, ["项", "值"])}

## 二、唯一阻塞

{table(blk_rows, ["编号", "内容", "谁能解", "卡住多久"])}

## 三、路线图

{table(rm_rows, ["阶段", "名称", "核心门禁", "状态"])}

## 四、其余文件读什么

| 文件 | 回答什么问题 | 谁写 |
|---|---|---|
| `01_产品需求.md` | 为谁做、解决什么、不做什么 | 你手写 |
| `02_系统架构.md` | 有哪些功能、数据流、依赖、参数意图 | 渲染 |
| `03_口径字典.md` | 每个数字怎么算、外部数据长什么样 | 你裁定 |
| `04_操作流程.md` | 业务一步步怎么走 | 渲染 |
| `05_执行与验收.md` | 这次做什么、怎么算做完 | 渲染 |
| `06_运维手册.md` | 怎么跑、参数改哪、报错怎么办 | 渲染 |
"""
    return body


def render_02(facts: Path):
    features = load_json(facts / "features.json", [])
    config = load_yaml_or_json(facts / "config.yaml", {})
    contract = load_yaml_or_json(facts / "data_contract.yaml", {})

    STATUS_ZH = {"active": "进行中", "in_progress": "进行中", "completed": "已完成",
                 "done": "已完成", "planned": "计划中", "blocked": "阻塞",
                 "deprecated": "已弃用", "draft": "草案", "pending": "待办"}
    feat_rows = [
        (f"`{f.get('id', '?')}`", f.get("name", ""),
         STATUS_ZH.get(f.get("status", ""), f.get("status", "")),
         "已提取" if f.get("evidence") == "extracted" else "已声明")
        for f in features
    ]
    cfg = config if isinstance(config, dict) and "_raw" not in config else {}
    param_rows = [(k, v.get("intent", "") if isinstance(v, dict) else "")
                  for k, v in cfg.get("parameters", {}).items()] if cfg else []
    ent_rows = [(e.get("entity", "?"), ", ".join(e.get("keys", [])), e.get("pk", ""))
                for e in (contract.get("entities", []) if isinstance(contract, dict) else [])]

    body = f"""{GENERATED}
<!-- 事实源：machine/facts/features.json、data_contract.yaml、config.yaml -->
<!-- 上限 200 行 -->
<!-- 纯净门：本文件「一、功能清单」章节出现 phase/gate/review/replay/audit 等日志词 -> 渲染 FAIL -->

# 系统架构

## 一、功能清单

> 这里只放**功能**。步骤日志去 `05_执行与验收.md`。

{table(feat_rows, ["功能 ID", "名称", "状态", "证据等级"])}

**证据等级：** `已提取` = 从代码/配置提取并核对｜`已声明` = 只有文档说法，未核对

## 二、数据流

{contract.get('data_flow', UNKNOWN) if isinstance(contract, dict) else UNKNOWN}

## 三、配置参数（设计意图）

> 当前值和怎么改在 `06_运维手册.md`；这里只说为什么这么设。

{table(param_rows, ["参数", "为什么是这个值"])}

## 四、数据模型

{table(ent_rows, ["实体", "关键字段", "主键"])}
"""
    return body


def render_04(facts: Path):
    flows = load_json(facts / "flows.json", {})
    main_rows = [
        (s.get("step", "?"), s.get("who", ""), s.get("do", ""), s.get("out", ""))
        for s in flows.get("main", [])
    ]
    body = f"""{GENERATED}
<!-- 事实源：machine/facts/flows.json -->
<!-- 上限 150 行 -->

# 操作流程

> 业务规则在 `03_口径字典.md`，本文件只讲怎么走。

## 一、主流程

{table(main_rows, ["步", "谁", "做什么", "产出"])}
"""
    return body


def render_05(facts: Path, runs_dir: Path):
    plan = load_json(facts / "plan.json", {})
    acceptance = load_json(facts / "acceptance.json", {})
    runs = []
    if runs_dir.is_dir():
        for f in sorted(runs_dir.glob("*.json")):
            data = load_json(f, [])
            runs.extend(data if isinstance(data, list) else [data])

    now_rows = [
        ("阶段", plan.get("stage", UNKNOWN)),
        ("步骤", plan.get("phase", UNKNOWN)),
        ("任务", plan.get("task", UNKNOWN)),
        ("负责", plan.get("owner", UNKNOWN)),
    ]
    acc_rows = [(a.get("id", "?"), a.get("criteria", ""), a.get("status", ""))
                for a in acceptance.get("items", [])]
    run_rows = [(r.get("run_id", "?"), r.get("action", ""), r.get("result", ""))
                for r in runs[-20:]]

    body = f"""{GENERATED}
<!-- 事实源：machine/facts/plan.json、acceptance.json、runs/*.json -->
<!-- 上限 100 行 -->

# 执行与验收

## 一、这一次做什么

{table(now_rows, ["项", "值"])}

## 二、验收标准

{table(acc_rows, ["验收 ID", "怎么算做完", "状态"])}

## 三、实际做了什么（近 20 条）

{table(run_rows, ["运行", "动作", "结果"])}
"""
    return body


def render_06(facts: Path, project_name: str):
    config = load_yaml_or_json(facts / "config.yaml", {})
    ops = load_json(facts / "ops.json", {})
    changelog = load_json(facts / "changelog.json", [])

    cfg = config if isinstance(config, dict) and "_raw" not in config else {}
    param_rows = [(k, v.get("value", "") if isinstance(v, dict) else v,
                   v.get("where", "") if isinstance(v, dict) else "")
                  for k, v in cfg.get("parameters", {}).items()] if cfg else []
    err_rows = [(e.get("symptom", "?"), e.get("cause", ""), e.get("fix", ""))
                for e in ops.get("troubleshooting", [])]
    cl_rows = [(c.get("version", "?"), c.get("date", ""), c.get("summary", ""))
               for c in changelog[-10:]]

    body = f"""{GENERATED}
<!-- 事实源：machine/config.yaml、machine/facts/ops.json、changelog.json -->
<!-- 上限 200 行 -->

# 运维手册

## 一、怎么跑

```bash
python3 machine/tools/render_human.py            # 渲染人类平面（先跑这个）
python3 machine/tools/check_doc_budget.py        # 体积门 + 中文门 + 纯净门
python3 machine/tools/check_blocker_stop.py      # 阻塞重审门
```

## 二、参数当前值与改哪里

{table(param_rows, ["参数", "当前值", "改哪里"])}

## 三、报错怎么办

{table(err_rows, ["症状", "原因", "怎么修"])}

## 四、变更历史（近 10 条）

{table(cl_rows, ["版本", "日期", "摘要"])}
"""
    return body


# ---------- 主流程 ----------

def check_handwritten(docs: Path, failures: list):
    for name in sorted(HANDWRITTEN):
        f = docs / name
        if not f.is_file():
            failures.append(f"手写区缺失: 文档/{name}（Owner 必须提供）")
        elif len(f.read_text(encoding="utf-8").strip()) < 40:
            failures.append(f"手写区为空: 文档/{name}（Owner 必须填写）")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--check", action="store_true", help="只校验手写区，不写文件")
    args = ap.parse_args()

    root = Path(args.root)
    docs = root / "文档"
    facts = root / "machine" / "facts"
    runs = root / "machine" / "runs"
    project_name = root.resolve().name

    failures: list = []
    check_handwritten(docs, failures)
    if args.check:
        if failures:
            print("FAIL —— 手写区\n" + "\n".join("  ✗ " + x for x in failures))
            return 1
        print("PASS —— 手写区存在且非空")
        return 0

    docs.mkdir(parents=True, exist_ok=True)
    rendered = {
        "00_我在哪.md": render_00(facts),
        "02_系统架构.md": render_02(facts),
        "04_操作流程.md": render_04(facts),
        "05_执行与验收.md": render_05(facts, runs),
        "06_运维手册.md": render_06(facts, project_name),
    }
    for name, body in rendered.items():
        (docs / name).write_text(body.rstrip() + "\n", encoding="utf-8")

    # 手写区不存在时生成占位骨架（供 Owner 填），已存在则绝不覆盖
    for name in sorted(HANDWRITTEN):
        f = docs / name
        if not f.is_file():
            title = name.split("_", 1)[1].replace(".md", "")
            if name == "03_口径字典.md":
                f.write_text(GLOSSARY_SKELETON, encoding="utf-8")
            else:
                f.write_text(
                    "<!-- 手写区。render_human.py 只读此文件，不会覆盖。 -->\n"
                    "<!-- 上限 200 行。 -->\n\n# " + title + "\n\n"
                    "> 状态：**待你（项目负责人）填写并冻结**。\n",
                    encoding="utf-8",
                )

    print(f"渲染完成：{len(rendered)} 个渲染文件 + {len(HANDWRITTEN)} 个手写区已就绪")
    if failures:
        print("注意 —— 手写区待补：\n" + "\n".join("  · " + x for x in failures))
    return 0


if __name__ == "__main__":
    sys.exit(main())
