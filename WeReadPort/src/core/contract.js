import { API_PARAMETER_RULES, MAX_GATEWAY_REQUEST_BYTES, REVIEWED_API_NAMES, SOURCE_SKILL_VERSION } from "./constants.js";
import { WeReadPortError } from "./errors.js";
import { isPlainObject, utf8 } from "./util.js";
const reviewedApis = new Set(REVIEWED_API_NAMES);

/** Validate shape only; the service cannot verify a user-bound key without an upstream call. @param {unknown} key */
export function validateUserKey(key) {
  const value = typeof key === "string" ? key.trim() : "";
  if (value.length < 12 || value.length > 512 || /[\s\u0000-\u001f]/.test(value) || !value.startsWith("wrk-")) {
    throw new WeReadPortError("AUTH", "请输入当前用户自己的有效微信读书密钥（以 wrk- 开头）。", { status: 401 });
  }
  return value;
}

/** @param {string} apiName @param {Record<string,unknown>} params @param {string} [skillVersion] */
export function buildGatewayBody(apiName, params, skillVersion = SOURCE_SKILL_VERSION) {
  if (!reviewedApis.has(apiName)) throw new WeReadPortError("INVALID_REQUEST", `接口 ${apiName} 不在已审查白名单。`, { status: 400 });
  if (!isPlainObject(params)) throw new WeReadPortError("INVALID_REQUEST", "业务参数必须是平铺对象。", { status: 400 });
  const rules = API_PARAMETER_RULES[apiName];
  /** @type {Record<string,unknown>} */
  const body = { api_name: apiName, skill_version: skillVersion };
  for (const [name, value] of Object.entries(params)) {
    if (["api_name", "skill_version", "params", "data", "body"].includes(name)) throw new WeReadPortError("INVALID_REQUEST", `保留字段 ${name} 不允许作为业务参数。`, { status: 400 });
    const expected = rules[name];
    if (!expected) throw new WeReadPortError("INVALID_REQUEST", `接口 ${apiName} 不接受参数 ${name}。`, { status: 400 });
    if (expected === "integer" && !Number.isInteger(value)) throw new WeReadPortError("INVALID_REQUEST", `${name} 必须是整数。`, { status: 400 });
    if (expected === "string" && typeof value !== "string") throw new WeReadPortError("INVALID_REQUEST", `${name} 必须是字符串。`, { status: 400 });
    body[name] = value;
  }
  validateRequired(apiName, body);
  validateRanges(apiName, body);
  if (utf8(JSON.stringify(body)).byteLength > MAX_GATEWAY_REQUEST_BYTES) throw new WeReadPortError("INVALID_REQUEST", "请求超过安全上限。", { status: 413 });
  return body;
}

/** Parse and rebuild an untrusted browser request. The client cannot override skill_version. @param {unknown} input */
export function parseProxyBody(input) {
  if (!isPlainObject(input)) throw new WeReadPortError("INVALID_REQUEST", "请求体必须是对象。", { status: 400 });
  const apiName = typeof input.api_name === "string" ? input.api_name : "";
  /** @type {Record<string,unknown>} */
  const params = {};
  for (const [name, value] of Object.entries(input)) {
    if (name === "api_name" || name === "skill_version") continue;
    params[name] = value;
  }
  return buildGatewayBody(apiName, params);
}

/** @param {string} apiName @param {Record<string,unknown>} body */
function validateRequired(apiName, body) {
  if (["/book/bookmarklist", "/book/info", "/book/getprogress", "/book/chapterinfo"].includes(apiName) && typeof body.bookId !== "string") throw new WeReadPortError("INVALID_REQUEST", "bookId 为必填参数。", { status: 400 });
  if (apiName === "/review/list/mine" && typeof body.bookid !== "string") throw new WeReadPortError("INVALID_REQUEST", "bookid 为必填参数。", { status: 400 });
}

/** @param {string} apiName @param {Record<string,unknown>} body */
function validateRanges(apiName, body) {
  if ("count" in body && (/** @type {number} */ (body.count) < 1 || /** @type {number} */ (body.count) > 100)) throw new WeReadPortError("INVALID_REQUEST", "count 必须在 1–100。", { status: 400 });
  for (const field of ["lastSort", "synckey", "baseTime"]) if (field in body && /** @type {number} */ (body[field]) < 0) throw new WeReadPortError("INVALID_REQUEST", `${field} 不得为负数。`, { status: 400 });
  for (const field of ["bookId", "bookid"]) if (field in body) { const value = /** @type {string} */ (body[field]); if (!value || value.length > 256 || /[\u0000-\u001f]/.test(value)) throw new WeReadPortError("INVALID_REQUEST", `${field} 格式无效。`, { status: 400 }); }
  if (apiName === "/readdata/detail" && "mode" in body && !new Set(["weekly", "monthly", "annually", "overall"]).has(/** @type {string} */ (body.mode))) throw new WeReadPortError("INVALID_REQUEST", "mode 不在允许范围。", { status: 400 });
}
