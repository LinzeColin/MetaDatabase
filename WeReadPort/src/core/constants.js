/** 共享且冻结的产品常量与已审阅上游契约。 */
export const APP_PRODUCT_ID = "WeRead Port"; // 兼容 v0.0.0.7 及更早导出包的不可变产品标识。
export const APP_NAME = "微信读书笔记迁移";
export const APP_SHORT_NAME = "笔记迁移";
export const APP_VERSION = "v0.0.0.1.3";
export const EXPORT_CONTRACT_VERSION = "1.0.0";
export const CANONICAL_SCHEMA_VERSION = "1.0.0";
export const SOURCE_SKILL_VERSION = "1.0.4";
export const LOCAL_IMPORT_CONTRACT_VERSION = "1.0.0";
export const CHATGPT_HANDOFF_URL = "https://chatgpt.com/";
export const OFFICIAL_WEREAD_GATEWAY = "https://i.weread.qq.com/api/agent/gateway";

export const EXPORT_PROFILES = Object.freeze({
  PORTABLE: "portable-commonmark",
  GFM: "gfm",
  OBSIDIAN: "obsidian",
  NOTION: "notion-import",
});

/** 界面与导出报告中的中文名称；括号内仅保留目标规范或软件专名。 */
export const PROFILE_LABELS = Object.freeze({
  [EXPORT_PROFILES.PORTABLE]: "便携纯文本（CommonMark）",
  [EXPORT_PROFILES.GFM]: "代码仓库兼容（GitHub 风格）",
  [EXPORT_PROFILES.OBSIDIAN]: "双链笔记库（Obsidian）",
  [EXPORT_PROFILES.NOTION]: "协作笔记导入（Notion）",
});

/** P0 白名单：只包含个人笔记导出必需的接口。 */
export const REVIEWED_API_NAMES = Object.freeze([
  "/_list",
  "/user/notebooks",
  "/book/bookmarklist",
  "/review/list/mine",
  "/book/info",
  "/book/getprogress",
  "/book/chapterinfo",
  "/readdata/detail",
]);

/** 严格的平铺参数白名单。 */
export const API_PARAMETER_RULES = Object.freeze({
  "/_list": Object.freeze({}),
  "/user/notebooks": Object.freeze({ count: "integer", lastSort: "integer" }),
  "/book/bookmarklist": Object.freeze({ bookId: "string" }),
  "/review/list/mine": Object.freeze({ bookid: "string", synckey: "integer", count: "integer" }),
  "/book/info": Object.freeze({ bookId: "string" }),
  "/book/getprogress": Object.freeze({ bookId: "string" }),
  "/book/chapterinfo": Object.freeze({ bookId: "string" }),
  "/readdata/detail": Object.freeze({ mode: "string", baseTime: "integer" }),
});

export const NOTEBOOK_PAGE_SIZE = 100;
export const REVIEW_PAGE_SIZE = 100;
export const MAX_GATEWAY_REQUEST_BYTES = 64 * 1024;
export const MAX_GATEWAY_RESPONSE_BYTES = 12 * 1024 * 1024;
export const DEFAULT_GATEWAY_TIMEOUT_MS = 20_000;
export const DEFAULT_GATEWAY_ATTEMPTS = 2;
export const DEFAULT_CONCURRENCY = 3;
export const MAX_NOTEBOOK_PAGES = 1_000;
export const MAX_REVIEW_PAGES_PER_BOOK = 1_000;
export const MAX_SELECTED_BOOKS = 2_000;
export const MAX_ARCHIVE_FILES = 65_000;
export const MAX_ARCHIVE_BYTES = 512 * 1024 * 1024;
export const MAX_PREVIOUS_ARCHIVE_BYTES = 256 * 1024 * 1024;
export const MAX_LOCAL_IMPORT_FILES = 50;
export const MAX_LOCAL_IMPORT_FILE_BYTES = 10 * 1024 * 1024;
export const MAX_LOCAL_IMPORT_TOTAL_BYTES = 50 * 1024 * 1024;
export const MAX_CHATGPT_CONTEXT_BYTES = 4 * 1024 * 1024;
export const MAX_USER_REGION_BYTES = 2_000_000;

export const FIXED_ZIP_DOS_DATE = 0x0021; // 1980-01-01
export const FIXED_ZIP_DOS_TIME = 0x0000;
export const USER_REGION_ID = "personal-notes";
export const USER_REGION_START = `<!-- weread-port:user:start id="${USER_REGION_ID}" -->`;
export const USER_REGION_END = `<!-- weread-port:user:end id="${USER_REGION_ID}" -->`;

/** 内部机器状态保持稳定英文值；用户界面必须通过中文映射显示。 */
export const EXPORT_STATUS = Object.freeze({ COMPLETE: "COMPLETE", PARTIAL: "PARTIAL_EXPORT", FAILED: "FAILED" });
