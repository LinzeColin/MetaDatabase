"use client";

// EEI-PULSE UI. Owner's verdict on the previous build was "数据根本没有更新" —
// and the workspace gave them no way to know otherwise: the hero counted the
// 6 nodes currently drawn, the "数据版本" line was a governance timestamp
// frozen ten days earlier, and nothing anywhere said when the collector last
// ran. These two components are the answer:
//
//   <PulseStrip/>      always-on: library scale, today's delta, live heartbeat
//   <PulseDashboard/>  the full picture: growth curve, windows, composition
//
// Both poll on an interval, so a number that changes is *seen* changing.

import { useCallback, useEffect, useRef, useState } from "react";

import {
  HEARTBEAT_LABEL,
  formatCount,
  formatDelta,
  formatLag,
  loadDataPulse,
  type PulseDay,
  type PulseRecord,
  type PulseResult
} from "../pulse-client";

const POLL_INTERVAL_MS = 60_000;

type MetricKey = "entities" | "relationships" | "events";

// ★这三个数说的是采集库，不是图上能看见的东西★
// 首屏此前把「实体 14,708 / 关系 14,576」和下面一行「当前视图 0 家实体 · 0 条关系」
// 并排放着，而 relationships 的说明还写着「已核实关系」——同一屏里「已核实关系」有两个
// 互相矛盾的意思。看的人只剩一个结论：这软件坏了。标签必须自己说清楚数的是哪一边。
const METRIC_LABEL: Record<MetricKey, string> = {
  entities: "采集库 · 实体",
  relationships: "采集库 · 关系",
  events: "采集库 · 事件"
};

const METRIC_HINT: Record<MetricKey, string> = {
  entities: "采集库里已建档的公司与机构（不等于图上画得出来）",
  relationships: "采集库里的关系候选，尚未经过 Owner 签核发布",
  events: "官方申报与披露事件"
};

function usePulse(days: number) {
  const [result, setResult] = useState<PulseResult | null>(null);
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);

  const refresh = useCallback(() => {
    let cancelled = false;
    void loadDataPulse(days).then((next) => {
      if (!cancelled) setResult(next);
    });
    return () => {
      cancelled = true;
    };
  }, [days]);

  useEffect(() => {
    const cancel = refresh();
    timer.current = setInterval(refresh, POLL_INTERVAL_MS);
    return () => {
      cancel();
      if (timer.current) clearInterval(timer.current);
    };
  }, [refresh]);

  return result;
}

// —— odometer ————————————————————————————————————————————————————————
// A number that silently swaps from 185,167 to 185,203 reads as static. Each
// digit that actually changed gets a short roll, so growth is perceived rather
// than merely displayed. Honours prefers-reduced-motion via --motion-scale.

function Odometer({ value, testId }: { value: number; testId?: string }) {
  const text = formatCount(value);
  const previous = useRef(text);
  const [changed, setChanged] = useState<Set<number>>(new Set());

  useEffect(() => {
    if (previous.current === text) return;
    const before = previous.current.padStart(text.length, " ");
    const next = new Set<number>();
    for (let i = 0; i < text.length; i += 1) {
      if (before[i] !== text[i]) next.add(i);
    }
    previous.current = text;
    setChanged(next);
    const handle = setTimeout(() => setChanged(new Set()), 700);
    return () => clearTimeout(handle);
  }, [text]);

  return (
    <span className="odometer" data-testid={testId}>
      {text.split("").map((char, index) => (
        <span
          className={`odometerDigit${changed.has(index) ? " rolled" : ""}`}
          // Digits have no identity beyond their position in the numeral.
          key={`${index}-${char}`}
        >
          {char}
        </span>
      ))}
    </span>
  );
}

function HeartbeatDot({ record }: { record: PulseRecord }) {
  const { state, lag_seconds: lag } = record.heartbeat;
  return (
    <span
      className={`pulseHeartbeat state-${state}`}
      data-state={state}
      data-testid="pulse-heartbeat"
      title={`采集器状态：${HEARTBEAT_LABEL[state]}（最后一次 ${formatLag(lag)}）`}
    >
      <i aria-hidden="true" />
      {HEARTBEAT_LABEL[state]} · {formatLag(lag)}
    </span>
  );
}

// —— the always-on strip ————————————————————————————————————————————

export function PulseStrip({
  days = 30,
  publishedRelationships = null
}: {
  days?: number;
  /** 已签核发布、图上真的画得出来的关系条数。null = 还没拿到，不是 0。 */
  publishedRelationships?: number | null;
}) {
  const result = usePulse(days);

  if (!result || result.status !== "hydrated") {
    // Honest placeholder: never invent a number, never show a stale one.
    return (
      <div className="pulseStrip loading" data-testid="pulse-strip" data-state={result?.status ?? "loading"}>
        <span className="pulseStripLoading">数据规模载入中…</span>
      </div>
    );
  }

  const { record } = result;
  const today = record.added.today;

  return (
    <div className="pulseStrip" data-testid="pulse-strip" data-state="hydrated">
      {(Object.keys(METRIC_LABEL) as MetricKey[]).map((key) => (
        <div className="pulseMetric" key={key} title={METRIC_HINT[key]}>
          <span className="pulseMetricLabel">{METRIC_LABEL[key]}</span>
          <Odometer testId={`pulse-total-${key}`} value={record.totals[key]} />
          <span
            className={`pulseDelta${today[key] > 0 ? " up" : ""}`}
            data-testid={`pulse-today-${key}`}
          >
            今日 {formatDelta(today[key])}
          </span>
        </div>
      ))}
      {/* 采集库有多大 ≠ 图上看得见多少。把两个数放在一起，任何一屏都不会再被读成
          「有 14,708 个实体但画不出来 = 坏了」。0 是真的 0，不是加载失败。 */}
      <div className="pulseMetric pulsePublished" title="已经过 Owner 签核发布、图上真的画得出来的关系条数">
        <span className="pulseMetricLabel">已发布到图上 · 关系</span>
        <span className="pulseMetricValue" data-testid="pulse-published-relationships">
          {publishedRelationships === null ? "载入中" : formatCount(publishedRelationships)}
        </span>
        {publishedRelationships === 0 ? (
          <span className="pulseDelta">图上暂时一条都没有</span>
        ) : null}
      </div>
      <div className="pulseStripTail">
        <HeartbeatDot record={record} />
        <a className="pulseStripLink" href="/objects-scope">
          数据全景 →
        </a>
      </div>
    </div>
  );
}

// —— growth chart ————————————————————————————————————————————————————
// Hand-drawn SVG rather than a chart dependency: one metric, one area, real
// axis labels. Cumulative totals as the area; daily arrivals as the bars, so
// "the library is big" and "it grew today" are legible in one glance.

function GrowthChart({ series, metric }: { series: PulseDay[]; metric: MetricKey }) {
  if (series.length < 2) {
    return (
      <p className="pulseChartEmpty">
        还只有 {series.length} 天的采集记录，曲线要到第二天才有意义。
      </p>
    );
  }
  const width = 720;
  const height = 220;
  const padLeft = 8;
  const padRight = 8;
  const padTop = 12;
  const padBottom = 26;

  const totals = series.map((d) => d[metric]);
  const added = series.map((d) => d[`${metric}_added` as keyof PulseDay] as number);
  const maxTotal = Math.max(...totals, 1);
  const maxAdded = Math.max(...added, 1);
  const innerW = width - padLeft - padRight;
  const innerH = height - padTop - padBottom;
  const x = (i: number) => padLeft + (innerW * i) / (series.length - 1);
  const y = (v: number) => padTop + innerH - (innerH * v) / maxTotal;

  const line = series.map((d, i) => `${i === 0 ? "M" : "L"}${x(i)},${y(d[metric])}`).join(" ");
  const area = `${line} L${x(series.length - 1)},${padTop + innerH} L${padLeft},${padTop + innerH} Z`;
  const barW = Math.max(1.5, innerW / series.length - 2);

  return (
    <figure className="pulseChart" data-testid="pulse-growth-chart">
      <svg role="img" viewBox={`0 0 ${width} ${height}`} aria-label={`${METRIC_LABEL[metric]}累计增长曲线`}>
        <defs>
          <linearGradient id={`pulseFill-${metric}`} x1="0" x2="0" y1="0" y2="1">
            <stop offset="0%" stopColor="var(--pulse-accent)" stopOpacity="0.34" />
            <stop offset="100%" stopColor="var(--pulse-accent)" stopOpacity="0" />
          </linearGradient>
        </defs>
        {/* daily arrivals — the part that answers "did anything come in today" */}
        {series.map((d, i) => {
          const value = d[`${metric}_added` as keyof PulseDay] as number;
          const h = value ? Math.max(2, (innerH * 0.42 * value) / maxAdded) : 0;
          return (
            <rect
              className="pulseChartBar"
              height={h}
              key={d.day}
              width={barW}
              x={x(i) - barW / 2}
              y={padTop + innerH - h}
            >
              <title>{`${d.day}：新增 ${formatCount(value)}`}</title>
            </rect>
          );
        })}
        <path className="pulseChartArea" d={area} fill={`url(#pulseFill-${metric})`} />
        <path className="pulseChartLine" d={line} />
        <circle
          className="pulseChartHead"
          cx={x(series.length - 1)}
          cy={y(totals[totals.length - 1])}
          r="4"
        />
      </svg>
      <figcaption>
        <span>{series[0].day}</span>
        <span>
          面积 = 累计 {METRIC_LABEL[metric]}（现 {formatCount(maxTotal)}）· 柱 = 当日新增
        </span>
        <span>{series[series.length - 1].day}</span>
      </figcaption>
    </figure>
  );
}

function WindowCard({
  title,
  counts,
  hint
}: {
  title: string;
  counts: { entities: number; relationships: number; events: number };
  hint: string;
}) {
  return (
    <article className="pulseWindowCard">
      <h4>{title}</h4>
      <dl>
        {(Object.keys(METRIC_LABEL) as MetricKey[]).map((key) => (
          <div key={key}>
            <dt>{METRIC_LABEL[key]}</dt>
            <dd className={counts[key] > 0 ? "up" : ""}>{formatDelta(counts[key])}</dd>
          </div>
        ))}
      </dl>
      <p>{hint}</p>
    </article>
  );
}

function CompositionBars({
  rows,
  total,
  labelFor
}: {
  rows: { bucket: string; count: number }[];
  total: number;
  labelFor: (bucket: string) => string;
}) {
  const top = rows.slice(0, 8);
  return (
    <ul className="pulseComposition">
      {top.map((row) => (
        <li key={row.bucket}>
          <span className="pulseCompositionLabel">{labelFor(row.bucket)}</span>
          <span className="pulseCompositionTrack" aria-hidden="true">
            <i style={{ width: `${total ? (row.count / total) * 100 : 0}%` }} />
          </span>
          <span className="pulseCompositionValue">{formatCount(row.count)}</span>
        </li>
      ))}
    </ul>
  );
}

const EVENT_TYPE_LABEL: Record<string, string> = {
  material_disclosure: "重大事项披露 (8-K)",
  quarterly_report: "季度报告 (10-Q)",
  annual_report: "年度报告 (10-K)",
  proxy_statement: "股东委托书 (DEF 14A)",
  beneficial_ownership_stake: "大额持股 (13D/G)",
  prospectus_filed: "招股说明书 (424)",
  securities_registration: "证券注册 (S-1/S-3)",
  delisting: "退市 (25)",
  ma_registration: "并购注册 (S-4)",
  tender_offer: "要约收购",
  capital_expenditure: "资本开支"
};

const RELATIONSHIP_FAMILY_LABEL: Record<string, string> = {
  corporate_structure: "集团结构",
  ownership_control: "所有权与控制",
  governance_people: "治理与人事",
  supply_chain_operations: "供应链运营",
  commercial_dependency: "商业依赖",
  capital_financing: "资本与融资",
  mergers_acquisitions: "并购",
  strategic_signal: "战略信号",
  government_policy: "政策环境",
  technology_data_ip: "技术与知识产权"
};

// —— the dashboard ————————————————————————————————————————————————————

export function PulseDashboard({ days = 60 }: { days?: number }) {
  const result = usePulse(days);
  const [metric, setMetric] = useState<MetricKey>("events");

  if (!result) {
    return <div className="pulsePanel loading" data-testid="pulse-dashboard" data-state="loading" />;
  }
  if (result.status !== "hydrated") {
    return (
      <div className="pulsePanel" data-testid="pulse-dashboard" data-state={result.status}>
        <h3>数据脉搏</h3>
        <p className="pulseUnavailable">
          {result.status === "skipped"
            ? "本地样例工作台不连采集管道，脉搏只在已发布面显示。"
            : "暂时读不到采集状态——这里只显示真实读到的数字，不显示猜测值。"}
        </p>
        <details className="diagDetails">
          <summary>诊断详情</summary>
          <div>
            <strong>原因</strong>
            <span data-testid="pulse-dashboard-reason">{result.reason}</span>
          </div>
        </details>
      </div>
    );
  }

  const { record } = result;
  const eventTotal = record.composition.event_type.reduce((sum, r) => sum + r.count, 0);
  const familyTotal = record.composition.relationship_family.reduce((s, r) => s + r.count, 0);

  return (
    <section className="pulsePanel" data-testid="pulse-dashboard" data-state="hydrated">
      <header className="pulsePanelHead">
        <div>
          <h3>数据脉搏</h3>
          <p>
            全库现有多少、今天涨了多少、采集器还在不在跑——这一屏就是答案。
            {record.data_as_of ? `数据截至 ${record.data_as_of.slice(0, 16).replace("T", " ")} UTC。` : ""}
          </p>
        </div>
        <HeartbeatDot record={record} />
      </header>

      <div className="pulseTotals">
        {(Object.keys(METRIC_LABEL) as MetricKey[]).map((key) => (
          <button
            aria-pressed={metric === key}
            className={`pulseTotalCard${metric === key ? " active" : ""}`}
            data-testid={`pulse-metric-${key}`}
            key={key}
            onClick={() => setMetric(key)}
            type="button"
          >
            <span className="pulseTotalLabel">{METRIC_LABEL[key]}</span>
            <Odometer value={record.totals[key]} />
            <span className={`pulseDelta${record.added.today[key] > 0 ? " up" : ""}`}>
              今日 {formatDelta(record.added.today[key])}
            </span>
            <small>{METRIC_HINT[key]}</small>
          </button>
        ))}
      </div>

      <GrowthChart metric={metric} series={record.series} />

      <div className="pulseWindows">
        <WindowCard
          counts={record.added.today}
          hint="今天已经入库的新事实。周末与美国假日 SEC 不发文，归零是正常的。"
          title="今日新增"
        />
        <WindowCard counts={record.added.d7} hint="最近 7 天的净增长。" title="近 7 天" />
        <WindowCard counts={record.added.d30} hint="最近 30 天的净增长。" title="近 30 天" />
      </div>

      <div className="pulseSplit">
        <section>
          <h4>事件构成</h4>
          <CompositionBars
            labelFor={(b) => EVENT_TYPE_LABEL[b] ?? b}
            rows={record.composition.event_type}
            total={eventTotal}
          />
        </section>
        <section>
          <h4>关系构成</h4>
          <CompositionBars
            labelFor={(b) => RELATIONSHIP_FAMILY_LABEL[b] ?? b}
            rows={record.composition.relationship_family}
            total={familyTotal}
          />
        </section>
      </div>

      <section className="pulseSources">
        <h4>来源与新鲜度</h4>
        <table data-testid="pulse-sources">
          <thead>
            <tr>
              <th scope="col">来源</th>
              <th scope="col">已收原始文件</th>
              <th scope="col">最近一次抓取</th>
            </tr>
          </thead>
          <tbody>
            {record.sources.map((source) => (
              <tr key={source.code}>
                <th scope="row">{source.name}</th>
                <td>{formatCount(source.documents)}</td>
                <td>{source.last_seen_at ? source.last_seen_at.slice(0, 16).replace("T", " ") : "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </section>
  );
}
