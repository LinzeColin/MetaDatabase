export type VisitorTime = {
  date: string;
  greeting: string;
  time: string;
  weekday: string;
};

const weekdays = ["星期日", "星期一", "星期二", "星期三", "星期四", "星期五", "星期六"];

export function formatVisitorTime(now = new Date()): VisitorTime {
  const hour = now.getHours();
  const greeting = hour < 11
    ? "早上好，小张张～"
    : hour < 14
      ? "中午好，小张张～"
      : hour < 18
        ? "下午好，小张张～"
        : "晚上好，小张张～";

  return {
    date: `${now.getFullYear()}年${now.getMonth() + 1}月${now.getDate()}日`,
    greeting,
    time: `${String(hour).padStart(2, "0")}:${String(now.getMinutes()).padStart(2, "0")}`,
    weekday: weekdays[now.getDay()] ?? "",
  };
}
