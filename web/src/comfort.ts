// Words and symbols for the comfort rating. The rating itself is computed by
// the pipeline (src/breamfish/conditions.py); nothing here changes a rating.

import type { Style } from "./data";

export const STYLES: { id: Style; label: string; noun: string }[] = [
  { id: "boat", label: "Boat", noun: "boat fishing" },
  { id: "kayak", label: "Kayak", noun: "kayaks and small craft" },
  { id: "shore", label: "Shore", noun: "shore fishing" },
];

export interface ComfortClass {
  label: string;
  /** A symbol shown beside the colour, so the rating never relies on colour alone. */
  symbol: string;
  css: string;
}

const CLASSES: Record<number, ComfortClass> = {
  3: { label: "Good", symbol: "✓", css: "good" },
  2: { label: "Fair", symbol: "!", css: "fair" },
  1: { label: "Poor", symbol: "✕", css: "poor" },
  0: { label: "No data", symbol: "?", css: "none" },
};

export const comfortClass = (value: number | null | undefined): ComfortClass => CLASSES[value ?? 0] ?? CLASSES[0];

const LIMITS: Record<string, string> = {
  wind: "wind",
  gust: "gusts",
  swell: "waves",
  rain: "heavy rain",
  offshore_wind: "wind blowing offshore",
  onshore_wind: "strong onshore wind",
  wind_against_tide: "wind against the outgoing tide",
  no_data: "no forecast for this hour",
};

/** "Good for boat fishing", "Fair for kayaks and small craft: limited by gusts". */
export function comfortSentence(value: number, limit: string, style: Style): string {
  const cls = comfortClass(value);
  const noun = STYLES.find((s) => s.id === style)?.noun ?? "fishing";
  if (value === 0) return "No forecast for this hour";
  const reason = LIMITS[limit];
  return reason && limit !== "ok" ? `${cls.label} for ${noun}: limited by ${reason}` : `${cls.label} for ${noun}`;
}

const POINTS = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE", "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"];

/** Compass point a direction in degrees lies on, e.g. 225 -> "SW". */
export const compass = (degrees: number | null | undefined): string =>
  degrees == null ? "" : POINTS[Math.round((((degrees % 360) + 360) % 360) / 22.5) % 16];
