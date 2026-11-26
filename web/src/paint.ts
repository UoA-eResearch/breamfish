// Painting a grid onto the map, one tile at a time, at the resolution of the
// screen. The seabed layers (seabed.ts) and the habitat index (habitat.ts) are
// both grids of cells in NZTM; this is how either becomes a picture. Nothing
// here measures, estimates or rates anything.

import { latitudeTerms, project } from "./nztm";

/** One layer's stored integers: the grid row by row from the north-west, gzip-compressed. */
export async function loadGrid(url: string, dtype: "uint8" | "uint16", cells: number): Promise<Uint8Array | Uint16Array> {
  const response = await fetch(url, { cache: "no-cache" });
  if (!response.ok) throw new Error(`${url}: HTTP ${response.status}`);
  let bytes = new Uint8Array(await response.arrayBuffer());
  // The files are gzip. A server may already have unpacked them on the way
  // (Content-Encoding), so look at the bytes rather than trust the name.
  if (bytes[0] === 0x1f && bytes[1] === 0x8b) {
    const stream = new Blob([bytes]).stream().pipeThrough(new DecompressionStream("gzip"));
    bytes = new Uint8Array(await new Response(stream).arrayBuffer());
  }
  const size = dtype === "uint16" ? 2 : 1;
  if (bytes.length !== cells * size) throw new Error(`${url}: ${bytes.length} bytes, expected ${cells * size}`);
  if (dtype === "uint8") return bytes;
  // Stored little-endian; read it that way whatever the machine.
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  const values = new Uint16Array(cells);
  for (let i = 0; i < cells; i++) values[i] = view.getUint16(i * 2, true);
  return values;
}

export type Rgba = [number, number, number, number];

/** A grid of cells of one size, laid from the north-west corner of the 100 m grid. */
export interface Lattice<T> {
  cells: T;
  ncols: number;
  nrows: number;
  cellM: number;
}

/**
 * A copy of a 100 m grid carried two cells past the shore, onto the land: the
 * map draws its own land over the seabed layers, so its coastline is the one
 * seen, and paint has to reach under it. A land cell takes the mean of its
 * neighbours that have a value (or, for classes, the first of them). Nothing
 * but painting uses the copy. `land` says which cells may be filled.
 */
export function pastShore<T extends Uint8Array | Uint16Array>(cells: T, land: Uint8Array, ncols: number, mean: boolean): T {
  let from = cells;
  let dry = land;
  for (let step = 0; step < 2; step++) {
    const to = from.slice() as T;
    const still = dry.slice();
    for (let i = 0; i < to.length; i++) {
      if (!dry[i]) continue;
      const col = i % ncols;
      let total = 0;
      let count = 0;
      for (const j of [i - ncols, i + ncols, i - 1, i + 1, i - ncols - 1, i - ncols + 1, i + ncols - 1, i + ncols + 1]) {
        if (j < 0 || j >= to.length || dry[j] || Math.abs((j % ncols) - col) > 1) continue;
        if (!count || mean) total += from[j];
        count++;
      }
      if (!count) continue;
      to[i] = mean ? total / count : total;
      still[i] = 0;
    }
    from = to;
    dry = still;
  }
  return from;
}


// --- Painting a tile ---------------------------------------------------------------
// A map tile is a square of Web Mercator. The grids are in NZTM, which is turned
// about a degree from it here, so every pixel is placed on the grid by projection:
// exactly at every STEP pixels, and along straight lines in between. Over the
// largest tile the map asks for, that is out by under a metre.

const STEP = 32;

export interface TileFrame {
  /** For each pixel, metres east of the grid's west edge and south of its north edge. */
  east: Float32Array;
  south: Float32Array;
  metresPerPixel: number;
}

export function tileFrame(westE: number, northN: number, z: number, x: number, y: number, px: number): TileFrame {
  const nodes = px / STEP + 1;
  const world = 2 ** z;
  const nodeE = new Float64Array(nodes * nodes);
  const nodeN = new Float64Array(nodes * nodes);
  for (let j = 0; j < nodes; j++) {
    const mercatorY = (y + (j * STEP) / px) / world;
    const lat = (Math.atan(Math.sinh(Math.PI * (1 - 2 * mercatorY))) * 180) / Math.PI;
    const terms = latitudeTerms(lat);
    for (let i = 0; i < nodes; i++) {
      const [e, n] = project(terms, ((x + (i * STEP) / px) / world) * 360 - 180);
      nodeE[j * nodes + i] = e - westE;
      nodeN[j * nodes + i] = northN - n;
    }
  }
  const east = new Float32Array(px * px);
  const south = new Float32Array(px * px);
  for (let j = 0; j < px; j++) {
    const blockJ = Math.floor(j / STEP);
    const v = ((j % STEP) + 0.5) / STEP;
    for (let i = 0; i < px; i++) {
      const blockI = Math.floor(i / STEP);
      const u = ((i % STEP) + 0.5) / STEP;
      const a = blockJ * nodes + blockI;
      const b = a + nodes;
      const k = j * px + i;
      east[k] = (nodeE[a] * (1 - u) + nodeE[a + 1] * u) * (1 - v) + (nodeE[b] * (1 - u) + nodeE[b + 1] * u) * v;
      south[k] = (nodeN[a] * (1 - u) + nodeN[a + 1] * u) * (1 - v) + (nodeN[b] * (1 - u) + nodeN[b + 1] * u) * v;
    }
  }
  const metresPerPixel = Math.hypot(nodeE[1] - nodeE[0], nodeN[1] - nodeN[0]) / STEP;
  return { east, south, metresPerPixel };
}

const clamp01 = (value: number): number => (value < 0 ? 0 : value > 1 ? 1 : value);

/**
 * Colour a tile by a measured quantity in steps: `colours[b]` where the value is
 * under `steps[b]`, the last colour above them all. The value at a pixel is
 * drawn between the four cell centres around it, so a step in colour is a smooth
 * line and not the edge of a cell, and is softened over one pixel. Stored 0 is
 * no data; the paint ends halfway to such a cell.
 */
export function paintSteps(
  out: Uint8ClampedArray,
  frame: TileFrame,
  grid: Lattice<Uint16Array | Uint8Array>,
  toValue: { scale: number; offset: number },
  steps: number[],
  colours: Rgba[],
): void {
  const { cells, ncols, nrows, cellM } = grid;
  const { east, south } = frame;
  const pixelsPerCell = Math.max(1, cellM / frame.metresPerPixel);
  const { scale, offset } = toValue;
  const last = steps.length;
  for (let k = 0; k < east.length; k++) {
    const gx = east[k] / cellM - 0.5;
    const gy = south[k] / cellM - 0.5;
    const x0 = Math.floor(gx);
    const y0 = Math.floor(gy);
    if (x0 < -1 || y0 < -1 || x0 >= ncols || y0 >= nrows) continue;
    const fx = gx - x0;
    const fy = gy - y0;
    const i = y0 * ncols + x0;
    const left = x0 >= 0;
    const right = x0 + 1 < ncols;
    const top = y0 >= 0;
    const bottom = y0 + 1 < nrows;
    const s00 = left && top ? cells[i] : 0;
    const s10 = right && top ? cells[i + 1] : 0;
    const s01 = left && bottom ? cells[i + ncols] : 0;
    const s11 = right && bottom ? cells[i + ncols + 1] : 0;
    const w00 = (1 - fx) * (1 - fy);
    const w10 = fx * (1 - fy);
    const w01 = (1 - fx) * fy;
    const w11 = fx * fy;
    const weight = (s00 ? w00 : 0) + (s10 ? w10 : 0) + (s01 ? w01 : 0) + (s11 ? w11 : 0);
    const alpha = clamp01(0.5 + (weight - 0.5) * pixelsPerCell);
    if (alpha === 0) continue;
    const value = offset + (scale * (s00 * w00 + s10 * w10 + s01 * w01 + s11 * w11)) / weight;

    let band = 0;
    while (band < last && value >= steps[band]) band++;
    let [r, g, b] = colours[band];
    if (s00 && s10 && s01 && s11) {
      // How far, in pixels, to the nearest step; within half a pixel the two colours mix.
      const slope =
        (scale * Math.hypot((s10 - s00) * (1 - fy) + (s11 - s01) * fy, (s01 - s00) * (1 - fx) + (s11 - s10) * fx)) /
        pixelsPerCell;
      if (slope > 0) {
        const below = band > 0 ? (value - steps[band - 1]) / slope : 1;
        const above = band < last ? (steps[band] - value) / slope : 1;
        const other = below < above ? band - 1 : band + 1;
        const share = 0.5 + Math.min(below, above);
        if (share < 1) {
          const mix = colours[other];
          r = r * share + mix[0] * (1 - share);
          g = g * share + mix[1] * (1 - share);
          b = b * share + mix[2] * (1 - share);
        }
      }
    }
    const o = k * 4;
    out[o] = r;
    out[o + 1] = g;
    out[o + 2] = b;
    out[o + 3] = 255 * alpha;
  }
}

/**
 * Colour a tile by a class: `colours[classOf[stored]]`, where class 0 is left
 * clear. A pixel takes the class that holds most of the four cell centres around
 * it, weighted by how near each is. That rounds the corners of the cells off
 * without moving any boundary by more than half a cell, and the boundary is
 * softened over one pixel.
 */
export function paintClasses(
  out: Uint8ClampedArray,
  frame: TileFrame,
  grid: Lattice<Uint8Array>,
  classOf: Uint8Array,
  colours: (Rgba | undefined)[],
): void {
  const { cells, ncols, nrows, cellM } = grid;
  const { east, south } = frame;
  const pixelsPerCell = Math.max(1, cellM / frame.metresPerPixel);
  const share = new Float32Array(colours.length);
  for (let k = 0; k < east.length; k++) {
    const gx = east[k] / cellM - 0.5;
    const gy = south[k] / cellM - 0.5;
    const x0 = Math.floor(gx);
    const y0 = Math.floor(gy);
    if (x0 < -1 || y0 < -1 || x0 >= ncols || y0 >= nrows) continue;
    const fx = gx - x0;
    const fy = gy - y0;
    const i = y0 * ncols + x0;
    const left = x0 >= 0;
    const right = x0 + 1 < ncols;
    const top = y0 >= 0;
    const bottom = y0 + 1 < nrows;
    const c00 = left && top ? classOf[cells[i]] : 0;
    const c10 = right && top ? classOf[cells[i + 1]] : 0;
    const c01 = left && bottom ? classOf[cells[i + ncols]] : 0;
    const c11 = right && bottom ? classOf[cells[i + ncols + 1]] : 0;
    let first = c00;
    let lead = 1; // how far the leading class is ahead of the next, 0 to 1
    if (c00 !== c10 || c00 !== c01 || c00 !== c11) {
      share[c00] = share[c10] = share[c01] = share[c11] = 0;
      share[c00] += (1 - fx) * (1 - fy);
      share[c10] += fx * (1 - fy);
      share[c01] += (1 - fx) * fy;
      share[c11] += fx * fy;
      let second = -1;
      for (const c of [c10, c01, c11]) {
        if (c === first) continue;
        if (share[c] > share[first]) {
          second = first;
          first = c;
        } else if (second < 0 || (c !== second && share[c] > share[second])) {
          second = c;
        }
      }
      lead = share[first] - share[second];
    }
    // The boundary is where the two leading classes are level; half a pixel either side mixes.
    const own = clamp01(0.5 + (lead / 2) * pixelsPerCell);
    const colour = colours[first];
    const o = k * 4;
    if (own === 1) {
      if (!colour) continue;
      out[o] = colour[0];
      out[o + 1] = colour[1];
      out[o + 2] = colour[2];
      out[o + 3] = 255;
      continue;
    }
    // Mixed with the runner-up, which may be clear. Found again here: it is rare.
    let second = -1;
    for (const c of [c00, c10, c01, c11]) {
      if (c !== first && (second < 0 || share[c] > share[second])) second = c;
    }
    const other = colours[second];
    const a = (colour ? own : 0) + (other ? 1 - own : 0);
    if (a === 0) continue;
    const p = (colour ? own : 0) / a;
    out[o] = (colour?.[0] ?? 0) * p + (other?.[0] ?? 0) * (1 - p);
    out[o + 1] = (colour?.[1] ?? 0) * p + (other?.[1] ?? 0) * (1 - p);
    out[o + 2] = (colour?.[2] ?? 0) * p + (other?.[2] ?? 0) * (1 - p);
    out[o + 3] = 255 * a;
  }
}
