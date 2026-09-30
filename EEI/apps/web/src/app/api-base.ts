// 数据接口基址的唯一解析点。
//
// NEXT_PUBLIC_EEI_API_BASE_URL（构建期注入）有三种写法：
//   - 空 / 未设：没有接口，前端走本地样例（本地 dev 与 CI 的样例工作台语义）；
//   - "same-origin"：接口就在页面所在的同一个域名下（/v1/*）。自托管镜像用这个值——
//     运行时取 window.location.origin，构建产物里不写死任何域名；
//   - 完整地址（如 http://127.0.0.1:8000）：本地全栈 E2E 连本机 API 用。
// 浏览器里仍可用 localStorage 覆盖（调试用），优先级高于构建期值。

export const SAME_ORIGIN_API_BASE = "same-origin";

/** 构建期是否配置了接口（含 same-origin）。页面据此判断「云生产模式」。 */
export const API_BASE_CONFIGURED = Boolean(
  process.env.NEXT_PUBLIC_EEI_API_BASE_URL?.trim()
);

/** 构建期配置的接口基址，已解析成可直接拼 `/v1/...` 的字符串；未配置返回空串。必须在浏览器里调用。 */
export function readConfiguredApiBaseUrl(): string {
  const configured = process.env.NEXT_PUBLIC_EEI_API_BASE_URL?.trim() ?? "";
  if (configured === SAME_ORIGIN_API_BASE) return window.location.origin;
  return configured;
}
