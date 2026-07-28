import { createHash } from "node:crypto";

export function buildAnalyticsDashboard(store, accountId, { now = Date.now() } = {}) {
  const notes = store.listNotes(accountId, { limit: 100000 });
  const consent = store.getConsent(accountId);
  const events = consent?.behaviorAnalytics ? store.listBehaviorEvents(accountId, Math.floor(now / 1000) - 366 * 24 * 3600, 100000) : [];
  const sources = countBy(notes, note => note.source || "unknown");
  const categories = countBy(notes, note => note.category || "未分类");
  const heatmap = buildHeatmap(notes, events, now);
  const weeklyTrend = buildWeeklyTrend(notes, now);
  const words = notes.reduce((sum, note) => sum + Number(note.wordCount || 0), 0);
  const official = store.listRecommendations(accountId, 20);
  const local = buildLocalRecommendations(categories, notes);
  const recommendations = consent?.recommendationPersonalization ? dedupeRecommendations([...official, ...local]).slice(0, 12) : [];
  return {
    generatedAt: new Date(now).toISOString(),
    consent,
    summary: {
      noteCount: notes.length,
      sourceCount: Object.keys(sources).length,
      estimatedWords: words,
      activeDays90: heatmap.filter(day => day.value > 0).length,
      connectedSources: Object.entries(sources).filter(([, count]) => count > 0).map(([source]) => source),
    },
    sourceDistribution: toSeries(sources),
    categoryDistribution: toSeries(categories).slice(0, 12),
    readingHeatmap: heatmap,
    weeklyTrend,
    recommendations,
    privacy: {
      behaviorAnalyticsEnabled: Boolean(consent?.behaviorAnalytics),
      recommendationPersonalizationEnabled: Boolean(consent?.recommendationPersonalization),
      rawNoteTextUsedInBehaviorEvents: false,
      modelOrTokenDependency: 0,
    },
  };
}

function buildHeatmap(notes, events, now) {
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
  const top = Object.entries(categories).sort((a, b) => b[1] - a[1]).slice(0, 3);
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
function noteEventAt(note) { return Number(note?.eventAt || note?.updatedAt || 0); }
