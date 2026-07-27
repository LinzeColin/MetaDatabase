import { MAX_USER_REGION_BYTES, USER_REGION_END, USER_REGION_START } from "./constants.js";
import { WeReadPortError } from "./errors.js";
import { utf8 } from "./util.js";

/** @param {string} markdown */
export function extractProtectedRegion(markdown) {
  const startCount = countOccurrences(markdown, USER_REGION_START);
  const endCount = countOccurrences(markdown, USER_REGION_END);
  if (startCount === 0 && endCount === 0) return undefined;
  if (startCount !== 1 || endCount !== 1) throw new WeReadPortError("PROTECTED_REGION_CONFLICT", "旧文件的个人补充区标记重复或缺失，已停止以避免覆盖用户内容。");
  const start = markdown.indexOf(USER_REGION_START);
  const end = markdown.indexOf(USER_REGION_END);
  if (end < start) throw new WeReadPortError("PROTECTED_REGION_CONFLICT", "旧文件的个人补充区标记顺序无效，已停止以避免覆盖用户内容。");
  const contentStart = start + USER_REGION_START.length;
  const content = markdown.slice(contentStart, end);
  if (content.includes("<!-- weread-port:user:")) throw new WeReadPortError("PROTECTED_REGION_CONFLICT", "旧文件个人补充区包含嵌套控制标记，已停止以避免覆盖用户内容。");
  if (utf8(content).byteLength > MAX_USER_REGION_BYTES) throw new WeReadPortError("PROTECTED_REGION_CONFLICT", "旧文件个人补充区超过安全上限。");
  return content;
}

/** @param {string|undefined} preserved */
export function renderProtectedRegion(preserved) {
  const content = preserved === undefined ? "\n\n在这里补充你的永久个人笔记。再次导出时，这一区域会被原样保留。\n\n" : preserved;
  return `${USER_REGION_START}${content}${USER_REGION_END}`;
}

/** @param {string} generated @param {string|undefined} preserved */
export function injectProtectedRegion(generated, preserved) {
  const current = extractProtectedRegion(generated);
  if (current === undefined) throw new WeReadPortError("INTERNAL_CONTRACT", "生成文件缺少个人补充区。");
  const start = generated.indexOf(USER_REGION_START);
  const end = generated.indexOf(USER_REGION_END) + USER_REGION_END.length;
  return `${generated.slice(0, start)}${renderProtectedRegion(preserved)}${generated.slice(end)}`;
}

/** Replace only the user-editable region with its canonical generated content. @param {string} markdown */
export function canonicalizeProtectedRegion(markdown) {
  return injectProtectedRegion(markdown, undefined);
}

/** @param {string} value @param {string} needle */
function countOccurrences(value, needle) {
  let count = 0;
  let offset = 0;
  while (true) {
    const index = value.indexOf(needle, offset);
    if (index < 0) return count;
    count += 1;
    offset = index + needle.length;
  }
}
