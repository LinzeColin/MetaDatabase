"use client";

// P2-10 旧路由收编（§A.3）：政策环境并入「外部信号」的政策 tab。
// /policy → /signals?tab=policy（signals 页读 tab 参数选中政策 tab）。
import { RouteRedirect } from "../components/route-redirect";

export default function PolicyRedirectPage() {
  return <RouteRedirect to="/signals?tab=policy" />;
}
