"use strict";

// 语气面板：主人在后台调，每一个真实 turn 生效。
//
// 存在 owner_persona 这张加密单行表里（迁移 010）。不放 service_state：那张表的
// value 列是明文，只收枚举和安全形状的短串，而这里有主人自己写的自由文本。
//
// 生效点只有一个：assembleRuntimeTurnText 把渲染出来的语气块贴在这一轮消息的最
// 前面。那个函数在 dispatchDurableRuntimeJob → dispatchPreparedTurn →
// buildRuntimeTurn 这条真实链路上（本仓已经四次栽在"代码存在但真实链路走不到"，
// 所以这里点名写清楚注入点在哪）。
//
// 为什么不写进 thread instructions：那是每条会话线程一份的东西，改一次语气要把
// 所有人的线程都刷一遍，而且旧线程刷不到。贴在每一轮前面虽然多花几十个 token，
// 但"改完下一句话就变"这件事是主人真正要的。

const MAX_NOTE_CHARS = 500;
const MAX_CALL_ME_CHARS = 24;

// 每个预设都是一句给模型的正面指令，不是形容词。写"少用感叹号"比写"沉稳"有用。
const TONE_PRESETS = Object.freeze([
  Object.freeze({
    id: "warm",
    label: "温和体贴",
    hint: "像认识很久的朋友，会顺着你的情绪走",
    instruction: "语气温和、体贴，像认识很久的朋友。先接住对方的情绪，再谈事情。",
  }),
  Object.freeze({
    id: "plain",
    label: "干脆利落",
    hint: "有话直说，不铺垫",
    instruction: "语气干脆，有话直说。不铺垫、不总结、不重复对方的问题。",
  }),
  Object.freeze({
    id: "playful",
    label: "轻松俏皮",
    hint: "会开玩笑，但不油腻",
    instruction: "语气轻松，可以开玩笑、可以接梗，但不要谄媚，也不要为了幽默而幽默。",
  }),
  Object.freeze({
    id: "steady",
    label: "稳重正式",
    hint: "用词讲究，适合谈正事",
    instruction: "语气稳重、用词讲究，适合谈正事。不用网络流行语。",
  }),
  Object.freeze({
    id: "quiet",
    label: "话少克制",
    hint: "能一句说完就不说两句",
    instruction: "话少、克制。能一句说完就不说两句，不主动展开。",
  }),
]);

const LENGTH_PRESETS = Object.freeze([
  Object.freeze({ id: "short", label: "很短", instruction: "回复控制在一两句话之内。" }),
  Object.freeze({ id: "medium", label: "适中", instruction: "回复保持在三五句话，说清楚就停。" }),
  Object.freeze({ id: "long", label: "详细", instruction: "可以展开说，但只在确实需要的时候。" }),
]);

const DEFAULT_TONE = "warm";
const DEFAULT_LENGTH = "medium";

// 不管选哪个语气都成立的几条。这些是"像个人"的底线，不交给主人调——把它们做成
// 选项等于允许把机器人调回机器腔。
const BASELINE = Object.freeze([
  "你在微信里和人聊天，不是在写文档。",
  "不要说「收到」「正在处理」「稍等」这类回执，也不要预告你接下来要做什么——直接说结果。",
  "不要自称 AI、助手、模型，不要说「作为一个……」。",
  "不要用「首先/其次/总结一下」这种结构词，不要列小标题，除非对方明确要一份清单。",
  "不知道就说不知道，不要编。",
]);

function toneById(id) {
  return TONE_PRESETS.find((entry) => entry.id === id) || null;
}

function lengthById(id) {
  return LENGTH_PRESETS.find((entry) => entry.id === id) || null;
}

function boundedText(value, max) {
  if (typeof value !== "string") {
    return "";
  }
  // 控制字符会把提示词拼接搞乱，也可能是注入尝试；连同首尾空白一起去掉。
  // 换行留着——主人写多行补充说明是正常的。
  const cleaned = value
    .replace(/[\u0000-\u0009\u000B-\u001F\u007F]/g, "")
    .trim();
  return cleaned.length > max ? cleaned.slice(0, max) : cleaned;
}

// 任何来源（数据库里的旧值、前端提交的表单）都过这一关，出来的一定是合法形状。
function normalizePersona(raw) {
  const source = raw && typeof raw === "object" ? raw : {};
  const tone = toneById(source.tone) ? source.tone : DEFAULT_TONE;
  const length = lengthById(source.length) ? source.length : DEFAULT_LENGTH;
  return Object.freeze({
    tone,
    length,
    emoji: source.emoji === true,
    callMe: boundedText(source.callMe, MAX_CALL_ME_CHARS),
    note: boundedText(source.note, MAX_NOTE_CHARS),
    updatedAt: typeof source.updatedAt === "string" ? source.updatedAt : "",
  });
}

function defaultPersona() {
  return normalizePersona({});
}

// 渲染成贴在每一轮最前面的那段文字。返回空串表示不贴（当前不会发生，基线永远在）。
function renderPersonaInstruction(persona) {
  const settings = normalizePersona(persona);
  const lines = ["[怎么说话]"];
  for (const line of BASELINE) {
    lines.push(`- ${line}`);
  }
  const tone = toneById(settings.tone);
  if (tone) {
    lines.push(`- ${tone.instruction}`);
  }
  const length = lengthById(settings.length);
  if (length) {
    lines.push(`- ${length.instruction}`);
  }
  lines.push(
    settings.emoji
      ? "- 可以用少量 emoji，一条最多一个。"
      : "- 不要用 emoji 和颜文字。",
  );
  if (settings.callMe) {
    lines.push(`- 称呼对方为「${settings.callMe}」。`);
  }
  if (settings.note) {
    // 主人自己写的补充。它是设置，不是对话内容，所以照原样给模型；上面的
    // boundedText 已经去掉了控制字符。
    lines.push(`- ${settings.note}`);
  }
  return lines.join("\n");
}

// 读写走 runtimeSpoolDatabase 的 owner_persona——一张加密单行表。主人写的
// 「怎么称呼我」和补充说明是自由文本，不能进 service_state 那个明文列。
//
// 读不出来时退回默认值而不是抛错：语气读不出来不该让一条消息发不出去。
class PersonaStore {
  constructor({ database = null } = {}) {
    this.database = database;
  }

  read() {
    if (!this.database || typeof this.database.readOwnerPersona !== "function") {
      return defaultPersona();
    }
    try {
      const row = this.database.readOwnerPersona();
      if (!row) {
        return defaultPersona();
      }
      return normalizePersona({ ...row.value, updatedAt: row.updatedAt });
    } catch {
      return defaultPersona();
    }
  }

  write(raw) {
    if (!this.database || typeof this.database.writeOwnerPersona !== "function") {
      const error = new Error("PERSONA_STORE_UNAVAILABLE");
      error.code = "PERSONA_STORE_UNAVAILABLE";
      throw error;
    }
    const next = normalizePersona(raw);
    this.database.writeOwnerPersona({
      tone: next.tone,
      length: next.length,
      emoji: next.emoji,
      callMe: next.callMe,
      note: next.note,
    });
    return this.read();
  }
}

module.exports = {
  BASELINE,
  DEFAULT_LENGTH,
  DEFAULT_TONE,
  LENGTH_PRESETS,
  MAX_CALL_ME_CHARS,
  MAX_NOTE_CHARS,
  PersonaStore,
  TONE_PRESETS,
  defaultPersona,
  normalizePersona,
  renderPersonaInstruction,
};
