"use client";

// P2-10 旧路由收编（§A.3）：并购交易并入「资本与事件」的事件类型筛选片。
// /ma → /capital?event_type=ma（capital 页读 event_type 参数预置筛选）。
import { RouteRedirect } from "../components/route-redirect";

export default function MaRedirectPage() {
  return <RouteRedirect to="/capital?event_type=ma" />;
}
