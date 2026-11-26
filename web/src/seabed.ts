// The seabed grids: depth, where each depth came from, slope, roughness and
// bottom type on a 100 m grid. They are static files written by
// scripts/build_seabed.py (the writer is scripts/seabed/publish.py); nothing
// here measures or estimates anything. This module reads the files, answers
// "what is at this spot?" and paints a layer as one image for the map.

import { loadJson, type ScaledLayer, type SeabedClass, type SeabedManifest } from "./data";

const BASE = "/seabed/";

/** What the map can colour the water by. */
export type Overlay = "depth" | "quality" | "bottom";

/** Depth bands in metres below chart datum. Each band is one step of the depth ramp. */
export const DEPTH_BANDS: { upTo: number; label: string }[] = [
  { upTo: 0, label: "Dries at low tide" },
  { upTo: 2, label: "0 to 2 m" },
  { upTo: 5, label: "2 to 5 m" },
  { upTo: 10, label: "5 to 10 m" },
  { upTo: 20, label: "10 to 20 m" },
  { upTo: 30, label: "20 to 30 m" },
  { upTo: 50, label: "30 to 50 m" },
  { upTo: Infinity, label: "Over 50 m" },
];

/** Which colour (a CSS custom property in style.css) each bottom class is drawn in.
    Shell and gravel share one: both are rare here, and a tap says which it is. */
export const BOTTOM_COLOUR: Record<string, string> = {
  rock: "--bottom-rock",
  sand: "--bottom-sand",
  mud: "--bottom-mud",
  shell: "--bottom-coarse",
  coarse: "--bottom-coarse",
  soft: "--bottom-soft",
};

export interface SeabedPoint {
  /** Metres below chart datum; negative dries at low tide. */
  depth: number;
  source: SeabedClass;
  quality: { key: string; label: string; detail?: string };
  bottom: SeabedClass;
  bottomSource: SeabedClass;
  /** Degrees; null where the depth is not from a surveyed surface. */
  slope: number | null;
  /** Metres; null where the depth is not from a surveyed surface. */
  roughness: number | null;
}

// --- NZTM2000 ------------------------------------------------------------------
// Longitude and latitude to New Zealand Transverse Mercator (EPSG:2193), by the
// series LINZ publishes for it. Good to a millimetre here. The manifest carries
// points worked out by PROJ, and load() refuses the grids if this disagrees.

const A = 6378137;
const F = 1 / 298.257222101;
const K0 = 0.9996;
const LON0 = (173 * Math.PI) / 180;
const FALSE_E = 1_600_000;
const FALSE_N = 10_000_000;
const E2 = 2 * F - F * F;
const E4 = E2 * E2;
const E6 = E4 * E2;
const A0 = 1 - E2 / 4 - (3 * E4) / 64 - (5 * E6) / 256;
const A2 = (3 / 8) * (E2 + E4 / 4 + (15 * E6) / 128);
const A4 = (15 / 256) * (E4 + (3 * E6) / 4);
const A6 = (35 * E6) / 3072;

/** The parts of the projection that depend on latitude alone. */
function latitudeTerms(latDeg: number) {
  const phi = (latDeg * Math.PI) / 180;
  const sin = Math.sin(phi);
  const cos = Math.cos(phi);
  const t = sin / cos;
  const m = A * (A0 * phi - A2 * Math.sin(2 * phi) + A4 * Math.sin(4 * phi) - A6 * Math.sin(6 * phi));
  const w = 1 - E2 * sin * sin;
  const nu = A / Math.sqrt(w);
  const psi = w / (1 - E2); // nu / rho
  return { sin, cos, t2: t * t, m, nu, psi };
}

function project(terms: ReturnType<typeof latitudeTerms>, lonDeg: number): [number, number] {
  const { sin, cos, t2, m, nu, psi } = terms;
  const w = (lonDeg * Math.PI) / 180 - LON0;
  const w2c2 = w * w * cos * cos;
  const t4 = t2 * t2;
  const t6 = t4 * t2;
  const psi2 = psi * psi;
  const e1 = (w2c2 / 6) * (psi - t2);
  const e2 = ((w2c2 * w2c2) / 120) * (4 * psi2 * psi * (1 - 6 * t2) + psi2 * (1 + 8 * t2) - psi * 2 * t2 + t4);
  const e3 = ((w2c2 * w2c2 * w2c2) / 5040) * (61 - 479 * t2 + 179 * t4 - t6);
  const n1 = (w2c2 / 12) * (4 * psi2 + psi - t2);
  const n2 =
    ((w2c2 * w2c2) / 360) *
    (8 * psi2 * psi2 * (11 - 24 * t2) - 28 * psi2 * psi * (1 - 6 * t2) + psi2 * (1 - 32 * t2) - psi * 2 * t2 + t4);
  const n3 = ((w2c2 * w2c2 * w2c2) / 20160) * (1385 - 3111 * t2 + 543 * t4 - t6);
  const easting = FALSE_E + K0 * nu * w * cos * (1 + e1 + e2 + e3);
  const northing = FALSE_N + K0 * (m + ((nu * sin * w * w) / 2) * cos * (1 + n1 + n2 + n3));
  return [easting, northing];
}

export const nztm = (lon: number, lat: number): [number, number] => project(latitudeTerms(lat), lon);

// --- Reading the files ------------------------------------------------------------

async function loadGrid(file: string, dtype: "uint8" | "uint16", cells: number): Promise<Uint8Array | Uint16Array> {
  const response = await fetch(BASE + file, { cache: "no-cache" });
  if (!response.ok) throw new Error(`${file}: HTTP ${response.status}`);
  let bytes = new Uint8Array(await response.arrayBuffer());
  // The files are gzip. A server may already have unpacked them on the way
  // (Content-Encoding), so look at the bytes rather than trust the name.
  if (bytes[0] === 0x1f && bytes[1] === 0x8b) {
    const stream = new Blob([bytes]).stream().pipeThrough(new DecompressionStream("gzip"));
    bytes = new Uint8Array(await new Response(stream).arrayBuffer());
  }
  const size = dtype === "uint16" ? 2 : 1;
  if (bytes.length !== cells * size) throw new Error(`${file}: ${bytes.length} bytes, expected ${cells * size}`);
  if (dtype === "uint8") return bytes;
  // Stored little-endian; read it that way whatever the machine.
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  const values = new Uint16Array(cells);
  for (let i = 0; i < cells; i++) values[i] = view.getUint16(i * 2, true);
  return values;
}

/** 0 means "nothing here" in every layer; otherwise value = offset + scale * stored. */
const scaled = (layer: ScaledLayer, stored: number): number | null =>
  stored === 0 ? null : layer.offset + layer.scale * stored;

type Rgba = [number, number, number, number];

export class Seabed {
  private constructor(
    readonly manifest: SeabedManifest,
    private depth: Uint16Array,
    private source: Uint8Array,
    private slope: Uint8Array,
    private roughness: Uint8Array,
    private bottom: Uint8Array,
    private bottomSource: Uint8Array,
  ) {}

  static async load(): Promise<Seabed> {
    const manifest = await loadJson<SeabedManifest>(`${BASE}manifest.json`);
    if (manifest.schema !== 1) throw new Error(`seabed manifest schema ${manifest.schema} is not one this page reads`);
    for (const [lon, lat, easting, northing] of manifest.projection_check) {
      const [e, n] = nztm(lon, lat);
      if (Math.hypot(e - easting, n - northing) > 0.5) throw new Error("seabed grid: projection check failed");
    }
    const { layers, grid } = manifest;
    const cells = grid.ncols * grid.nrows;
    const [depth, source, slope, roughness, bottom, bottomSource] = await Promise.all([
      loadGrid(layers.depth.file, layers.depth.dtype, cells),
      loadGrid(layers.depth_source.file, "uint8", cells),
      loadGrid(layers.slope.file, layers.slope.dtype, cells),
      loadGrid(layers.roughness.file, layers.roughness.dtype, cells),
      loadGrid(layers.bottom.file, "uint8", cells),
      loadGrid(layers.bottom_source.file, "uint8", cells),
    ]);
    return new Seabed(
      manifest,
      depth as Uint16Array,
      source as Uint8Array,
      slope as Uint8Array,
      roughness as Uint8Array,
      bottom as Uint8Array,
      bottomSource as Uint8Array,
    );
  }

  /** Index of the cell containing a projected point, or -1 outside the grid. */
  private cell(easting: number, northing: number): number {
    const { west_e, north_n, cell_m, ncols, nrows } = this.manifest.grid;
    const col = Math.floor((easting - west_e) / cell_m);
    const row = Math.floor((north_n - northing) / cell_m);
    return col < 0 || col >= ncols || row < 0 || row >= nrows ? -1 : row * ncols + col;
  }

  /** What the grids hold at a spot; null on land, outside the grid, or where there is no depth. */
  inspect(lon: number, lat: number): SeabedPoint | null {
    const i = this.cell(...nztm(lon, lat));
    if (i < 0 || this.source[i] === 0) return null;
    const { layers, quality } = this.manifest;
    const depth = scaled(layers.depth, this.depth[i]);
    const source = layers.depth_source.classes.find((c) => c.code === this.source[i]);
    const bottom = layers.bottom.classes.find((c) => c.code === this.bottom[i]);
    const bottomSource = layers.bottom_source.classes.find((c) => c.code === this.bottomSource[i]);
    if (depth == null || !source || !bottom || !bottomSource) return null;
    return {
      depth,
      source,
      quality: quality[source.quality ?? 0] ?? quality[0],
      bottom,
      bottomSource,
      slope: scaled(layers.slope, this.slope[i]),
      roughness: scaled(layers.roughness, this.roughness[i]),
    };
  }

  /**
   * One layer as an image whose pixels are evenly spaced in Web Mercator, the
   * map's own projection, so it can be pinned by its four corners with no
   * distortion. Each pixel takes the colour of the grid cell under its centre.
   * `colour` reads a CSS custom property as [r, g, b, a].
   */
  paint(overlay: Overlay, colour: (name: string) => Rgba): HTMLCanvasElement {
    const { grid, bounds, layers } = this.manifest;
    const [west, south, east, north] = bounds;
    const mercator = (lat: number) => Math.log(Math.tan(Math.PI / 4 + (lat * Math.PI) / 360));
    const top = mercator(north);
    const bottom = mercator(south);
    const width = grid.ncols * 2;
    const height = Math.round((width * (top - bottom)) / (((east - west) * Math.PI) / 180));

    // One colour per stored value.
    const palette = new Map<number, Rgba>();
    const depthColours = DEPTH_BANDS.map((_, band) => colour(`--depth-${band}`));
    if (overlay === "quality") {
      for (const cls of layers.depth_source.classes) {
        palette.set(cls.code, colour(`--quality-${this.manifest.quality[cls.quality ?? 0].key}`));
      }
    } else if (overlay === "bottom") {
      for (const cls of layers.bottom.classes) {
        const name = BOTTOM_COLOUR[cls.key];
        if (name) palette.set(cls.code, colour(name));
      }
    }

    const canvas = document.createElement("canvas");
    canvas.width = width;
    canvas.height = height;
    const context = canvas.getContext("2d")!;
    const image = context.createImageData(width, height);
    const lons = Array.from({ length: width }, (_, x) => west + ((x + 0.5) / width) * (east - west));
    for (let y = 0; y < height; y++) {
      const lat = (Math.atan(Math.exp(top + ((y + 0.5) / height) * (bottom - top))) * 360) / Math.PI - 90;
      const terms = latitudeTerms(lat);
      for (let x = 0; x < width; x++) {
        const i = this.cell(...project(terms, lons[x]));
        if (i < 0 || this.source[i] === 0) continue;
        let rgba: Rgba | undefined;
        if (overlay === "depth") {
          const depth = scaled(layers.depth, this.depth[i]);
          if (depth != null) rgba = depthColours[DEPTH_BANDS.findIndex((band) => depth < band.upTo)];
        } else {
          rgba = palette.get(overlay === "quality" ? this.source[i] : this.bottom[i]);
        }
        if (rgba) image.data.set(rgba, (y * width + x) * 4);
      }
    }
    context.putImageData(image, 0, 0);
    return canvas;
  }
}
