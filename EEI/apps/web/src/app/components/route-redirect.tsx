"use client";

// P2-10 旧路由收编（UX_SPEC_EEI v1.0 §A.3 / §G-P2-10）。
// next.config 是 output: export 静态导出，不支持 server 端 redirects()。
// 故旧路由页渲染本组件做客户端重定向：
//   ① window.location.replace(to)——有 JS 即刻跳转，且不留历史（Back 不回旧路由）；
//   ② <meta http-equiv=refresh>——React 19 提升进 <head>，无 JS 也跳；
//   ③ 可点 <a href=to>——0 死链兜底（无 JS 且不认 meta 时仍可手动前往）。
// 落地页各自高亮正确一级入口（activeModuleId 由目标页自带）。

import { useEffect } from "react";

export function RouteRedirect({ to }: { to: string }) {
  useEffect(() => {
    window.location.replace(to);
  }, [to]);

  return (
    <div className="routeRedirect" data-redirect-to={to} data-testid="route-redirect">
      {/* eslint-disable-next-line @next/next/no-html-link-for-pages */}
      <meta content={`0; url=${to}`} httpEquiv="refresh" />
      <p>正在前往新位置…</p>
      {/* 普通 <a>（非 next/link）：跨 query/hash 的静态重定向兜底，0 死链。 */}
      <a href={to}>如果没有自动跳转，请点此继续 →</a>
    </div>
  );
}
