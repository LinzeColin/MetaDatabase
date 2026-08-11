/* eslint-disable @next/next/no-img-element */

import type { Metadata } from "next";
import type { ReactNode } from "react";
import {
  FatlossClient,
  GenericPageClient,
  HomeClient,
  LedgerClient,
  PeriodClient,
} from "./_components/workbench/lifestyle-pages-client";
import TodoPageClient from "./_components/workbench/todo-page-client";
import { LegacyDomainRedirect } from "./_components/workbench/legacy-domain-redirect";

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
  title: "个人日程",
  description: "把生活里的小事，温柔地放在一起。",
};

type PageProps = {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
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
    <aside className="sidebar" aria-label="个人日程导航">
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
            <a aria-label="登录或管理账户" className="account-entry normal-only" href="/account">
              登录 / 账户
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
        <a aria-label="登录或管理账户" className="welcome-account-link normal-only" href="/account">
          登录 / 账户
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
            进入个人日程&nbsp; →
          </a>
          {!reference ? <p className="welcome-auth-note">登录后，换设备也能接着用</p> : null}
        </div>
      </section>
    </div>
  );
}

function Home({ reference }: { reference: boolean }) {
  const habitCards = [
    { icon: "habit_early.png", label: "早起" },
    { icon: "habit_read.png", label: "阅读" },
    { icon: "habit_sport.png", label: "运动" },
    { icon: "habit_water.png", label: "喝水" },
    { icon: "habit_sleep.png", label: "早睡" },
  ];

  return (
    <Shell pageClass="home-page" reference={reference} route="home">
      <HomeClient habitCards={habitCards} reference={reference} />
    </Shell>
  );
}

function Ledger({ reference }: { reference: boolean }) {
  return (
    <Shell pageClass="ledger-page" reference={reference} route="ledger">
      <PageHead icon="ledger_title.png" motto="理性消费，快乐生活" title="记账本" />
      <LedgerClient fixtureDate={fixture.date} reference={reference} />
    </Shell>
  );
}

function Fatloss({ reference }: { reference: boolean }) {
  return (
    <Shell pageClass="fatloss-page" reference={reference} route="fatloss-food">
      <PageHead icon="fatloss_title.png" motto="坚持就是胜利！" title="减脂记录" />
      <FatlossClient fixtureDate={fixture.date} reference={reference} />
    </Shell>
  );
}

function Period({ reference }: { reference: boolean }) {
  return (
    <Shell pageClass="period-page" reference={reference} route="period">
      <PageHead icon="period_title.png" title="经期记录" />
      <PeriodClient reference={reference} />
    </Shell>
  );
}

function GenericPage({ reference, route }: { reference: boolean; route: string }) {
  if (route === "todo") {
    return (
      <Shell pageClass="todo-page" reference={reference} route="todo">
        <TodoPageClient />
      </Shell>
    );
  }

  const label =
    ({ todo: "待办事项", schedule: "日程安排", anniversary: "纪念日", diary: "日记", savings: "存钱计划" } as Record<string, string>)[route] ??
    "个人日程";
  return (
    <Shell pageClass="generic-page" reference={reference} route={route}>
      <PageHead icon="nav_desktop.png" title={label} />
      <GenericPageClient
        label={label}
        reference={reference}
        route={route as "schedule" | "anniversary" | "diary" | "savings"}
      />
    </Shell>
  );
}

export default async function HomePage({ searchParams }: PageProps) {
  const params = await searchParams;
  const reference = typeof params.reference === "string" && referenceRoutes.has(params.reference);
  const requestedRoute = reference ? params.reference! : params.view;
  const route = typeof requestedRoute === "string" && navigableRoutes.has(requestedRoute) ? requestedRoute : "welcome";

  let page: ReactNode;
  switch (route) {
    case "home":
      page = <Home reference={reference} />;
      break;
    case "ledger":
      page = <Ledger reference={reference} />;
      break;
    case "fatloss-food":
      page = <Fatloss reference={reference} />;
      break;
    case "period":
      page = <Period reference={reference} />;
      break;
    case "welcome":
      page = <Welcome reference={reference} />;
      break;
    default:
      page = <GenericPage reference={reference} route={route} />;
  }

  return (
    <>
      <LegacyDomainRedirect />
      {page}
    </>
  );
}
