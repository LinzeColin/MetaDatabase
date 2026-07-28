import { createHash } from "node:crypto";

export function buildAnalyticsDashboard(store, accountId, { now = Date.now() } = {}) {
  const notes = store.listNotes(accountId, { limit: 100000 });
  const consent = store.getConsent(accountId);
  const events = consent?.behaviorAnalytics ? store.listBehaviorEvents(accountId, Math.floor(now / 1000) - 366 * 24 * 3600, 100000) : [];
  const wereadState = store.getWereadState(accountId);
  const officialReading = publicOfficialReading(wereadState?.summary?.officialReading);
  const sources = countBy(notes, note => note.source || "unknown");
  const categories = countBy(notes, note => note.category || "未分类");
  const heatmap = buildNoteActivityHeatmap(notes, events, now);
  const weeklyTrend = buildWeeklyTrend(notes, now);
  const words = notes.reduce((sum, note) => sum + Number(note.wordCount || 0), 0);
  const official = store.listRecommendations(accountId, 20);
  const local = buildLocalRecommendations(categories, notes);
  const recommendations = consent?.recommendationPersonalization ? dedupeRecommendations([...official, ...local]).slice(0, 12).map(withOfficialWeReadLink) : [];
  return {
    generatedAt: new Date(now).toISOString(),
    consent,
    summary: {
      noteCount: notes.length,
      sourceCount: Object.keys(sources).length,
      estimatedWords: words,
      noteActivityDays90: heatmap.filter(day => day.value > 0).length,
      // Retained for clients on the prior API shape. It is explicitly labelled
      // as note activity in the current UI and is never presented as reading time.
      activeDays90: heatmap.filter(day => day.value > 0).length,
      connectedSources: Object.entries(sources).filter(([, count]) => count > 0).map(([source]) => source),
    },
    sourceDistribution: toSeries(sources),
    categoryDistribution: toSeries(categories).slice(0, 12),
    noteActivityHeatmap: heatmap,
    readingHeatmap: heatmap,
    weeklyTrend,
    officialReading,
    recommendations,
    privacy: {
      behaviorAnalyticsEnabled: Boolean(consent?.behaviorAnalytics),
      recommendationPersonalizationEnabled: Boolean(consent?.recommendationPersonalization),
      rawNoteTextUsedInBehaviorEvents: false,
      modelOrTokenDependency: 0,
    },
  };
}

function buildNoteActivityHeatmap(notes, events, now) {
  const days = new Map();
  for (let index = 89; index >= 0; index -= 1) {
    const date = new Date(now - index * 86400000);
    const key = date.toISOString().slice(0, 10);
    days.set(key, 0);
  }
  for (const note of notes) {
    const key = new Date(noteEventAt(note) * 1000).toISOString().slice(0, 10);
    if (days.has(key)) days.set(key, days.get(key) + 1);
  }
  for (const event of events) {
    if (!["reading_completed", "reading_session"].includes(event.eventType)) continue;
    const key = new Date(Number(event.occurredAt) * 1000).toISOString().slice(0, 10);
    if (days.has(key)) days.set(key, days.get(key) + Math.max(1, Math.round(Number(event.value?.minutes || 0) / 15)));
  }
  return [...days].map(([date, value]) => ({ date, value, level: value === 0 ? 0 : value < 2 ? 1 : value < 5 ? 2 : value < 10 ? 3 : 4 }));
}

function buildWeeklyTrend(notes, now) {
  const weeks = [];
  for (let index = 11; index >= 0; index -= 1) {
    const end = new Date(now - index * 7 * 86400000);
    const start = new Date(end.getTime() - 7 * 86400000);
    const value = notes.filter(note => noteEventAt(note) * 1000 >= start.getTime() && noteEventAt(note) * 1000 < end.getTime()).length;
    weeks.push({ week: start.toISOString().slice(0, 10), value });
  }
  return weeks;
}

function buildLocalRecommendations(categories, notes) {
  const top = Object.entries(categories).filter(([category]) => !["微信读书", "未分类", "unknown"].includes(String(category).trim().toLowerCase())).sort((a, b) => b[1] - a[1]).slice(0, 3);
  return top.map(([category, count], index) => ({
    id: `local:${hash(`${category}:${count}`)}`,
    source: "account-pattern",
    title: `继续探索「${category}」`,
    author: null,
    reason: `你的账户中有 ${count} 条相关笔记；这是基于账户内元数据的可解释建议。`,
    deepLink: null,
    score: 50 - index,
  })).concat(notes.length === 0 ? [{
    id: "local:first-import",
    source: "onboarding",
    title: "先导入第一批阅读笔记",
    author: null,
    reason: "完成一次微信读书、Notion、Obsidian、GitHub 或 Google Drive 导入后，系统才能形成可靠画像。",
    deepLink: null,
    score: 100,
  }] : []);
}

function countBy(items, keyFn) {
  const output = {};
  for (const item of items) { const key = String(keyFn(item)); output[key] = (output[key] || 0) + 1; }
  return output;
}
function toSeries(record) { return Object.entries(record).sort((a, b) => b[1] - a[1]).map(([label, value]) => ({ label, value })); }
function hash(value) { return createHash("sha256").update(value).digest("hex").slice(0, 16); }
function dedupeRecommendations(items) { const seen = new Set(); return items.filter(item => { const key = `${item.title}\u0000${item.author || ""}`.toLowerCase(); if (seen.has(key)) return false; seen.add(key); return true; }).sort((a, b) => Number(b.score || 0) - Number(a.score || 0)); }
function withOfficialWeReadLink(item) {
  if (item?.source !== "weread-official") return item;
  if (item?.deepLinkVerified !== true) return { ...item, deepLink: null };
  const existing = safeOfficialWeReadLink(item.deepLink);
  return existing ? { ...item, deepLink: existing } : { ...item, deepLink: null };
}
function safeOfficialWeReadLink(value) {
  try {
    const url = new URL(String(value));
    if (url.protocol === "weread:") return url.toString();
    return url.protocol === "https:" && url.hostname === "weread.qq.com" ? url.toString() : null;
  } catch { return null; }
}
function noteEventAt(note) { return Number(note?.eventAt || note?.updatedAt || 0); }

function publicOfficialReading(value) {
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;
  const statistics = {};
  for (const mode of ["weekly", "monthly", "annually", "overall"]) {
    const raw = value.statistics?.[mode];
    if (!raw || typeof raw !== "object" || Array.isArray(raw)) continue;
    const metric = {
      mode,
      totalReadingTimeSeconds: safeMetric(raw.totalReadingTimeSeconds),
      totalReadingDays: safeMetric(raw.totalReadingDays),
      totalFinishedBooks: safeMetric(raw.totalFinishedBooks),
    };
    if (Object.values(metric).some(item => item !== null && item !== mode)) statistics[mode] = metric;
  }
  if (!Object.keys(statistics).length) return null;
  const categories = Array.isArray(value.preferredCategories) ? value.preferredCategories.map(item => ({
    label: safeLabel(item?.label, 120),
    readingTimeSeconds: safeMetric(item?.readingTimeSeconds),
    readingCount: safeMetric(item?.readingCount),
  })).filter(item => item.label).slice(0, 12) : [];
  const hours = Array.isArray(value.preferredHours) ? value.preferredHours.map(item => ({ hour: Number(item?.hour) }))
    .filter(item => Number.isInteger(item.hour) && item.hour >= 0 && item.hour < 24).slice(0, 4) : [];
  return {
    source: "weread-official-readdata-detail",
    freshness: ["CURRENT", "PARTIAL", "STALE"].includes(value.freshness) ? value.freshness : "STALE",
    collectedAt: safeMetric(value.collectedAt),
    statistics,
    preferredCategories: categories,
    preferredHours: hours,
  };
}

function safeMetric(value) { const number = Number(value); return Number.isFinite(number) && number >= 0 ? Math.floor(number) : null; }
function safeLabel(value, maxLength) { return String(value ?? "").replace(/[\u0000-\u001f\u007f]/g, " ").replace(/\s+/g, " ").trim().slice(0, maxLength); }
