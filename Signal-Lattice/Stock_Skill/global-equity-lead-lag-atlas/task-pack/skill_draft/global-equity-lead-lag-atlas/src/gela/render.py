from __future__ import annotations

import csv
import json
import shutil
import tempfile
import uuid
from pathlib import Path
from typing import Any

from .io import config_to_public_dict, file_sha256
from .models import AnalysisConfig

REQUIRED_OUTPUTS = (
    "analysis.json",
    "co_movement.csv",
    "correlation_matrix.csv",
    "hypotheses.csv",
    "edges.csv",
    "matrix.csv",
    "quality_report.json",
    "provenance.json",
    "visualization_spec.json",
    "summary.md",
    "atlas.html",
)


def _write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            normalized = {
                key: json.dumps(value, ensure_ascii=False) if isinstance(value, (list, dict)) else value
                for key, value in row.items()
            }
            writer.writerow(normalized)


def _correlation_matrix(result: dict[str, Any]) -> tuple[list[dict[str, Any]], list[str]]:
    market_ids = sorted(item["market_id"] for item in result["markets"])
    by_key: dict[tuple[int, str, str], dict[str, Any]] = {}
    for item in result["co_movement"]:
        by_key[(item["horizon"], item["market_a"], item["market_b"])] = item
    rows: list[dict[str, Any]] = []
    horizons = sorted({item["horizon"] for item in result["co_movement"]})
    for horizon in horizons:
        for market_a in market_ids:
            row: dict[str, Any] = {"horizon": horizon, "market_id": market_a}
            for market_b in market_ids:
                if market_a == market_b:
                    row[market_b] = 1.0
                    continue
                left, right = sorted((market_a, market_b))
                item = by_key.get((horizon, left, right))
                row[market_b] = "" if item is None or item["pearson_r"] is None else item["pearson_r"]
            rows.append(row)
    return rows, ["horizon", "market_id", *market_ids]


def _summary(result: dict[str, Any]) -> str:
    counts = result["counts"]
    lines = [
        f"# {result['analysis_id']} 分析摘要",
        "",
        "## 结论",
        "",
        f"- 市场数：{counts['markets']}",
        f"- 同期相关检验：{counts['co_movement_hypotheses']}",
        f"- 已确认同期相关：{counts['confirmed_co_movements']}",
        f"- 时延假设：{counts['lead_lag_hypotheses']}",
        f"- 已确认方向边：{counts['confirmed_lead_lag_edges']}",
        "",
    ]
    if result["confirmed_co_movements"]:
        lines.extend(["## 已确认同期相关", ""])
        ranked = sorted(
            result["confirmed_co_movements"],
            key=lambda item: abs(item["pearson_r"] or 0.0),
            reverse=True,
        )
        for item in ranked[:20]:
            lines.append(
                f"- `{item['market_a']} ↔ {item['market_b']}`；尺度 {item['horizon']}；"
                f"r={item['pearson_r']:.4f}；q={item['q_value']:.4g}；"
                f"稳定性={item['rolling_sign_stability']:.3f}。"
            )
        lines.append("")
    else:
        lines.extend([
            "> 未发现满足样本量、FDR、效应量、区块 Bootstrap 与滚动稳定性全部条件的同期相关。",
            "",
        ])
    if result["confirmed_edges"]:
        lines.extend(["## 已确认时延方向边", ""])
        for edge in result["confirmed_edges"]:
            lines.append(
                f"- `{edge['source_market']} → {edge['target_market']}`；"
                f"尺度 {edge['horizon']}；额外滞后 {edge['source_lag']}；"
                f"r={edge['pearson_r']:.4f}；q={edge['q_value']:.4g}；"
                f"OOS 改进={edge['oos_mse_improvement']:.4f}。"
            )
        lines.append("")
    else:
        lines.extend([
            "> 未发现满足样本量、FDR、效应量、区块 Bootstrap、滚动稳定性与样本外改进全部条件的方向性关系。",
            "",
        ])
    lines.extend([
        "## 解释边界",
        "",
        "- 同期相关按双方声明的 `session_date` 对齐，只描述共同变动，不表示谁先谁后。",
        "- `horizon` 是累计收益尺度，不是领先长度。",
        "- `source_lag` 是来源市场额外后移的会话数。",
        "- `median_wall_clock_lead_hours` 是来源收盘到目标开盘的真实小时中位数。",
        "- 统计相关或领先不等于现实因果，也不构成投资建议。",
        "",
    ])
    return "\n".join(lines)


def _html_document(result: dict[str, Any]) -> str:
    payload = json.dumps(result, ensure_ascii=False).replace("</", "<\\/")
    template = r'''<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>全球股市时序联动图谱</title>
<style>
:root{--bg:#0b1020;--panel:#121a2f;--line:#33415f;--text:#e8edf8;--muted:#9aa7bd;--accent:#7dd3fc;--corr:#86efac;--negative:#fca5a5}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font:14px/1.5 system-ui,-apple-system,"PingFang SC","Microsoft YaHei",sans-serif}
header{padding:24px 28px;border-bottom:1px solid var(--line)}h1{margin:0 0 6px;font-size:25px}.sub{color:var(--muted)}
.controls{display:flex;gap:12px;flex-wrap:wrap;margin-top:16px}label{color:var(--muted)}select{background:#0e162b;color:var(--text);border:1px solid var(--line);padding:7px 10px;border-radius:8px}
main{display:grid;grid-template-columns:minmax(0,2fr) minmax(340px,1fr);gap:16px;padding:16px}.panel{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:16px;overflow:auto}
#map{width:100%;min-height:460px}svg{width:100%;height:460px;background:linear-gradient(180deg,#0e1830,#0c1427);border-radius:8px}
.grid{stroke:#273552;stroke-width:1}.edge-lead{stroke:var(--accent);fill:none;opacity:.75}.edge-corr{stroke:var(--corr);fill:none;opacity:.68}.edge-negative{stroke:var(--negative);stroke-dasharray:7 5}.node{fill:#f8fafc;stroke:#0b1020;stroke-width:2}.label{fill:#dbeafe;font-size:12px}
table{width:100%;border-collapse:collapse}th,td{padding:8px 9px;border-bottom:1px solid #26334f;text-align:left;white-space:nowrap}th{color:#bae6fd;position:sticky;top:0;background:var(--panel)}tbody tr{cursor:pointer}tbody tr:hover{background:#18233c}
.kpi{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-bottom:12px}.kpi div{background:#0e162b;border:1px solid #26334f;padding:10px;border-radius:9px}.kpi strong{display:block;font-size:20px}
.notice{border-left:3px solid #fbbf24;padding:9px 12px;background:#241d0e;color:#fde68a;margin-top:12px}.empty{color:var(--muted);padding:30px;text-align:center}.legend{color:var(--muted);margin:8px 0 0}
@media(max-width:900px){main{grid-template-columns:1fr}}
</style>
</head>
<body>
<header>
<h1>全球股市时序联动图谱</h1>
<div class="sub">Global Equity Lead–Lag Atlas · 同期相关与会话感知时延证据，不代表现实因果</div>
<div class="controls">
<label>视图 <select id="mode"><option value="lead_lag">时延方向</option><option value="co_movement">同期相关</option></select></label>
<label>收益尺度 <select id="horizon"></select></label>
<label>状态 <select id="status"><option value="all">全部结果</option><option value="confirmed">仅已确认</option></select></label>
</div>
</header>
<main>
<section class="panel"><div class="kpi" id="kpi"></div><div id="map"></div><div class="legend" id="legend"></div><div class="notice" id="notice"></div></section>
<section class="panel"><h2 id="table-title">关系</h2><div id="table"></div></section>
<section class="panel" style="grid-column:1/-1"><h2>选中关系证据</h2><pre id="detail" style="white-space:pre-wrap;color:#cbd5e1"></pre></section>
</main>
<script type="application/json" id="gela-data">__PAYLOAD__</script>
<script>
const data=JSON.parse(document.getElementById('gela-data').textContent);
const allItems=[...(data.best_candidates||[]),...(data.co_movement||[])];
const horizons=[...new Set(allItems.map(x=>x.horizon))].sort((a,b)=>a-b);
const hSelect=document.getElementById('horizon');horizons.forEach(h=>{const o=document.createElement('option');o.value=h;o.textContent=h+' 个交易时段';hSelect.appendChild(o)});
const modeSelect=document.getElementById('mode');
const statusSelect=document.getElementById('status');
const markets=Object.fromEntries(data.markets.map(m=>[m.market_id,m]));
function esc(s){return String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}
function project(lon,lat,w,h){return [(Number(lon)+180)/360*w,(90-Number(lat))/180*h]}
function currentRows(){const h=Number(hSelect.value);let rows=(modeSelect.value==='co_movement'?data.co_movement:data.best_candidates).filter(x=>x.horizon===h);if(statusSelect.value==='confirmed')rows=rows.filter(x=>x.status==='CONFIRMED');return rows.slice()}
function endpoints(item){return modeSelect.value==='co_movement'?[item.market_a,item.market_b]:[item.source_market,item.target_market]}
function render(){const rows=currentRows();const confirmed=rows.filter(x=>x.status==='CONFIRMED');const noun=modeSelect.value==='co_movement'?'市场对':'方向候选';document.getElementById('kpi').innerHTML=`<div><span>市场</span><strong>${data.counts.markets}</strong></div><div><span>当前${noun}</span><strong>${rows.length}</strong></div><div><span>已确认</span><strong>${confirmed.length}</strong></div>`;renderMap(confirmed);renderTable(rows);document.getElementById('table-title').textContent=modeSelect.value==='co_movement'?'同期相关市场对':'时延方向关系';document.getElementById('legend').textContent=modeSelect.value==='co_movement'?'实线为正相关，虚线为负相关；线宽表示 |r|。':'箭头从来源市场指向目标市场；线宽表示 |r|。';document.getElementById('notice').textContent=modeSelect.value==='co_movement'?'同期相关按双方 session_date 对齐，只描述共同变动，不能判断先行者。':'箭头只表示来源收盘在目标开盘前可得且通过冻结统计门；不构成交易建议。'}
function renderMap(edges){const w=1000,h=460;let s=`<svg viewBox="0 0 ${w} ${h}" role="img" aria-label="全球股市联动图"><defs><marker id="arrow" markerWidth="8" markerHeight="8" refX="7" refY="3" orient="auto"><path d="M0,0 L0,6 L8,3 z" fill="#7dd3fc"/></marker></defs>`;[-120,-60,0,60,120].forEach(l=>{const [x]=project(l,0,w,h);s+=`<line class="grid" x1="${x}" y1="0" x2="${x}" y2="${h}"/>`});[-60,-30,0,30,60].forEach(l=>{const [,y]=project(0,l,w,h);s+=`<line class="grid" x1="0" y1="${y}" x2="${w}" y2="${y}"/>`});edges.forEach(e=>{const [aId,bId]=endpoints(e),a=markets[aId],b=markets[bId];if(!a||!b)return;const [x1,y1]=project(a.longitude,a.latitude,w,h),[x2,y2]=project(b.longitude,b.latitude,w,h);const width=1.5+Math.min(7,Math.abs(e.pearson_r||0)*6);if(modeSelect.value==='co_movement'){const neg=(e.pearson_r||0)<0?' edge-negative':'';s+=`<line class="edge-corr${neg}" x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}" stroke-width="${width}"/>`}else{s+=`<line class="edge-lead" x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}" stroke-width="${width}" marker-end="url(#arrow)"/>`}});data.markets.forEach(m=>{const [x,y]=project(m.longitude,m.latitude,w,h);s+=`<circle class="node" cx="${x}" cy="${y}" r="5"><title>${esc(m.country_name_zh)} · ${esc(m.index_name)}</title></circle><text class="label" x="${x+7}" y="${y-7}">${esc(m.country_name_zh)}</text>`});s+='</svg>';document.getElementById('map').innerHTML=s}
function renderTable(rows){if(!rows.length){document.getElementById('table').innerHTML='<div class="empty">当前过滤器下无关系</div>';document.getElementById('detail').textContent='';return}rows.sort((a,b)=>Math.abs(b.pearson_r||0)-Math.abs(a.pearson_r||0));let t;if(modeSelect.value==='co_movement'){t='<table><thead><tr><th>市场对</th><th>r</th><th>q</th><th>有效 N</th><th>状态</th></tr></thead><tbody>';rows.forEach((r,i)=>{t+=`<tr data-i="${i}"><td>${esc(r.market_a)} ↔ ${esc(r.market_b)}</td><td>${r.pearson_r==null?'—':r.pearson_r.toFixed(3)}</td><td>${r.q_value==null?'—':r.q_value.toExponential(2)}</td><td>${r.n_effective}</td><td>${esc(r.status)}</td></tr>`})}else{t='<table><thead><tr><th>来源 → 目标</th><th>r</th><th>q</th><th>额外滞后</th><th>小时</th><th>状态</th></tr></thead><tbody>';rows.forEach((r,i)=>{t+=`<tr data-i="${i}"><td>${esc(r.source_market)} → ${esc(r.target_market)}</td><td>${r.pearson_r==null?'—':r.pearson_r.toFixed(3)}</td><td>${r.q_value==null?'—':r.q_value.toExponential(2)}</td><td>${r.source_lag}</td><td>${r.median_wall_clock_lead_hours==null?'—':r.median_wall_clock_lead_hours.toFixed(1)}</td><td>${esc(r.status)}</td></tr>`})}t+='</tbody></table>';document.getElementById('table').innerHTML=t;[...document.querySelectorAll('tbody tr')].forEach((tr,i)=>tr.onclick=()=>{document.getElementById('detail').textContent=JSON.stringify(rows[i],null,2)});document.getElementById('detail').textContent=JSON.stringify(rows[0],null,2)}
hSelect.onchange=render;modeSelect.onchange=render;statusSelect.onchange=render;render();
</script>
</body></html>'''
    return template.replace("__PAYLOAD__", payload)


def _assert_replaceable_output(output: Path) -> None:
    if output.is_symlink():
        raise ValueError(f"output_dir 不得是符号链接: {output}")
    if not output.exists():
        return
    if not output.is_dir():
        raise ValueError(f"output_dir 已存在但不是目录: {output}")
    entries = list(output.rglob("*"))
    symlinks = [path.relative_to(output).as_posix() for path in entries if path.is_symlink()]
    if symlinks:
        raise ValueError(f"output_dir 不得包含符号链接: {symlinks}")
    actual = {
        path.relative_to(output).as_posix()
        for path in entries
        if path.is_file()
    }
    nested_dirs = [path for path in entries if path.is_dir()]
    unexpected = sorted(actual.difference(REQUIRED_OUTPUTS))
    missing = sorted(set(REQUIRED_OUTPUTS).difference(actual))
    if nested_dirs or unexpected or (actual and missing):
        raise ValueError(
            "output_dir 必须为空或仅包含一套完整旧版 GELA 输出；"
            f" unexpected={unexpected}, missing={missing}, nested_dirs={len(nested_dirs)}"
        )


def _render_into(
    output: Path,
    result: dict[str, Any],
    config: AnalysisConfig,
    input_sha256: str,
    config_sha256: str,
    input_warnings: list[str],
) -> None:
    _write_json(output / "analysis.json", result)
    co_fields = [
        "pair_id", "market_a", "market_b", "horizon", "alignment", "n_raw", "n_effective",
        "pearson_r", "spearman_r", "p_value", "q_value", "ci_low", "ci_high",
        "rolling_sign_stability", "status", "failure_reasons",
    ]
    _write_csv(output / "co_movement.csv", result["co_movement"], co_fields)
    matrix_rows, matrix_fields = _correlation_matrix(result)
    _write_csv(output / "correlation_matrix.csv", matrix_rows, matrix_fields)
    hypothesis_fields = [
        "hypothesis_id", "source_market", "target_market", "horizon", "source_lag",
        "n_raw", "n_effective", "median_wall_clock_lead_hours", "pearson_r", "spearman_r",
        "p_value", "q_value", "ci_low", "ci_high", "rolling_sign_stability",
        "oos_mse_improvement", "status", "failure_reasons",
    ]
    _write_csv(output / "hypotheses.csv", result["hypotheses"], hypothesis_fields)
    _write_csv(output / "edges.csv", result["confirmed_edges"], hypothesis_fields)
    _write_csv(output / "matrix.csv", result["best_candidates"], hypothesis_fields)
    quality = {
        "schema_version": "1.0",
        "analysis_id": config.analysis_id,
        "status": "PASS" if not input_warnings else "PASS_WITH_WARNINGS",
        "warnings": input_warnings,
        "checks": {
            "minimum_two_markets": True,
            "strict_utc_session_order": True,
            "unique_market_session": True,
            "positive_close": True,
            "cash_index_only": True,
            "single_return_type": True,
            "source_retrieval_not_before_close": True,
            "co_movement_alignment_declared": True,
            "causal_claims_disabled": True,
            "license_acknowledgement": True,
        },
    }
    _write_json(output / "quality_report.json", quality)
    provenance = {
        "schema_version": "1.0",
        "analysis_id": config.analysis_id,
        "input_sha256": input_sha256,
        "config_sha256": config_sha256,
        "config": config_to_public_dict(config),
        "data_policy": "输入数据由宿主提供；Skill 不重新分发真实行情，不将运行结果写入代码仓。",
    }
    _write_json(output / "provenance.json", provenance)
    spec = {
        "schema_version": "1.0",
        "views": ["global_co_movement_map", "global_directed_lead_lag_map", "relationship_table", "evidence_detail"],
        "filters": ["mode", "horizon", "status"],
        "offline": True,
        "external_assets": [],
        "claim_boundary": result["claim_boundary"],
    }
    _write_json(output / "visualization_spec.json", spec)
    (output / "summary.md").write_text(_summary(result), encoding="utf-8")
    (output / "atlas.html").write_text(_html_document(result), encoding="utf-8")


def render_outputs(
    result: dict[str, Any],
    config: AnalysisConfig,
    input_sha256: str,
    config_sha256: str,
    input_warnings: list[str],
) -> Path:
    output = config.output_dir
    output.parent.mkdir(parents=True, exist_ok=True)
    _assert_replaceable_output(output)
    temporary = Path(tempfile.mkdtemp(prefix=f".{output.name}.gela-stage-", dir=output.parent))
    backup: Path | None = None
    try:
        _render_into(temporary, result, config, input_sha256, config_sha256, input_warnings)
        if output.exists():
            backup = output.parent / f".{output.name}.gela-backup-{uuid.uuid4().hex}"
            output.replace(backup)
        try:
            temporary.replace(output)
        except Exception:
            if backup is not None and backup.exists() and not output.exists():
                backup.replace(output)
            raise
        if backup is not None:
            shutil.rmtree(backup, ignore_errors=True)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    return output


def output_inventory(output: Path) -> dict[str, Any]:
    files = []
    for name in REQUIRED_OUTPUTS:
        path = output / name
        files.append({"path": name, "size": path.stat().st_size, "sha256": file_sha256(path)})
    return {"files": files}
