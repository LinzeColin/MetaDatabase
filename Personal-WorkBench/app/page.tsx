/* eslint-disable @next/next/no-img-element */

import type { Metadata } from "next";
import type { ReactNode } from "react";

const PRIVATE_ASSET_ROOT = "/private-reference-assets";
const RUNTIME_ASSET_ROOT = `${PRIVATE_ASSET_ROOT}/runtime`;

const referenceRoutes = new Set([
  "welcome",
  "home",
  "ledger",
  "fatloss-food",
  "period",
]);

const navigableRoutes = new Set([
  "welcome",
  "home",
  "todo",
  "ledger",
  "fatloss-food",
  "schedule",
  "anniversary",
  "diary",
  "savings",
  "period",
]);

const navItems = [
  ["home", "桌面", "nav_desktop.png"],
  ["todo", "待办", "nav_todo.png"],
  ["ledger", "记账", "nav_ledger.png"],
  ["fatloss-food", "减脂", "nav_fatloss.png"],
  ["schedule", "日程", "nav_schedule.png"],
  ["anniversary", "纪念", "nav_anniversary.png"],
  ["diary", "日记", "nav_diary.png"],
  ["savings", "存钱", "nav_savings.png"],
  ["period", "经期", "nav_period.png"],
] as const;

const fixture = {
  date: "2026年8月2日",
  weekday: "星期日",
  name: "小张张",
  time: "11:27",
};

export const metadata: Metadata = {
  title: "胡楚靓工作台",
  description: "把生活里的小事，温柔地放在一起。",
};

type PageProps = {
  searchParams: Promise<{ reference?: string; view?: string }>;
};

function asset(name: string) {
  return `${RUNTIME_ASSET_ROOT}/${name}`;
}

function referenceAsset(name: string) {
  return `${PRIVATE_ASSET_ROOT}/${name}`;
}

function hrefFor(route: string, reference: boolean) {
  return `?${reference ? "reference" : "view"}=${route}`;
}

function Sidebar({ route, reference }: { route: string; reference: boolean }) {
  return (
    <aside className="sidebar" aria-label="工作台导航">
      <nav className="nav-list">
        {navItems.map(([key, label, icon]) => (
          <a
            aria-current={route === key ? "page" : undefined}
            className={`nav-item ${route === key ? "is-active" : ""}`}
            href={hrefFor(key, reference)}
            key={key}
          >
            <img alt="" className="nav-icon" src={asset(icon)} />
            <span className="nav-label">{label}</span>
          </a>
        ))}
      </nav>
    </aside>
  );
}

function Shell({
  children,
  pageClass,
  reference,
  route,
}: {
  children: ReactNode;
  pageClass: string;
  reference: boolean;
  route: string;
}) {
  return (
    <div
      className={`app-stage ${pageClass} ${reference ? "reference-mode" : ""}`}
      data-reference-mode={reference ? "true" : "false"}
      data-reference-page={reference ? route : undefined}
    >
      <div className="workbench-shell">
        <Sidebar reference={reference} route={route} />
        <main className="main">
          {!reference ? (
            <a className="account-entry normal-only" href="/auth/sign-in">
              账户
            </a>
          ) : null}
          {children}
        </main>
      </div>
    </div>
  );
}

function PageHead({
  icon,
  motto,
  title,
}: {
  icon: string;
  motto?: string;
  title: string;
}) {
  return (
    <header className="page-head">
      <h1 className="page-title">
        <img alt="" className="page-title-icon" src={asset(icon)} />
        {title}
      </h1>
      {motto ? <span className="page-motto">{motto}</span> : null}
    </header>
  );
}

function Welcome({ reference }: { reference: boolean }) {
  return (
    <div
      className={`app-stage welcome-stage ${reference ? "reference-mode" : ""}`}
      data-reference-mode={reference ? "true" : "false"}
      data-reference-page={reference ? "welcome" : undefined}
    >
      {!reference ? (
        <a className="welcome-account-link normal-only" href="/auth/sign-in">
          账户
        </a>
      ) : null}
      <section className="welcome-page">
        <div className="welcome-inner">
          <img
            alt="Hello Kitty"
            className="welcome-kitty"
            src={referenceAsset("welcome_hello_kitty_reference_crop.png")}
          />
          <p className="welcome-date">
            {fixture.date}&nbsp; {fixture.weekday}
          </p>
          <h1 className="welcome-name">
            嗨，{fixture.name}
            <img alt="" src={asset("welcome_bow.png")} />
          </h1>
          <p className="welcome-subtitle">
            慢慢来，一切都在变好<span aria-hidden="true" className="welcome-spark" />
          </p>
          <a className="welcome-enter" href={hrefFor("home", reference)}>
            进入工作台&nbsp; →
          </a>
          {!reference ? <p className="welcome-auth-note">登录后，换设备也能接着用</p> : null}
        </div>
      </section>
    </div>
  );
}

function Home({ reference }: { reference: boolean }) {
  const habitCards = [
    ["habit_early.png", "早起", "点击打卡"],
    ["habit_read.png", "阅读", "点击打卡"],
    ["habit_sport.png", "运动", "点击打卡"],
    ["habit_water.png", "喝水", "点击打卡"],
    ["habit_sleep.png", "早睡", "点击打卡"],
  ];

  return (
    <Shell pageClass="home-page" reference={reference} route="home">
      <section className="home-hero">
        <p className="home-greeting">早上好，{fixture.name}～</p>
        <div className="home-time">{fixture.time}</div>
        <p className="home-date">{fixture.date}</p>
        <p className="home-weekday">{fixture.weekday}</p>
      </section>
      <article className="card quote-card">
        <p className="quote-cn">今天的你，比昨天更优秀。</p>
        <p className="quote-en">You are better today than you were yesterday.</p>
      </article>
      <h2 className="section-title dot">每日打卡</h2>
      <div className="habit-grid">
        {habitCards.map(([icon, label, state]) => (
          <button className="habit-card" key={label} type="button">
            <img alt="" className="habit-icon" src={asset(icon)} />
            <strong>{label}</strong>
            <small>{state}</small>
          </button>
        ))}
      </div>
      <article className="card overview-card">
        <h2 className="section-title dot">今日概览</h2>
        <div className="overview-grid">
          <div className="overview-stat">
            <b>0/5</b>
            <span>今日打卡</span>
          </div>
          <div className="overview-stat">
            <b>0</b>
            <span>待办未完成</span>
          </div>
          <div className="overview-stat">
            <b>¥0.00</b>
            <span>今日支出</span>
          </div>
        </div>
      </article>
    </Shell>
  );
}

function Ledger({ reference }: { reference: boolean }) {
  return (
    <Shell pageClass="ledger-page" reference={reference} route="ledger">
      <PageHead icon="ledger_title.png" motto="理性消费，快乐生活" title="记账本" />
      <div className="summary-grid">
        <div className="summary-card income">
          <span>收入</span>
          <b>+¥0.00</b>
        </div>
        <div className="summary-card expense">
          <span>支出</span>
          <b>-¥0.00</b>
        </div>
        <div className="summary-card balance">
          <span>结余</span>
          <b>¥0.00</b>
        </div>
      </div>
      <form className="card ledger-form">
        <div className="segmented" role="group" aria-label="账目类型">
          <button className="is-active" type="button">
            支出
          </button>
          <button type="button">收入</button>
        </div>
        <div className="form-grid">
          <label className="field">
            <span>金额</span>
            <input className="input" inputMode="decimal" placeholder="0.00" />
          </label>
          <label className="field">
            <span>日期</span>
            <input className="input" defaultValue={fixture.date} readOnly={reference} />
          </label>
          <label className="field wide">
            <span>分类</span>
            <select className="select" defaultValue="餐饮">
              <option>餐饮</option>
              <option>交通</option>
              <option>购物</option>
              <option>工资</option>
              <option>其他</option>
            </select>
          </label>
          <label className="field wide">
            <span>备注（可选）</span>
            <input className="input" placeholder="写点什么…" />
          </label>
        </div>
        <button className="primary full" type="button">
          ＋ 记一笔
        </button>
      </form>
      <article className="card record-list-card">
        <h2 className="section-title">
          <span aria-hidden="true" className="section-glyph">
            ≡
          </span>
          账单明细
        </h2>
        <div className="empty">
          <p>还没有账单，记一笔吧～</p>
        </div>
      </article>
    </Shell>
  );
}

function Fatloss({ reference }: { reference: boolean }) {
  return (
    <Shell pageClass="fatloss-page" reference={reference} route="fatloss-food">
      <PageHead icon="fatloss_title.png" motto="坚持就是胜利！" title="减脂记录" />
      <div className="module-tabs" role="tablist" aria-label="减脂记录类型">
        <button className="module-tab" role="tab" type="button">
          <img alt="" className="module-tab-icon" src={asset("tab_exercise.png")} />
          运动
        </button>
        <button className="module-tab" role="tab" type="button">
          <img alt="" className="module-tab-icon" src={asset("tab_weight.png")} />
          体重
        </button>
        <button aria-selected="true" className="module-tab is-active" role="tab" type="button">
          <img alt="" className="module-tab-icon" src={asset("tab_food.png")} />
          饮食
        </button>
      </div>
      <form className="card food-card">
        <h2 className="section-title">
          <img alt="" src={asset("food_title.png")} />
          饮食记录
        </h2>
        <label className="field">
          <span>饮食照片（可选，帮您记录）</span>
          <span className="upload-zone">
            <img alt="" src={asset("food_camera.png")} />
            <span>点击上传食物照片</span>
          </span>
        </label>
        <div className="form-grid">
          <label className="field wide">
            <span>食物</span>
            <select className="select" defaultValue="manual">
              <option value="manual">-- 手动输入 --</option>
            </select>
          </label>
          <label className="field wide">
            <span className="sr-only">食物名称</span>
            <input className="input" placeholder="输入食物名称" />
          </label>
          <label className="field">
            <span>热量(千卡)</span>
            <input className="input" defaultValue="0" inputMode="numeric" />
          </label>
          <label className="field">
            <span>餐次</span>
            <select className="select" defaultValue="早餐">
              <option>早餐</option>
              <option>午餐</option>
              <option>晚餐</option>
              <option>加餐</option>
            </select>
          </label>
          <label className="field">
            <span>日期</span>
            <input className="input" defaultValue={fixture.date} readOnly={reference} />
          </label>
          <label className="field">
            <span>备注</span>
            <input className="input" placeholder="可选" />
          </label>
        </div>
        <button className="primary full" type="button">
          ＋ 记录饮食
        </button>
      </form>
      <article className="total-card">
        <span>今日摄入总热量</span>
        <b>0</b>
        <span>千卡</span>
      </article>
    </Shell>
  );
}

function Period({ reference }: { reference: boolean }) {
  return (
    <Shell pageClass="period-page" reference={reference} route="period">
      <PageHead icon="period_title.png" title="经期记录" />
      <form className="card period-form">
        <div className="form-grid">
          <label className="field">
            <span>开始日期</span>
            <input className="input" defaultValue="" readOnly={reference} />
          </label>
          <label className="field">
            <span>结束日期</span>
            <input className="input" defaultValue="" readOnly={reference} />
          </label>
        </div>
        <button className="primary full" type="button">
          ＋ 记录经期
        </button>
      </form>
      <article className="card period-overview">
        <h2 className="section-title">
          <img alt="" src={asset("period_title.png")} />
          周期概览
        </h2>
        <div className="period-stats">
          <div className="period-stat">
            <span>当前周期</span>
            <b>--</b>
          </div>
          <div className="period-stat">
            <span>预测下次（估算）</span>
            <b>--</b>
          </div>
          <div className="period-stat">
            <span>平均周期</span>
            <b>--</b>
          </div>
        </div>
      </article>
      <article className="card period-history">
        <h2 className="section-title">
          <span aria-hidden="true" className="section-glyph">
            ≡
          </span>
          历史记录
        </h2>
        <div className="empty">
          <p>还没有经期记录</p>
        </div>
      </article>
    </Shell>
  );
}

function GenericPage({ reference, route }: { reference: boolean; route: string }) {
  const label =
    ({ todo: "待办事项", schedule: "日程安排", anniversary: "纪念日", diary: "日记", savings: "存钱计划" } as Record<string, string>)[route] ??
    "工作台";
  return (
    <Shell pageClass="generic-page" reference={reference} route={route}>
      <PageHead icon="nav_desktop.png" title={label} />
      <article className="card generic-card">
        <p className="muted">把今天真正要完成的小事，温柔地放在这里。</p>
        <button className="primary full" type="button">
          ＋ 新增记录
        </button>
      </article>
    </Shell>
  );
}

export default async function HomePage({ searchParams }: PageProps) {
  const params = await searchParams;
  const reference = typeof params.reference === "string" && referenceRoutes.has(params.reference);
  const requestedRoute = reference ? params.reference! : params.view;
  const route = typeof requestedRoute === "string" && navigableRoutes.has(requestedRoute) ? requestedRoute : "welcome";

  switch (route) {
    case "home":
      return <Home reference={reference} />;
    case "ledger":
      return <Ledger reference={reference} />;
    case "fatloss-food":
      return <Fatloss reference={reference} />;
    case "period":
      return <Period reference={reference} />;
    case "welcome":
      return <Welcome reference={reference} />;
    default:
      return <GenericPage reference={reference} route={route} />;
  }
}
