"use client";

import { useEffect, useState } from "react";
import { formatVisitorTime, type VisitorTime } from "./visitor-time";

const refreshIntervalMs = 30_000;

export function useVisitorTime(reference: boolean): VisitorTime | null {
  const [visitorTime, setVisitorTime] = useState<VisitorTime | null>(null);

  useEffect(() => {
    if (reference) return;

    const refresh = () => setVisitorTime(formatVisitorTime());
    refresh();
    const timer = window.setInterval(refresh, refreshIntervalMs);
    return () => window.clearInterval(timer);
  }, [reference]);

  return reference ? null : visitorTime;
}

export function VisitorDate({
  fixtureDate,
  fixtureWeekday,
  reference,
}: {
  fixtureDate: string;
  fixtureWeekday: string;
  reference: boolean;
}) {
  const visitorTime = useVisitorTime(reference);

  if (reference) return <>{fixtureDate}&nbsp; {fixtureWeekday}</>;
  if (!visitorTime) return <>正在读取本地日期…</>;
  return <>{visitorTime.date}&nbsp; {visitorTime.weekday}</>;
}
