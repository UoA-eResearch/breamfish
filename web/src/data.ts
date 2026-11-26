// Shapes of the two files the pipeline publishes under /data/, and of the seabed
// manifest. The Python side (src/breamfish/publish.py, scripts/build_seabed.py) is
// the source of truth.

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

// --- Seabed grids ---------------------------------------------------------------
// /seabed/manifest.json, written by scripts/build_seabed.py. The grids it describes
// are read in seabed.ts.

export interface SeabedClass {
  code: number;
  key: string;
  label: string;
  /** Index into the manifest's quality list (depth sources only). */
  quality?: number;
  cells?: number;
  name?: string;
  url?: string;
  licence?: string;
}

/** value = offset + scale * stored; stored 0 means nothing here. */
export interface ScaledLayer {
  file: string;
  dtype: "uint8" | "uint16";
  scale: number;
  offset: number;
  unit: string;
  label: string;
  note?: string;
}

export interface ClassLayer {
  file: string;
  dtype: "uint8";
  label: string;
  classes: SeabedClass[];
}

export interface SeabedManifest {
  schema: number;
  built: string;
  grid: { crs: string; cell_m: number; west_e: number; north_n: number; ncols: number; nrows: number };
  /** West, south, east, north in degrees: the box the grid fits in. */
  bounds: [number, number, number, number];
  /** [longitude, latitude, easting, northing] worked out by PROJ. */
  projection_check: [number, number, number, number][];
  datum: { name: string; note: string };
  layers: {
    depth: ScaledLayer;
    depth_source: ClassLayer;
    slope: ScaledLayer;
    roughness: ScaledLayer;
    bottom: ClassLayer;
    bottom_source: ClassLayer;
  };
  quality: { code: number; key: string; label: string; detail?: string; cells: number }[];
  contours: { file: string; levels_m: number[]; note: string };
}

export async function loadJson<T>(path: string): Promise<T> {
  const response = await fetch(path, { cache: "no-cache" });
  if (!response.ok) throw new Error(`${path}: HTTP ${response.status}`);
  return (await response.json()) as T;
}
