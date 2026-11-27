// The seabed grids: depth, where each depth came from, slope, roughness and
// bottom type on a 100 m grid, and the same depth on a 20 m grid for drawing.
// They are static files written by scripts/build_seabed.py (the writer is
// scripts/seabed/publish.py), and rough ground by scripts/build_relief.py;
// nothing here measures or estimates anything.
// This module reads the files, answers "what is at this spot?" and paints a
// layer one map tile at a time, at the resolution of the screen.

import { loadJson, type ScaledLayer, type SeabedClass, type SeabedManifest } from "./data";
import { nztm } from "./nztm";
import { loadGrid as loadLayer, paintClasses, paintSteps, pastShore, tileFrame, type Rgba } from "./paint";

const BASE = "/seabed/";

/** What the map can colour the water by. */
export type Overlay = "depth" | "quality" | "bottom" | "rough";

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
  /** Metres, over 10 m; null where the depth is not from the LiDAR. */
  roughGround: number | null;
}

// --- Reading the files ------------------------------------------------------------

/**
 * The 20 m drawing grid's depth, which is stored as what is left after guessing
 * each cell from its neighbours (to_bytes_predicted in scripts/seabed/publish.py):
 * every low byte, then every high byte, of the difference from west + north -
 * north-west, folded so that 0, -1, 1, -2 ... are stored as 0, 1, 2, 3 ...
 */
async function loadPredicted(file: string, ncols: number, nrows: number): Promise<Uint16Array> {
  const cells = ncols * nrows;
  const bytes = (await loadGrid(file, "uint8", cells * 2)) as Uint8Array;
  const values = new Uint16Array(cells);
  for (let row = 0, i = 0; row < nrows; row++) {
    for (let col = 0; col < ncols; col++, i++) {
      const folded = bytes[i] | (bytes[cells + i] << 8);
      const difference = (folded >>> 1) ^ -(folded & 1);
      const west = col ? values[i - 1] : 0;
      const north = row ? values[i - ncols] : 0;
      const northWest = row && col ? values[i - ncols - 1] : 0;
      values[i] = west + north - northWest + difference; // a Uint16Array wraps at 65,536
    }
  }
  return values;
}

/** 0 means "nothing here" in every layer; otherwise value = offset + scale * stored. */
const scaled = (layer: Pick<ScaledLayer, "scale" | "offset">, stored: number): number | null =>
  stored === 0 ? null : layer.offset + layer.scale * stored;

/** Tiles this fine and finer are painted from the 20 m grid: a pixel there is under 20 m. */
const DRAWING_FROM_Z = 12;

const loadGrid = (file: string, dtype: "uint8" | "uint16", cells: number) => loadLayer(BASE + file, dtype, cells);

export class Seabed {
  /** The 20 m grid, once loadDrawing() has fetched it. */
  private drawing: { depth: Uint16Array; source: Uint8Array; bottom: Uint8Array; bottomSource: Uint8Array } | null = null;
  private drawingRequest: Promise<boolean> | null = null;
  /** The 100 m grids as painted: carried a little past the shore (see pastShore). */
  private painted: { depth: Uint16Array; source: Uint8Array; bottom: Uint8Array };
  /** 1 for each 100 m cell that is land (or has no depth), 0 for water. */
  readonly land: Uint8Array;

  private constructor(
    readonly manifest: SeabedManifest,
    private depth: Uint16Array,
    private source: Uint8Array,
    private slope: Uint8Array,
    private roughness: Uint8Array,
    private bottom: Uint8Array,
    private bottomSource: Uint8Array,
    /** Rough ground, where the build has it; the rest of the seabed works without. */
    private roughGround: Uint8Array | null,
  ) {
    const land = source.map((code) => (code === 0 ? 1 : 0));
    this.land = land;
    const { ncols } = manifest.grid;
    this.painted = {
      depth: pastShore(depth, land, ncols, true),
      source: pastShore(source, land, ncols, false),
      bottom: pastShore(bottom, land, ncols, false),
    };
  }

  static async load(): Promise<Seabed> {
    const manifest = await loadJson<SeabedManifest>(`${BASE}manifest.json`);
    if (manifest.schema !== 2) throw new Error(`seabed manifest schema ${manifest.schema} is not one this page reads`);
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
    const rough = layers.fine_roughness;
    const roughGround = rough
      ? await loadGrid(rough.file, "uint8", cells).catch((error) => {
          console.error(error);
          return null;
        })
      : null;
    return new Seabed(
      manifest,
      depth as Uint16Array,
      source as Uint8Array,
      slope as Uint8Array,
      roughness as Uint8Array,
      bottom as Uint8Array,
      bottomSource as Uint8Array,
      roughGround as Uint8Array | null,
    );
  }

  /** Whether there is a rough-ground layer to show. */
  get hasRoughGround(): boolean {
    return this.roughGround !== null;
  }

  /**
   * Fetch the 20 m drawing grid, once. Resolves true when it is ready to paint
   * from; false if it could not be had, in which case the 100 m grid carries on.
   */
  loadDrawing(): Promise<boolean> {
    this.drawingRequest ??= (async () => {
      const { depth, source, bottom, bottom_source, ncols, nrows } = this.manifest.drawing;
      const bytes = (file: string) => loadGrid(file, "uint8", ncols * nrows) as Promise<Uint8Array>;
      try {
        const [depthCells, sourceCells, bottomCells, bottomSourceCells] = await Promise.all([
          loadPredicted(depth.file, ncols, nrows),
          bytes(source.file),
          bytes(bottom.file),
          bytes(bottom_source.file),
        ]);
        this.drawing = { depth: depthCells, source: sourceCells, bottom: bottomCells, bottomSource: bottomSourceCells };
        return true;
      } catch (error) {
        console.error(error);
        return false;
      }
    })();
    return this.drawingRequest;
  }

  /** Index of the cell containing a projected point, or -1 outside the grid. */
  private cell(easting: number, northing: number, cellM = this.manifest.grid.cell_m): number {
    const { west_e, north_n, cell_m, ncols, nrows } = this.manifest.grid;
    const finer = cell_m / cellM;
    const col = Math.floor((easting - west_e) / cellM);
    const row = Math.floor((north_n - northing) / cellM);
    return col < 0 || col >= ncols * finer || row < 0 || row >= nrows * finer ? -1 : row * ncols * finer + col;
  }

  /** Index of the 100 m cell under a point given in degrees, or -1 outside the grid. */
  cellAt(lon: number, lat: number): number {
    return this.cell(...nztm(lon, lat));
  }

  /**
   * What the grids hold at a spot; null on land, outside the grid, or where there
   * is no depth. Once the 20 m grid is loaded the depth, the bottom type and their
   * sources are read from that, so a tap agrees with what is drawn. Slope and
   * roughness are always the 100 m cell's.
   */
  inspect(lon: number, lat: number): SeabedPoint | null {
    const [easting, northing] = nztm(lon, lat);
    const i = this.cell(easting, northing);
    if (i < 0) return null;
    const { layers, quality, drawing } = this.manifest;
    const fine = this.drawing ? this.cell(easting, northing, drawing.cell_m) : -1;
    const sourceCode = this.drawing ? this.drawing.source[fine] : this.source[i];
    // Nothing known, or the fringe painted past the shore for the map's land to cover.
    if (sourceCode === 0 || (this.drawing && sourceCode >= drawing.source.past_shore)) return null;
    const depth = this.drawing ? scaled(drawing.depth, this.drawing.depth[fine]) : scaled(layers.depth, this.depth[i]);
    const source = layers.depth_source.classes.find((c) => c.code === sourceCode);
    const bottomCode = this.drawing ? this.drawing.bottom[fine] : this.bottom[i];
    const bottomSourceCode = this.drawing ? this.drawing.bottomSource[fine] : this.bottomSource[i];
    const bottom = layers.bottom.classes.find((c) => c.code === bottomCode);
    const bottomSource = layers.bottom_source.classes.find((c) => c.code === bottomSourceCode);
    if (depth == null || !source || !bottom || !bottomSource) return null;
    return {
      depth,
      source,
      quality: quality[source.quality ?? 0] ?? quality[0],
      bottom,
      bottomSource,
      slope: scaled(layers.slope, this.slope[i]),
      roughness: scaled(layers.roughness, this.roughness[i]),
      roughGround: this.roughGround && layers.fine_roughness ? scaled(layers.fine_roughness, this.roughGround[i]) : null,
    };
  }

  /**
   * One map tile of a layer, `px` pixels square. `colour` reads a CSS custom
   * property as [r, g, b, a]. Every layer comes from the 20 m grid on tiles fine
   * enough to show it, once it is loaded.
   */
  paintTile(overlay: Overlay, z: number, x: number, y: number, px: number, colour: (name: string) => Rgba): ImageData {
    const { grid, layers, quality, drawing } = this.manifest;
    const image = new ImageData(px, px);
    const frame = tileFrame(grid.west_e, grid.north_n, z, x, y, px);
    const coarse = { ncols: grid.ncols, nrows: grid.nrows, cellM: grid.cell_m };
    const fine = this.drawing && z >= DRAWING_FROM_Z ? { ncols: drawing.ncols, nrows: drawing.nrows, cellM: drawing.cell_m } : null;

    if (overlay === "depth") {
      const cells = fine ? { ...fine, cells: this.drawing!.depth } : { ...coarse, cells: this.painted.depth };
      const steps = DEPTH_BANDS.slice(0, -1).map((band) => band.upTo);
      const colours = DEPTH_BANDS.map((_, band) => colour(`--depth-${band}`));
      paintSteps(image.data, frame, cells, fine ? drawing.depth : layers.depth, steps, colours);
      return image;
    }
    if (overlay === "rough") {
      // Always the 100 m grid: that is the scale the layer is worked out at.
      const rough = layers.fine_roughness;
      if (!rough || !this.roughGround) return image;
      const colours = [...rough.bands_m, Infinity].map((_, band) => colour(`--rough-${band}`));
      paintSteps(image.data, frame, { ...coarse, cells: this.roughGround }, rough, rough.bands_m, colours);
      return image;
    }

    // One colour per class; several stored codes can share one (two kinds of survey
    // are both "measured"), and then no line is drawn between them.
    const classOf = new Uint8Array(256);
    const colours: (Rgba | undefined)[] = [undefined];
    const names: string[] = [""];
    const assign = (code: number, name: string | undefined) => {
      if (!name) return;
      if (!names.includes(name)) {
        names.push(name);
        colours.push(colour(name));
      }
      classOf[code] = names.indexOf(name);
    };
    if (overlay === "quality") {
      for (const cls of layers.depth_source.classes) {
        assign(cls.code, `--quality-${quality[cls.quality ?? 0].key}`);
        classOf[cls.code + drawing.source.past_shore] = classOf[cls.code];
      }
      const cells = fine ? { ...fine, cells: this.drawing!.source } : { ...coarse, cells: this.painted.source };
      paintClasses(image.data, frame, cells, classOf, colours);
    } else {
      for (const cls of layers.bottom.classes) assign(cls.code, BOTTOM_COLOUR[cls.key]);
      const cells = fine ? { ...fine, cells: this.drawing!.bottom } : { ...coarse, cells: this.painted.bottom };
      paintClasses(image.data, frame, cells, classOf, colours);
    }
    return image;
  }
}
