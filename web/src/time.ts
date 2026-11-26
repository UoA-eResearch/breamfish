// Everything on the site is shown in New Zealand time, whatever the visitor's
// device is set to. The data itself is in UTC.

import type { Conditions, SunDay } from "./data";

export const TZ = "Pacific/Auckland";
const HOUR = 3_600_000;

const partsFormat = new Intl.DateTimeFormat("en-CA", {
  timeZone: TZ,
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
  hour: "2-digit",
  hourCycle: "h23",
});
const timeFormat = new Intl.DateTimeFormat("en-NZ", { timeZone: TZ, hour: "numeric", minute: "2-digit", hour12: true });
const hourFormat = new Intl.DateTimeFormat("en-NZ", { timeZone: TZ, hour: "numeric", hour12: true });
const dayFormat = new Intl.DateTimeFormat("en-NZ", { timeZone: TZ, weekday: "short", day: "numeric", month: "short" });
const weekdayFormat = new Intl.DateTimeFormat("en-NZ", { timeZone: TZ, weekday: "short" });

/** Local calendar date (YYYY-MM-DD) and hour of day (0-23) for a UTC instant. */
export function localParts(ms: number): { date: string; hour: number } {
  const parts: Record<string, string> = {};
  for (const part of partsFormat.formatToParts(ms)) parts[part.type] = part.value;
  return { date: `${parts.year}-${parts.month}-${parts.day}`, hour: Number(parts.hour) % 24 };
}

export const fmtTime = (ms: number): string => timeFormat.format(ms).replace(/\s/g, " ");
export const fmtHour = (ms: number): string => hourFormat.format(ms).replace(/\s/g, " ");
export const fmtDay = (ms: number): string => dayFormat.format(ms).replace(",", "");
export const fmtWeekday = (ms: number): string => weekdayFormat.format(ms);

/** One local calendar day of the forecast window. */
export interface Day {
  key: string;
  label: string;
  /** Indexes into Conditions.hours that fall on this local date. */
  idx: number[];
  /** Local midnight at the start and end of the day, in ms. */
  start: number;
  end: number;
  sun?: SunDay;
}

export function buildDays(conditions: Conditions, times: number[], now: number): Day[] {
  const days: Day[] = [];
  const today = localParts(now).date;
  times.forEach((ms, i) => {
    const { date, hour } = localParts(ms);
    let day = days[days.length - 1];
    if (!day || day.key !== date) {
      const start = ms - hour * HOUR;
      const label = date === today ? "Today" : fmtDay(ms);
      day = { key: date, label, idx: [], start, end: start + 24 * HOUR, sun: conditions.sun.find((s) => s.date === date) };
      days.push(day);
    }
    day.idx.push(i);
  });
  // A day ends where the next one starts, which also absorbs daylight-saving shifts.
  for (let d = 0; d < days.length - 1; d++) days[d].end = days[d + 1].start;
  return days;
}

/** True when the instant falls between sunrise and sunset on its local date. */
export function isDaylight(ms: number, days: Day[]): boolean {
  const key = localParts(ms).date;
  const sun = days.find((d) => d.key === key)?.sun;
  if (!sun) return true;
  return ms >= Date.parse(sun.sunrise) && ms < Date.parse(sun.sunset);
}

/** "3 h ago", "25 min ago". */
export function ago(ms: number, now: number): string {
  const minutes = Math.max(0, Math.round((now - ms) / 60_000));
  if (minutes < 1) return "just now";
  if (minutes < 90) return `${minutes} min ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 48) return `${hours} h ago`;
  return `${Math.round(hours / 24)} days ago`;
}
