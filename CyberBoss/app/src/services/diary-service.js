const fs = require("fs");
const path = require("path");

const { resolveBodyInput } = require("./text-input");
const { BEIJING_ZONE, formatDateInZone, formatInZone } = require("./time/canonical-time");

class DiaryService {
  constructor({ config }) {
    this.config = config;
  }

  async append({ text = "", textFile = "", title = "", date = "", time = "" } = {}) {
    const body = await resolveBodyInput({ text, textFile });
    if (!body) {
      throw new Error("Diary content cannot be empty. Pass text or textFile.");
    }

    const now = new Date();
    const dateString = date || formatDate(now);
    const timeString = time || formatTime(now);
    const filePath = path.join(this.config.diaryDir, `${dateString}.md`);
    const entry = buildDiaryEntry({
      timeString,
      title,
      body,
    });

    fs.mkdirSync(this.config.diaryDir, { recursive: true });
    const prefix = fs.existsSync(filePath) && fs.statSync(filePath).size > 0 ? "\n\n" : "";
    fs.appendFileSync(filePath, `${prefix}${entry}`, "utf8");
    return {
      filePath,
      date: dateString,
      time: timeString,
      body,
    };
  }
}

function buildDiaryEntry({ timeString, title, body }) {
  const heading = title ? `## ${timeString} ${String(title).trim()}` : `## ${timeString}`;
  return `${heading}\n\n${body}`;
}

// 日记按天归档，「哪一天」的边界必须按时区切，不能按 UTC——北京时间 0 点到
// 8 点写的东西，按 UTC 切会掉进前一天的那一篇里。
function formatDate(date) {
  return formatDateInZone(date, BEIJING_ZONE);
}

function formatTime(date) {
  return formatInZone(date, BEIJING_ZONE).slice(11);
}

module.exports = {
  DiaryService,
  buildDiaryEntry,
  formatDate,
  formatTime,
};
