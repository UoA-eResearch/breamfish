// Shapes of the two files the pipeline publishes under /data/.
// The Python side (src/breamfish/publish.py) is the source of truth.

export type Style = "boat" | "kayak" | "shore";
export type Series = (number | null)[];

export interface TideEvent {
  t: string;
  type: "high" | "low";
  h: number;
}

export interface SunDay {
  date: string;
  dawn: string;
  sunrise: string;
  sunset: string;
  dusk: string;
}

export interface Zone {
  id: string;
  name: string;
  lat: number;
  lon: number;
  wind_kn: Series;
  gust_kn: Series;
  wind_dir: Series;
  rain_mm: Series;
  cloud_pct: Series;
  air_c: Series;
  wave_m: Series;
  wave_dir: Series;
  wave_period_s: Series;
  swell_m: Series;
  swell_period_s: Series;
  sst_c: Series;
  comfort: Record<Style, number[]>;
  limit: Record<Style, string[]>;
}

export interface Limits {
  wind_kn: number;
  gust_kn: number;
  wave_m: number;
}

export interface Thresholds {
  styles?: Record<Style, { good: Limits; fair: Limits }>;
  [key: string]: unknown;
}

export interface Conditions {
  schema: number;
  generated_at: string;
  timezone: string;
  hours: string[];
  tide: { port: string; datum: string; events: TideEvent[]; height: Series; rate: Series };
  sun: SunDay[];
  zones: Zone[];
  thresholds: Thresholds;
}

export interface SourceStatus {
  id: string;
  name: string;
  ok: boolean;
  stale: boolean;
  fetched_at: string | null;
  message: string;
}

export interface Status {
  generated_at: string;
  ok: boolean;
  sources: SourceStatus[];
}

export async function loadJson<T>(path: string): Promise<T> {
  const response = await fetch(path, { cache: "no-cache" });
  if (!response.ok) throw new Error(`${path}: HTTP ${response.status}`);
  return (await response.json()) as T;
}
