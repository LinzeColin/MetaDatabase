const SECTION_LIMIT = 12;
const EXCERPT_LIMIT = 220;

export class BookToSkillError extends Error {
  constructor(code, message) {
    super(message);
    this.name = "BookToSkillError";
    this.code = code;
  }
}

/**
 * Turn one book's account-owned notes into a compact, reusable reading skill.
 * This is deterministic by design: no note body is sent to a model or third
 * party while a preview or saved skill is produced.
 */
export function buildBookSkill({ bookTitle, author = "", notes = [], generatedAt = new Date().toISOString() } = {}) {
  const title = cleanInline(bookTitle);
  const writer = cleanInline(author);
  if (!title) throw new BookToSkillError("BOOK_SKILL_BOOK_REQUIRED", "请选择一本有书名的笔记。" );
  const sourceNotes = normalizeNotes(notes);
  if (!sourceNotes.length) throw new BookToSkillError("BOOK_SKILL_NOTES_EMPTY", "这本书还没有可用于生成 Skill 的笔记。" );

  const sections = classifyCandidates(sourceNotes);
  const skillName = `reading-book-${safeSlug(title)}`;
  const description = `从《${title}》的 ${sourceNotes.length} 条账户笔记中提炼的可复用阅读 Skill。`;
  const artifact = {
    schemaVersion: "1.0.0",
    kind: "reading-book-skill",
    generatedAt: String(generatedAt),
    book: { title, author: writer || null },
    source: { noteCount: sourceNotes.length, transmission: "account-local" },
    skill: {
      name: skillName,
      description,
      frameworks: sections.frameworks,
      principles: sections.principles,
      techniques: sections.techniques,
      antiPatterns: sections.antiPatterns,
    },
  };
  artifact.markdown = renderSkillMarkdown(artifact);
  artifact.filename = `${skillName}.md`;
  return artifact;
}

function normalizeNotes(notes) {
  if (!Array.isArray(notes)) return [];
  return notes.map(note => ({
    title: cleanInline(note?.title || ""),
    content: cleanBody(note?.content || ""),
    category: cleanInline(note?.category || ""),
    chapterTitle: cleanInline(note?.chapterTitle || ""),
    noteKind: cleanInline(note?.noteKind || ""),
  })).filter(note => note.content);
}

function classifyCandidates(notes) {
  const classified = { frameworks: [], principles: [], techniques: [], antiPatterns: [] };
  for (const note of notes) {
    for (const candidate of noteCandidates(note)) {
      const bucket = candidateBucket(candidate, note);
      classified[bucket].push(candidate);
    }
  }
  for (const key of Object.keys(classified)) classified[key] = uniqueItems(classified[key]).slice(0, SECTION_LIMIT);
  if (!classified.principles.length) {
    classified.principles = uniqueItems(notes.map(note => note.title || firstSentence(note.content)).filter(Boolean)).slice(0, SECTION_LIMIT);
  }
  return classified;
}

function noteCandidates(note) {
  const values = [];
  if (note.title && !isGenericTitle(note.title)) values.push(note.title);
  for (const sentence of note.content.split(/[。！？!?；;\n]+/u)) {
    const clean = compactExcerpt(sentence);
    if (clean) values.push(clean);
    if (values.length >= 4) break;
  }
  return values;
}

function candidateBucket(value, note) {
  const text = `${value} ${note.category} ${note.noteKind}`;
  if (/(避免|不要|误区|反例|盲点|风险|失败|代价|局限|偏见|陷阱)/u.test(text)) return "antiPatterns";
  if (/(步骤|行动|练习|方法|流程|清单|提问|复盘|执行|尝试|操作)/u.test(text)) return "techniques";
  if (/(框架|模型|系统|结构|循环|层次|机制|地图|视角)/u.test(text)) return "frameworks";
  return "principles";
}

function renderSkillMarkdown(artifact) {
  const bookLabel = artifact.book.author ? `《${artifact.book.title}》 · ${artifact.book.author}` : `《${artifact.book.title}》`;
  const sections = [
    ["核心框架", artifact.skill.frameworks],
    ["可复用原则", artifact.skill.principles],
    ["可执行练习", artifact.skill.techniques],
    ["反模式与盲点", artifact.skill.antiPatterns],
  ].filter(([, values]) => values.length);
  return [
    "---",
    `name: ${artifact.skill.name}`,
    `description: ${yamlInline(artifact.skill.description)}`,
    "metadata:",
    "  source: account-local-book-notes",
    `  note_count: ${artifact.source.noteCount}`,
    `  generated_at: ${artifact.generatedAt}`,
    "---",
    "",
    `# ${bookLabel} 阅读 Skill`,
    "",
    "## 使用方式",
    "",
    "- 在遇到类似议题时，先从下面的框架、原则和练习中选择一个最贴近当前问题的切入点。",
    "- 将它作为复盘与提问的脚手架，而不是替代原书或原始笔记的结论。",
    "",
    ...sections.flatMap(([heading, values]) => [
      `## ${heading}`,
      "",
      ...values.map(value => `- ${value}`),
      "",
    ]),
    "## 数据边界",
    "",
    "- 此文件仅由当前账户中该书的笔记在服务端本地生成；生成过程不会把笔记发送给外部 AI 平台。",
    "- 请在使用前结合原书上下文复核；这里保留的是可复用线索，不是对全书的完整替代。",
    "",
  ].join("\n");
}

function uniqueItems(values) {
  const seen = new Set();
  return values.filter(value => {
    const key = String(value || "").replace(/\s+/gu, " ").trim().toLocaleLowerCase("zh-CN");
    if (!key || seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

function cleanInline(value) {
  return compactExcerpt(String(value ?? "").replace(/^#+\s*/u, "").replace(/[<>]/gu, ""));
}

function cleanBody(value) {
  return String(value ?? "").replace(/\r\n?/gu, "\n").trim();
}

function compactExcerpt(value) {
  const text = String(value ?? "").replace(/^[-*+\d.、\s]+/u, "").replace(/[*_`>#]/gu, "").replace(/\s+/gu, " ").trim();
  if (!text) return "";
  return text.length > EXCERPT_LIMIT ? `${text.slice(0, EXCERPT_LIMIT - 1).trimEnd()}…` : text;
}

function firstSentence(value) {
  return compactExcerpt(String(value || "").split(/[。！？!?；;\n]+/u)[0]);
}

function isGenericTitle(value) {
  return /^(笔记|摘录|想法|未命名笔记|读书笔记)(\s*\d+)?$/u.test(String(value || "").trim());
}

function safeSlug(value) {
  const ascii = String(value || "").toLocaleLowerCase("en-US").replace(/[^a-z0-9]+/gu, "-").replace(/^-+|-+$/gu, "").slice(0, 40);
  return `${ascii || "book"}-${stableHash(value).slice(0, 8)}`;
}

function stableHash(value) {
  let hash = 2166136261;
  for (const char of String(value || "")) {
    hash ^= char.codePointAt(0) || 0;
    hash = Math.imul(hash, 16777619);
  }
  return (hash >>> 0).toString(16).padStart(8, "0");
}

function yamlInline(value) {
  return JSON.stringify(String(value || ""));
}
