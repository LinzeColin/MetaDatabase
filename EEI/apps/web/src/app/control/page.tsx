"use client";

// P2-10 旧路由收编（§A.3）：控制关系并入「集团与控制」的控制区。
// /control → /structure#control（structure 的法律集团/控制区锚点）。
import { RouteRedirect } from "../components/route-redirect";

export default function ControlRedirectPage() {
  return <RouteRedirect to="/structure#control" />;
}
