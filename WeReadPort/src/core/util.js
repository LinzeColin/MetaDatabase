import { WeReadPortError } from "./errors.js";
const encoder = new TextEncoder();
const decoder = new TextDecoder("utf-8", { fatal: true });

/** @param {unknown} value */
export function isPlainObject(value) { if (value === null || typeof value !== "object" || Array.isArray(value)) return false; const p = Object.getPrototypeOf(value); return p === Object.prototype || p === null; }
/** @param {unknown} value @param {string} [field] */
export function asObject(value, field = "值") { if (!isPlainObject(value)) throw new WeReadPortError("SCHEMA", `${field} 必须是对象。`); return /** @type {Record<string,unknown>} */ (value); }
/** @param {unknown} value */
export function asArray(value) { return Array.isArray(value) ? value : []; }
/** @param {unknown} value @param {string} [fallback] */
export function asString(value, fallback = "") { return typeof value === "string" ? value : fallback; }
/** @param {unknown} value @param {number} [fallback] */
export function asFiniteNumber(value, fallback = 0) { return typeof value === "number" && Number.isFinite(value) ? value : fallback; }
/** @param {unknown} value */
export function asOptionalInteger(value) { return Number.isInteger(value) ? /** @type {number} */ (value) : undefined; }
/** @param {unknown} value */
export function asOptionalBoolean(value) { if (typeof value === "boolean") return value; if (value === 1) return true; if (value === 0) return false; return undefined; }
/** @param {string} value */
export function normalizeText(value) { return value.normalize("NFC").replace(/\r\n?/g, "\n").replace(/[ \t]+$/gm, "").trim(); }
/** @param {string} value */
export function utf8(value) { return encoder.encode(value); }
/** @param {Uint8Array} value */
export function decodeUtf8(value) { return decoder.decode(value); }
/** @param {unknown} value */
export function stableStringify(value) { return `${JSON.stringify(sortJson(value), null, 2)}\n`; }
/** @param {unknown} value @returns {unknown} */
function sortJson(value) { if (Array.isArray(value)) return value.map(sortJson); if (isPlainObject(value)) { const out = {}; for (const key of Object.keys(value).sort()) out[key] = sortJson(value[key]); return out; } return value; }
/** @param {Uint8Array|string} input */
export async function sha256Hex(input) { const bytes = typeof input === "string" ? utf8(input) : input; const digest = await globalThis.crypto.subtle.digest("SHA-256", bytes); return Array.from(new Uint8Array(digest), n => n.toString(16).padStart(2, "0")).join(""); }
/** @param {string} value */
export function fnv1a32Hex(value) { let hash = 0x811c9dc5; for (const byte of utf8(value.normalize("NFC"))) { hash ^= byte; hash = Math.imul(hash, 0x01000193) >>> 0; } return hash.toString(16).padStart(8, "0"); }
const WINDOWS_DEVICE = /^(con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\.|$)/i;
/** @param {string} raw @param {string} [fallback] */
export function safePathSegment(raw, fallback = "untitled") { let value = normalizeText(raw || fallback).replace(/[<>:"/\\|?*\u0000-\u001f]/g, "-").replace(/\.{2,}/g, ".").replace(/[. ]+$/g, "").replace(/^\.+/g, "").replace(/\s+/g, " ").trim(); if (!value) value = fallback; if (WINDOWS_DEVICE.test(value)) value = `_${value}`; const chars = Array.from(value); if (chars.length > 96) value = chars.slice(0, 96).join("").replace(/[. ]+$/g, ""); return value || fallback; }
/** @param {string} title @param {string} sourceId */
export function safeBookFilename(title, sourceId) { return `${safePathSegment(title, "untitled-book")}--${fnv1a32Hex(sourceId)}.md`; }
/** @param {string} path */
export function assertSafeArchivePath(path) { if (!path || path.startsWith("/") || path.startsWith("\\") || /^[A-Za-z]:/.test(path)) throw new WeReadPortError("UNSAFE_PATH", `不安全的归档路径：${path}`); const normalized = path.replace(/\\/g, "/"); if (normalized.includes("//") || normalized.split("/").some(p => p === ".." || p === "." || !p)) throw new WeReadPortError("UNSAFE_PATH", `不安全的归档路径：${path}`); return normalized.normalize("NFC"); }
/** @param {unknown} unixSeconds */
export function unixSecondsToIsoDate(unixSeconds) { const value = asFiniteNumber(unixSeconds, NaN); if (!Number.isFinite(value) || value <= 0) return undefined; const date = new Date(value * 1000); return Number.isNaN(date.getTime()) ? undefined : date.toISOString().slice(0, 10); }
/** @param {number|undefined} seconds */
export function formatDuration(seconds) { if (seconds === undefined || !Number.isFinite(seconds) || seconds < 0) return undefined; const total = Math.floor(seconds), h = Math.floor(total / 3600), m = Math.floor((total % 3600) / 60), s = total % 60, parts = []; if (h) parts.push(`${h}小时`); if (m) parts.push(`${m}分钟`); if (!h && !m) parts.push(`${s}秒`); return parts.join(""); }
/** @param {string} value */
export function yamlQuote(value) { return JSON.stringify(normalizeText(value)); }
/** @param {number} ms @param {AbortSignal|undefined} signal */
export function abortableDelay(ms, signal) {
  if (ms <= 0) return Promise.resolve();
  return new Promise((resolve, reject) => {
    let settled = false;
    const cleanup = () => signal?.removeEventListener("abort", abort);
    const finish = () => { if (settled) return; settled = true; cleanup(); resolve(); };
    const timer = setTimeout(finish, ms);
    const abort = () => { if (settled) return; settled = true; clearTimeout(timer); cleanup(); reject(signal?.reason ?? new WeReadPortError("CANCELLED", "操作已取消。")); };
    if (signal?.aborted) abort(); else signal?.addEventListener("abort", abort, { once: true });
  });
}
/** @param {AbortSignal|undefined} first @param {AbortSignal} second */
export function combineSignals(first, second) { if (!first) return second; if (typeof AbortSignal.any === "function") return AbortSignal.any([first, second]); const controller = new AbortController(); const relay = signal => controller.abort(signal.reason); if (first.aborted) relay(first); else first.addEventListener("abort", () => relay(first), { once: true }); if (second.aborted) relay(second); else second.addEventListener("abort", () => relay(second), { once: true }); return controller.signal; }
/** @param {unknown[]} values */
export function maxFinite(values) { const nums = values.filter(v => typeof v === "number" && Number.isFinite(v)); return nums.length ? Math.max(...nums) : undefined; }
/** @param {unknown} value @param {number} min @param {number} max */
export function clampOptional(value, min, max) { if (typeof value !== "number" || !Number.isFinite(value)) return undefined; return Math.min(max, Math.max(min, value)); }
