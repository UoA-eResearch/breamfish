// The habitat index: how well each 100 m cell of the bay suits snapper, season
// by season. It is worked out in Python (src/breamfish/habitat.py, from the
// species file) and arrives here as grids; this module reads them, says what
// they hold at a cell, and paints them. It never recomputes the index, a
// factor or a class boundary.

import { loadJson, type HabitatManifest, type Season, type Style } from "./data";
import { loadGrid, paintClasses, paintSteps, pastShore, tileFrame, type Rgba } from "./paint";
import { TZ } from "./time";

const BASE = "/habitat/";

/** What the index says about one cell in one season. */
export interface HabitatPoint {
  season: Season;
  /** 1 (lowest) to 5 (highest); 0 where the cell is not rated. */
  class: number;
  label: string;
  /** Each factor's suitability from 0 to 1; null where it had no data and was left out. */
  factors: { key: string; label: string; suitability: number | null }[];
  /** Which styles of fishing are taken to reach the cell. */
  reach: Record<Style, boolean>;
}

export class Habitat {
  private index = new Map<Season, { cells: Uint8Array; painted: Uint8Array }>();
  private factors = new Map<string, Promise<Uint8Array>>();
  private reach: Uint8Array | null = null;

  private constructor(
    readonly manifest: HabitatManifest,
    /** 1 for each cell that is land, from the seabed grids: where paint may run under the shore. */
    private land: Uint8Array,
  ) {}

  static async load(land: Uint8Array): Promise<Habitat> {
    const manifest = await loadJson<HabitatManifest>(`${BASE}manifest.json`);
    if (manifest.schema !== 1) throw new Error(`habitat manifest schema ${manifest.schema} is not one this page reads`);
    if (manifest.grid.ncols * manifest.grid.nrows !== land.length) throw new Error("habitat grid does not match the seabed grid");
    return new Habitat(manifest, land);
  }

  private grid(file: string): Promise<Uint8Array> {
    const { ncols, nrows } = this.manifest.grid;
    return loadGrid(BASE + file, "uint8", ncols * nrows) as Promise<Uint8Array>;
  }

  /** The season it is now in New Zealand. */
  seasonNow(): Season {
    const month = Number(new Intl.DateTimeFormat("en-NZ", { timeZone: TZ, month: "numeric" }).format(Date.now()));
    const seasons = Object.keys(this.manifest.seasons) as Season[];
    return seasons.find((season) => this.manifest.seasons[season].includes(month)) ?? seasons[0];
  }

  /** Fetch what is needed to paint a season: its index, and reach. */
  async loadSeason(season: Season): Promise<void> {
    const [cells, reach] = await Promise.all([
      this.index.has(season) ? null : this.grid(this.manifest.index.files[season]),
      this.reach ?? this.grid(this.manifest.reach.file),
    ]);
    this.reach = reach;
    if (cells) this.index.set(season, { cells, painted: pastShore(cells, this.land, this.manifest.grid.ncols, true) });
  }

  /**
   * What the index says at a cell, with what each factor contributed. Fetches
   * the factor grids the first time it is asked. Null if the season is not
   * loaded or the cell is outside the grid.
   */
  async inspect(cell: number, season: Season): Promise<HabitatPoint | null> {
    const index = this.index.get(season);
    if (!index || !this.reach || cell < 0) return null;
    const { classes, score, factors, reach } = this.manifest;
    const stored = index.cells[cell];
    const cls = stored === 0 ? 0 : 1 + classes.breaks_stored[season].filter((boundary) => stored >= boundary).length;
    const parts = await Promise.all(
      factors.map(async (factor) => {
        const file = typeof factor.files === "string" ? factor.files : factor.files[season];
        if (!this.factors.has(file)) this.factors.set(file, this.grid(file));
        const value = (await this.factors.get(file)!)[cell];
        return { key: factor.key, label: factor.label, suitability: value === 0 ? null : score.offset + score.scale * value };
      }),
    );
    const reached = (style: Style) => (this.reach![cell] & reach.bits[style]) !== 0;
    return {
      season,
      class: cls,
      label: cls === 0 ? "Not rated" : classes.labels[cls - 1],
      factors: parts,
      reach: { boat: reached("boat"), kayak: reached("kayak"), shore: reached("shore") },
    };
  }

  /**
   * One map tile of a season's index in its five classes. The index is drawn
   * between cell centres, so the classes meet along smooth lines, not cell edges.
   */
  paintIndex(season: Season, z: number, x: number, y: number, px: number, colour: (name: string) => Rgba): ImageData {
    const image = new ImageData(px, px);
    const index = this.index.get(season);
    if (!index) return image;
    const { grid, score, classes } = this.manifest;
    const frame = tileFrame(grid.west_e, grid.north_n, z, x, y, px);
    // A cell stored exactly at a boundary is in the class above it; half a step
    // lower keeps it there whatever the rounding.
    const steps = classes.breaks_stored[season].map((boundary) => score.offset + score.scale * (boundary - 0.5));
    const colours = classes.labels.map((_, i) => colour(`--habitat-${i + 1}`));
    const cells = { cells: index.painted, ncols: grid.ncols, nrows: grid.nrows, cellM: grid.cell_m };
    paintSteps(image.data, frame, cells, score, steps, colours);
    return image;
  }

  /** One map tile of the veil drawn over water a style of fishing does not reach. */
  paintVeil(style: Style, z: number, x: number, y: number, px: number, colour: (name: string) => Rgba): ImageData {
    const image = new ImageData(px, px);
    if (!this.reach) return image;
    const { grid, reach } = this.manifest;
    const frame = tileFrame(grid.west_e, grid.north_n, z, x, y, px);
    // Class 1 is water out of reach; land and water within reach are left clear.
    const classOf = new Uint8Array(256);
    for (let code = 1; code < 256; code++) classOf[code] = code & reach.bits[style] ? 0 : 1;
    const cells = { cells: this.reach, ncols: grid.ncols, nrows: grid.nrows, cellM: grid.cell_m };
    paintClasses(image.data, frame, cells, classOf, [undefined, colour("--veil")]);
    return image;
  }
}
