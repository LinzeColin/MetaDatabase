import { createHash } from "node:crypto";

export function buildAnalyticsDashboard(store, accountId, { now = Date.now() } = {}) {
  const notes = store.listNotes(accountId, { limit: 100000 });
  const consent = store.getConsent(accountId);
  const events = consent?.behaviorAnalytics ? store.listBehaviorEvents(accountId, Math.floor(now / 1000) - 366 * 24 * 3600, 100000) : [];
  const wereadState = store.getWereadState(accountId, { includeBookState: true });
  const officialReading = publicOfficialReading(wereadState?.summary?.officialReading);
  const sources = countBy(notes, note => note.source || "unknown");
  const categories = countBy(notes, note => note.category || "未分类");
  const heatmap = buildNoteActivityHeatmap(notes, events, now);
  const noteWeeklyTrend = buildWeeklyTrend(notes, now);
  const officialReadingPeriods = buildOfficialReadingPeriods(officialReading);
  const readingCategoryDistribution = buildReadingCategoryDistribution(officialReading);
  const readingProgress = buildReadingProgress(wereadState?.bookState);
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
    // Kept for existing API consumers. The account UI deliberately renders
    // category distribution instead, so a source label is never mistaken for
    // a reading preference.
    sourceDistribution: toSeries(sources),
    categoryDistribution: toSeries(categories).slice(0, 12),
    readingCategoryDistribution,
    noteActivityHeatmap: heatmap,
    readingHeatmap: heatmap,
    // `weeklyTrend` is the legacy name for note events. It is not an official
    // reading-time series and is labelled as a note trend in the UI.
    noteWeeklyTrend,
    weeklyTrend: noteWeeklyTrend,
    officialReadingPeriods,
    officialReading,
    readingProgress,
    dataFreshness: buildDataFreshness(wereadState, officialReading, notes, now),
    recommendations,
    privacy: {
      behaviorAnalyticsEnabled: Boolean(consent?.behaviorAnalytics),
      recommendationPersonalizationEnabled: Boolean(consent?.recommendationPersonalization),
      rawNoteTextUsedInBehaviorEvents: false,
      modelOrTokenDependency: 0,
    },
  };
}

function buildOfficialReadingPeriods(reading) {
  const modes = [
    ["weekly", "本周"],
    ["monthly", "本月"],
    ["annually", "本年"],
    ["overall", "累计"],
  ].map(([mode, label]) => ({ mode, label, ...(reading?.statistics?.[mode] || {}) }));
  const metric = ["totalReadingTimeSeconds", "totalReadingDays", "totalFinishedBooks"]
    .find(field => modes.some(item => safeMetric(item[field]) !== null));
  if (!metric) return { source: "weread-official-readdata-detail", metric: null, items: [] };
  return {
    source: "weread-official-readdata-detail",
    metric,
    items: modes.map(item => ({ mode: item.mode, label: item.label, value: safeMetric(item[metric]) }))
      .filter(item => item.value !== null),
  };
}

function buildReadingCategoryDistribution(reading) {
  const categories = Array.isArray(reading?.preferredCategories) ? reading.preferredCategories : [];
  const metric = ["readingTimeSeconds", "readingCount"].find(field => categories.some(item => safeMetric(item?.[field]) !== null));
  if (!metric) return null;
  return {
    source: "weread-official-readdata-detail",
    metric,
    items: categories.map(item => ({ label: safeLabel(item?.label, 120), value: safeMetric(item?.[metric]) }))
      .filter(item => item.label && item.value !== null)
      .sort((left, right) => right.value - left.value || left.label.localeCompare(right.label, "zh-CN"))
      .slice(0, 12),
  };
}

function buildReadingProgress(bookState) {
  const rows = Object.values(bookState || {}).map((state, index) => {
    if (!state || typeof state !== "object" || Array.isArray(state)) return null;
    const fingerprint = progressFromFingerprint(state.fingerprint);
    const progress = safeProgress(state.progress) ?? fingerprint.progress;
    if (progress === null) return null;
    return {
      label: safeLabel(state.title, 120) || `已同步书籍 ${index + 1}`,
      author: safeLabel(state.author, 120) || null,
      progress,
      readingTimeSeconds: safeMetric(state.readingTimeSeconds),
      updatedAt: safeMetric(state.progressUpdatedAt) ?? fingerprint.sourceTime,
    };
  }).filter(Boolean).sort((left, right) => Number(right.updatedAt || 0) - Number(left.updatedAt || 0) || right.progress - left.progress || left.label.localeCompare(right.label, "zh-CN"));
  return { source: "weread-official-book-progress", items: rows.slice(0, 12) };
}

function buildDataFreshness(wereadState, officialReading, notes, now) {
  const latestNoteEventAt = notes.reduce((latest, note) => Math.max(latest, noteEventAt(note)), 0);
  return {
    analyticsRecomputedAt: Math.floor(Number(now) / 1000),
    weread: {
      lastSyncedAt: safeMetric(wereadState?.lastSyncAt),
      officialReadingCollectedAt: safeMetric(officialReading?.collectedAt),
      latestNoteEventAt: latestNoteEventAt > 0 ? latestNoteEventAt : null,
      noteActivitySource: "real-note-event-time",
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
  const noteTimes = notes.map(note => noteEventAt(note) * 1000).filter(value => Number.isFinite(value) && value > 0);
  const current = Number(now);
  const latest = noteTimes.length ? Math.max(...noteTimes) : 0;
  const recentWindowStart = current - 84 * 86400000;
  // If an account's genuine history is older than the current twelve-week
  // window, anchor the chart on its last real event instead of rendering a
  // misleading all-zero trend.
  const hasRecentEvent = noteTimes.some(value => value >= recentWindowStart && value <= current);
  const anchor = hasRecentEvent || !latest ? current : latest + 86400000;
  const weeks = [];
  for (let index = 11; index >= 0; index -= 1) {
    const end = new Date(anchor - index * 7 * 86400000);
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
function safeProgress(value) { const number = Number(value); return Number.isFinite(number) && number >= 0 && number <= 100 ? Math.round(number * 10) / 10 : null; }
function progressFromFingerprint(value) {
  if (typeof value !== "string") return { progress: null, sourceTime: null };
  try {
    const parsed = JSON.parse(value);
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) return { progress: null, sourceTime: null };
    return { progress: safeProgress(parsed.progress), sourceTime: safeMetric(parsed.sourceTime) };
  } catch {
    return { progress: null, sourceTime: null };
  }
}
function safeLabel(value, maxLength) { return String(value ?? "").replace(/[\u0000-\u001f\u007f]/g, " ").replace(/\s+/g, " ").trim().slice(0, maxLength); }
