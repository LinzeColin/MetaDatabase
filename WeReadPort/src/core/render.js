import { EXPORT_PROFILES, PROFILE_LABELS } from "./constants.js";
import { WeReadPortError } from "./errors.js";
import { renderProtectedRegion } from "./protected-regions.js";
import { formatDuration, normalizeText, unixSecondsToIsoDate, yamlQuote } from "./util.js";

/** @param {import('./model.js').CanonicalBook} book @param {{profile:string,includeCover?:boolean,preservedRegion?:string}} options */
export function renderBookMarkdown(book, options) {
  if (!Object.values(EXPORT_PROFILES).includes(options.profile)) throw new WeReadPortError("PROFILE", "未知标记文本兼容格式。");
  const notion = options.profile === EXPORT_PROFILES.NOTION;
  const lines = [];
  if (!notion) lines.push(...renderFrontmatter(book, options.profile), "");
  lines.push(`# ${escapeHeading(book.metadata.title)}`, "");
  if (options.includeCover && book.metadata.coverUrl) lines.push(`![${escapeInline(book.metadata.title)} 封面](${safeMarkdownUrl(book.metadata.coverUrl)})`, "");
  lines.push(...renderMetadata(book, options.profile), "");
  if (book.metadata.intro) lines.push("## 简介", "", normalizeText(book.metadata.intro), "");
  lines.push("## 导出说明", "", `- 格式：${PROFILE_LABELS[options.profile]}`, `- 微信读书技能契约：${book.source.skillVersion}`, `- 划线正文：${book.counts.highlights} 条`, `- 想法与点评：${book.counts.thoughtsAndReviews} 条`, `- 书签：${book.counts.officialBookmarkCount} 条（官方当前接口仅提供数量，不提供书签正文）`, "");
  if (book.warnings.length) { lines.push("### 数据提示", ""); for (const warning of book.warnings) lines.push(`- ${escapeInline(warning)}`); lines.push(""); }

  lines.push("## 笔记正文", "");
  const chapterMap = new Map(book.chapters.map(chapter => [chapter.uid, chapter]));
  const contentByChapter = new Map();
  for (const chapter of book.chapters) contentByChapter.set(chapter.uid, { chapter, highlights: [], thoughts: [] });
  for (const highlight of book.highlights) ensureGroup(contentByChapter, chapterMap, String(highlight.chapterUid ?? "unknown"), String(highlight.chapterTitle ?? "未分章"), Number(highlight.chapterIdx ?? Number.MAX_SAFE_INTEGER)).highlights.push(highlight);
  for (const thought of book.thoughts) ensureGroup(contentByChapter, chapterMap, String(thought.chapterUid ?? "book"), String(thought.chapterTitle ?? "整本书"), Number(thought.chapterIdx ?? Number.MAX_SAFE_INTEGER)).thoughts.push(thought);
  const groups = Array.from(contentByChapter.values()).filter(group => group.highlights.length || group.thoughts.length).sort((a, b) => a.chapter.chapterIdx - b.chapter.chapterIdx || a.chapter.title.localeCompare(b.chapter.title, "zh-CN"));
  if (!groups.length) lines.push("本次未读取到可导出的划线或想法。", "");
  for (const group of groups) {
    lines.push(`### ${escapeHeading(group.chapter.title)}`, "");
    const remainingThoughts = new Set(group.thoughts);
    for (const highlight of group.highlights) {
      lines.push(...renderHighlight(highlight, options.profile));
      for (const thought of group.thoughts) {
        if (!remainingThoughts.has(thought) || !thoughtMatchesHighlight(thought, highlight)) continue;
        lines.push(...renderThought(thought, options.profile));
        remainingThoughts.delete(thought);
      }
    }
    for (const thought of group.thoughts) if (remainingThoughts.has(thought)) lines.push(...renderThought(thought, options.profile));
  }

  lines.push("## 我的永久补充", "", renderProtectedRegion(options.preservedRegion), "");
  if (book.metadata.deepLink) lines.push("## 来源", "", `[在微信读书中打开](${safeMarkdownUrl(book.metadata.deepLink)})`, "");
  return `${lines.join("\n").replace(/\n{4,}/g, "\n\n\n").trimEnd()}\n`;
}

/** @param {import('./model.js').CanonicalBook} book @param {string} profile */
function renderFrontmatter(book, profile) {
  const tags = profile === EXPORT_PROFILES.OBSIDIAN ? "[微信读书, 读书笔记, 笔记迁移]" : "[微信读书, 读书笔记]";
  const sourceDate = book.sourceSnapshotAtIso ?? "";
  return ["---", `title: ${yamlQuote(book.metadata.title)}`, `author: ${yamlQuote(book.metadata.author)}`, `source_book_id: ${yamlQuote(book.source.bookId)}`, `source_skill_version: ${yamlQuote(book.source.skillVersion)}`, `source_snapshot_date: ${yamlQuote(sourceDate)}`, `tags: ${tags}`, "---"];
}

/** @param {import('./model.js').CanonicalBook} book @param {string} profile */
function renderMetadata(book, profile) {
  const values = [
    ["作者", book.metadata.author], ["译者", book.metadata.translator], ["出版社", book.metadata.publisher], ["出版时间", book.metadata.publishTime], ["ISBN", book.metadata.isbn],
    ["分类", book.metadata.category], ["阅读进度", book.progress.progress === undefined ? "" : `${book.progress.progress}%`], ["阅读时长", formatDuration(book.progress.readingTimeSeconds)], ["数据更新时间", unixSecondsToIsoDate(book.progress.updateTime) ?? book.sourceSnapshotAtIso],
  ].filter(([, value]) => value);
  if (profile === EXPORT_PROFILES.GFM) {
    return ["| 字段 | 内容 |", "| --- | --- |", ...values.map(([label, value]) => `| ${escapeTable(String(label))} | ${escapeTable(String(value))} |`)];
  }
  return values.map(([label, value]) => `- **${label}**：${escapeInline(String(value))}`);
}

/** @param {Record<string,unknown>} highlight @param {string} profile */
function renderHighlight(highlight, profile) {
  const lines = [`<!-- weread-port:item type="highlight" id="${escapeHtmlComment(String(highlight.id))}" -->`];
  if (profile === EXPORT_PROFILES.OBSIDIAN) lines.push(`> [!quote] 划线${highlight.createdAtIso ? ` · ${highlight.createdAtIso}` : ""}`);
  else lines.push(`> **划线${highlight.createdAtIso ? ` · ${highlight.createdAtIso}` : ""}**`);
  for (const line of normalizeText(String(highlight.text)).split("\n")) lines.push(`> ${line}`);
  if (highlight.range) lines.push(`>`, `> 位置：${escapeInline(String(highlight.range))}`);
  lines.push(""); return lines;
}

/** @param {Record<string,unknown>} thought @param {string} profile */
function renderThought(thought, profile) {
  const kindLabels = { "highlight-thought": "划线想法", "chapter-comment": "章节点评", "book-review": "整本书评", unclassified: "个人想法" };
  const label = kindLabels[String(thought.kind)] ?? "个人想法";
  const lines = [`<!-- weread-port:item type="thought" id="${escapeHtmlComment(String(thought.id))}" -->`, `#### ${label}${thought.createdAtIso ? ` · ${thought.createdAtIso}` : ""}`, ""];
  if (thought.abstract) {
    if (profile === EXPORT_PROFILES.OBSIDIAN) lines.push("> [!quote] 对应原文"); else lines.push("> **对应原文**");
    for (const line of normalizeText(String(thought.abstract)).split("\n")) lines.push(`> ${line}`);
    lines.push("");
  }
  lines.push(normalizeText(String(thought.content)), "");
  const details = [];
  if (thought.star !== undefined) details.push(`评分：${thought.star}/5`);
  if (thought.isFinish !== undefined) details.push(`阅读状态：${thought.isFinish ? "已读完" : "未读完"}`);
  if (thought.range) details.push(`位置：${escapeInline(String(thought.range))}`);
  if (details.length) lines.push(`_${details.join(" · ")}_`, "");
  return lines;
}


/** @param {Record<string,unknown>} thought @param {Record<string,unknown>} highlight */
function thoughtMatchesHighlight(thought, highlight) {
  const thoughtRange = String(thought.range ?? "").trim();
  const highlightRange = String(highlight.range ?? "").trim();
  if (thoughtRange && highlightRange && thoughtRange === highlightRange) return true;
  const abstract = normalizeText(String(thought.abstract ?? ""));
  const text = normalizeText(String(highlight.text ?? ""));
  return Boolean(abstract && text && abstract === text);
}

/** @param {Map<string,any>} groups @param {Map<string,any>} chapterMap @param {string} uid @param {string} title @param {number} idx */
function ensureGroup(groups, chapterMap, uid, title, idx) { if (!groups.has(uid)) groups.set(uid, { chapter: chapterMap.get(uid) ?? { uid, title, level: 1, chapterIdx: idx }, highlights: [], thoughts: [] }); return groups.get(uid); }
/** @param {string} value */
function escapeInline(value) { return normalizeText(value).replace(/([\\`*_{}\[\]<>])/g, "\\$1").replace(/\|/g, "\\|").replace(/\n/g, " "); }
/** @param {string} value */
function escapeHeading(value) { return normalizeText(value).replace(/^#+\s*/g, "").replace(/\n/g, " ").replace(/\s+#+$/g, ""); }
/** @param {string} value */
function escapeTable(value) { return escapeInline(value).replace(/\|/g, "\\|"); }
/** @param {string} value */
function escapeHtmlComment(value) { return value.replace(/--/g, "-").replace(/["<>]/g, ""); }
/** @param {string} value */
function safeMarkdownUrl(value) { return value.replace(/[()\s]/g, character => encodeURIComponent(character)); }
