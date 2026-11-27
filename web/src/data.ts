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

/**
 * wind.json: a field of arrows over the map for each hour. Mirrors publish.build_wind.
 * u and v are the east and north parts of where the air is going. A row of the grid
 * has its own longitudes, because the weather model's cells do not line up from one
 * row to the next.
 */
export interface VectorField {
  schema: number;
  generated_at: string;
  fetched_at: string;
  /** The same hours as conditions.json. */
  hours: string[];
  unit: string;
  source: { id: string; name: string; cell_km: [number, number] };
  grid: { nrows: number; ncols: number; lats: number[]; lons: number[][] };
  /** One list per hour, a value per grid point row by row from the north-west; null for an hour with none. */
  u: (Series | null)[];
  v: (Series | null)[];
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
    /** Written by scripts/build_relief.py; absent until that has been run. */
    fine_roughness?: ScaledLayer & { bands_m: number[]; reading: string };
  };
  quality: { code: number; key: string; label: string; detail?: string; cells: number }[];
  /** The same depth merge on a finer grid, for drawing only. */
  drawing: {
    cell_m: number;
    ncols: number;
    nrows: number;
    note: string;
    /** Stored as differences from a prediction; see loadPredicted in seabed.ts. */
    depth: Omit<ScaledLayer, "label"> & { predictor: "plane" };
    /** A depth_source code, plus past_shore on the fringe carried onto the land. */
    source: { file: string; dtype: "uint8"; past_shore: number };
    /** Codes as in layers.bottom and layers.bottom_source. */
    bottom: { file: string; dtype: "uint8" };
    bottom_source: { file: string; dtype: "uint8" };
  };
  contours: { file: string; levels_m: number[]; note: string };
  /** Shaded relief, as raster tile archives. Written by scripts/build_relief.py. */
  relief?: {
    built: string;
    note: string;
    tile_px: number;
    exaggeration: number;
    lights: { azimuth_deg: number; altitude_deg: number; weight: number }[];
    /** In the order they are drawn. */
    archives: ReliefArchive[];
  };
}

export interface ReliefArchive {
  key: string;
  /** A PMTiles archive on this site. */
  url: string;
  /** Changes when the archive does; sent with the address so no stale piece is read. */
  version: string;
  tiles: number;
  bytes: number;
  min_zoom: number;
  max_zoom: number;
  cell_m: number;
  smooth_m: number;
  name: string;
  url_source: string;
  licence: string;
}

// --- Habitat index ----------------------------------------------------------------
// /habitat/manifest.json, written by scripts/build_habitat.py from the species file
// (src/breamfish/species/snapper.toml). The grids it describes are read in habitat.ts.

export type Season = "summer" | "autumn" | "winter" | "spring";

/** [value, suitability] pairs, with straight lines between them. */
export type Curve = [number, number][];

export interface HabitatFactor {
  key: string;
  label: string;
  weight: number;
  unit?: string;
  confidence?: string;
  note?: string;
  limits?: string;
  /** A factor that changes with the season has one curve for each. */
  curve?: Record<Season, { points: Curve; basis: string; judgement: string }>;
  points?: Curve;
  basis?: string;
  judgement?: string;
  /** A factor scored by class (bottom type): suitability for each class key. */
  scores?: Record<string, number>;
  judgements?: Record<string, string>;
  class_labels?: Record<string, string>;
  evidence: { ref: string; says: string }[];
  /** The factor's suitability grid, or one for each season. */
  files: string | Record<Season, string>;
}

export interface ValidationGroup {
  source: string;
  label: string;
  season: Season | null;
  places: number;
  auc: number;
  auc_low?: number;
  auc_high?: number;
  share_in_top_two_fifths: number;
}

export interface HabitatManifest {
  schema: number;
  built: string;
  species: { key: string; name: string; scientific_name: string; applies_to: string; summary: string };
  grid: { west_e: number; north_n: number; cell_m: number; ncols: number; nrows: number };
  /** The months of each season, 1 to 12. */
  seasons: Record<Season, number[]>;
  /** value = offset + scale * stored, for the index and for every factor; stored 0 is not rated. */
  score: { dtype: "uint8"; scale: number; offset: number };
  index: { files: Record<Season, string>; how: string };
  classes: {
    labels: string[];
    /** A cell is in the class above every boundary its stored index reaches. */
    breaks_stored: Record<Season, number[]>;
    cells: Record<Season, number[]>;
    note: string;
  };
  factors: HabitatFactor[];
  references: Record<string, { citation: string; url: string; read: string }>;
  not_rated: { reserve_cells: number; note: string };
  reach: {
    file: string;
    /** The bit of the reach grid that is set where a style of fishing gets to a cell. */
    bits: Record<Style, number>;
    within_m_of_mainland_shore: Record<Style, number | null>;
    cells: Record<Style, number>;
    shore_points: string;
    note: string;
  };
  validation: {
    window_m: number;
    records: number;
    unused: { no_month: number; outside_or_no_water: number };
    groups: ValidationGroup[];
    how_to_read: string;
    cautions: string[];
  };
  limits: string[];
}

export async function loadJson<T>(path: string): Promise<T> {
  const response = await fetch(path, { cache: "no-cache" });
  if (!response.ok) throw new Error(`${path}: HTTP ${response.status}`);
  return (await response.json()) as T;
}
