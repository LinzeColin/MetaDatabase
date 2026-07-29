'use strict';
const TEMPLATES = Object.freeze([
  '现在最重要的一件事是什么？回复一句话即可。',
  '你准备先完成哪个最小动作？',
  '这件事完成了多少？下一步只写一个动作。',
]);
function localHour(date, offsetMinutes) {
  const ms = new Date(date).getTime() + Number(offsetMinutes || 0) * 60_000;
  return new Date(ms).getUTCHours();
}
function buildCheckin({ userId, scheduledAt, timezoneOffsetMinutes = 0, quietStartHour = 22, quietEndHour = 8, enabled = true, sequence = 0 }) {
  if (!enabled) return { action:'skip_disabled', modelCalls:0 };
  const hour = localHour(scheduledAt, timezoneOffsetMinutes);
  const quiet = quietStartHour > quietEndHour ? (hour >= quietStartHour || hour < quietEndHour) : (hour >= quietStartHour && hour < quietEndHour);
  if (quiet) return { action:'skip_quiet_hours', modelCalls:0 };
  const index = Math.abs(Number(sequence || 0)) % TEMPLATES.length;
  return { action:'send_template', text:TEMPLATES[index], userId, modelCalls:0 };
}
module.exports = { TEMPLATES, buildCheckin };
