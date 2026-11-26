// A field of arrows drawn moving over the map: the forecast wind now, and any
// other field published in the same shape later (a finer wind, tidal currents).
//
// It draws what the pipeline published and works nothing out about fishing. The
// values between the published points are read off by straight-line
// interpolation, for drawing only.
//
// Streaks are white with a dark edge so they show over every layer in both
// themes. Strength is carried by how fast and far a streak runs and by its
// weight, never by colour: the map's colours are all spoken for.

import type * as maplibregl from "maplibre-gl";
import type { VectorField } from "./data";

/** Strength classes, in the field's own unit (knots for wind). The key in the layer control shows the same. */
export const FLOW_BANDS: { under: number; label: string; width: number }[] = [
  { under: 10, label: "Under 10 kn", width: 1.1 },
  { under: 15, label: "10 to 15 kn", width: 1.5 },
  { under: 20, label: "15 to 20 kn", width: 2 },
  { under: Infinity, label: "20 kn and over", width: 2.6 },
];

/** Screen pixels a second that a streak covers for each knot. Ten knots crosses a phone in about ten seconds. */
const PX_PER_S_PER_UNIT = 3.6;
/** Frames are drawn no closer together than this: about 30 a second. */
const FRAME_MS = 30;
/** How much of a trail is rubbed out each frame. A trail lasts about two thirds of a second. */
const FADE = 0.1;
/** One streak for every so many square CSS pixels of field on the screen. */
const PX_PER_STREAK = 1300;
const MAX_STREAKS = 1600;
/** How long a streak lives, in frames, before it starts again somewhere else. */
const LIFE = [40, 110];
/** Still arrows, for people who ask for less motion: one every so many CSS pixels. */
const ARROW_EVERY = 56;
/** Streaks thin out over this share of the field's width at its edges, so it has no hard border. */
const EDGE = 0.08;

const band = (speed: number): number => FLOW_BANDS.findIndex((b) => speed < b.under);

export class FlowLayer {
  private canvas = document.createElement("canvas");
  private ctx = this.canvas.getContext("2d")!;
  private field: VectorField | null = null;
  private hour = "";
  private u: (number | null)[] | null = null;
  private v: (number | null)[] | null = null;
  private shown = false;
  /** Longitude, latitude, frames left and whole life for each streak. */
  private streaks = new Float64Array(0);
  private timer = 0;
  private last = 0;
  private scale = 1;
  private reduced = window.matchMedia("(prefers-reduced-motion: reduce)");
  /** Set to draw still arrows whatever the device asks for. The device's own wish is the default. */
  still: boolean | null = null;
  private ink: string;
  private edge: string;

  constructor(private map: maplibregl.Map) {
    this.canvas.className = "flow";
    this.canvas.setAttribute("aria-hidden", "true");
    // Straight after the map's own canvas: over the map, under the markers and popups.
    map.getCanvas().insertAdjacentElement("afterend", this.canvas);
    const css = getComputedStyle(document.documentElement);
    this.ink = css.getPropertyValue("--flow").trim() || "#ffffff";
    this.edge = css.getPropertyValue("--flow-edge").trim() || "#0b0b0b";

    map.on("resize", this.fit);
    // Trails are on the screen, not on the map: when the map moves under them they go.
    map.on("move", this.wipe);
    map.on("moveend", this.restart);
    document.addEventListener("visibilitychange", this.restart);
    this.reduced.addEventListener("change", this.restart);
    this.fit();
  }

  /** Is there a field for the hour being shown? */
  get available(): boolean {
    return this.u !== null && this.v !== null;
  }

  /** How far apart the field's points are, north-south and east-west, in km. */
  get cellKm(): [number, number] | null {
    return this.field?.source.cell_km ?? null;
  }

  setField(field: VectorField | null): void {
    this.field = field;
    this.pick();
  }

  /** The hour to draw, as it is written in the published files. */
  setHour(iso: string): void {
    if (iso === this.hour) return;
    this.hour = iso;
    this.pick();
  }

  setShown(shown: boolean): void {
    if (shown === this.shown) return;
    this.shown = shown;
    this.restart();
  }

  private pick(): void {
    const i = this.field ? this.field.hours.indexOf(this.hour) : -1;
    const was = this.available;
    this.u = i < 0 ? null : (this.field!.u[i] ?? null);
    this.v = i < 0 ? null : (this.field!.v[i] ?? null);
    // Moving streaks pick up the new hour on their next step. Anything else is drawn afresh.
    if (was !== this.available || this.isStill) this.restart();
  }

  private get isStill(): boolean {
    return this.still ?? this.reduced.matches;
  }

  private get running(): boolean {
    return this.shown && this.available && !document.hidden;
  }

  /** The field at a place, as [east, north], or null outside it. */
  sample(lon: number, lat: number): [number, number] | null {
    const grid = this.field?.grid;
    if (!grid || !this.u || !this.v) return null;
    const { lats, lons, nrows, ncols } = grid;
    if (lat > lats[0] || lat < lats[nrows - 1]) return null;
    let row = 0;
    while (row < nrows - 2 && lat < lats[row + 1]) row++;
    const down = (lats[row] - lat) / (lats[row] - lats[row + 1]);
    // Each row of the model's cells sits a little east or west of the next,
    // so a place is found along each row by that row's own longitudes.
    const along = (r: number, values: (number | null)[]): number | null => {
      const line = lons[r];
      if (lon < line[0] || lon > line[ncols - 1]) return null;
      let col = 0;
      while (col < ncols - 2 && lon > line[col + 1]) col++;
      const a = values[r * ncols + col];
      const b = values[r * ncols + col + 1];
      if (a == null || b == null) return null;
      return a + ((b - a) * (lon - line[col])) / (line[col + 1] - line[col]);
    };
    const uTop = along(row, this.u);
    const uBottom = along(row + 1, this.u);
    const vTop = along(row, this.v);
    const vBottom = along(row + 1, this.v);
    if (uTop === null || uBottom === null || vTop === null || vBottom === null) return null;
    return [uTop + (uBottom - uTop) * down, vTop + (vBottom - vTop) * down];
  }

  /** The box every row of the field covers: [west, south, east, north]. */
  private get extent(): [number, number, number, number] | null {
    const grid = this.field?.grid;
    if (!grid) return null;
    const west = Math.max(...grid.lons.map((line) => line[0]));
    const east = Math.min(...grid.lons.map((line) => line[grid.ncols - 1]));
    return [west, grid.lats[grid.nrows - 1], east, grid.lats[0]];
  }

  /** 1 in the body of the field, falling to 0 at its edge. */
  private inside(lon: number, lat: number, [west, south, east, north]: [number, number, number, number]): number {
    const x = Math.min(lon - west, east - lon) / ((east - west) * EDGE);
    const y = Math.min(lat - south, north - lat) / ((north - south) * EDGE);
    return Math.max(0, Math.min(1, x, y));
  }

  private fit = (): void => {
    const box = this.map.getContainer();
    this.scale = Math.min(window.devicePixelRatio || 1, 2);
    this.canvas.width = Math.round(box.clientWidth * this.scale);
    this.canvas.height = Math.round(box.clientHeight * this.scale);
    this.restart();
  };

  private wipe = (): void => {
    this.ctx.setTransform(1, 0, 0, 1, 0, 0);
    this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);
  };

  /** Start again from a clean canvas: after the map has moved, or anything else has changed. */
  private restart = (): void => {
    cancelAnimationFrame(this.timer);
    this.timer = 0;
    this.wipe();
    this.canvas.hidden = !this.running;
    if (!this.running) return;
    if (this.isStill) {
      this.drawStill();
      return;
    }
    this.seed();
    this.last = 0;
    this.timer = requestAnimationFrame(this.step);
  };

  /** The part of the field that is on the screen, in longitude and latitude, and its size in CSS pixels. */
  private onScreen(): { west: number; south: number; east: number; north: number; area: number } | null {
    const extent = this.extent;
    if (!extent) return null;
    const bounds = this.map.getBounds();
    const west = Math.max(extent[0], bounds.getWest());
    const south = Math.max(extent[1], bounds.getSouth());
    const east = Math.min(extent[2], bounds.getEast());
    const north = Math.min(extent[3], bounds.getNorth());
    if (west >= east || south >= north) return null;
    const a = this.map.project([west, north]);
    const b = this.map.project([east, south]);
    return { west, south, east, north, area: Math.abs((b.x - a.x) * (b.y - a.y)) };
  }

  private seed(): void {
    const view = this.onScreen();
    const count = view ? Math.min(MAX_STREAKS, Math.round(view.area / PX_PER_STREAK)) : 0;
    this.streaks = new Float64Array(count * 4);
    if (!view) return;
    for (let i = 0; i < count; i++) {
      this.place(i, view);
      // Not all born at once, or they would all die at once too.
      this.streaks[i * 4 + 2] = Math.random() * this.streaks[i * 4 + 3];
    }
  }

  private place(i: number, view: { west: number; south: number; east: number; north: number }): void {
    const life = LIFE[0] + Math.random() * (LIFE[1] - LIFE[0]);
    this.streaks.set(
      [view.west + Math.random() * (view.east - view.west), view.south + Math.random() * (view.north - view.south), life, life],
      i * 4,
    );
  }

  private step = (now: number): void => {
    this.timer = requestAnimationFrame(this.step);
    if (now - this.last < FRAME_MS) return;
    // After a pause (a hidden tab, a slow frame) take one ordinary step, not a leap.
    const seconds = Math.min(now - this.last, 100) / 1000;
    this.last = now;
    const view = this.onScreen();
    const extent = this.extent;
    if (!view || !extent) return;

    const { ctx, map, streaks } = this;
    const width = this.canvas.width / this.scale;
    const height = this.canvas.height / this.scale;
    ctx.setTransform(this.scale, 0, 0, this.scale, 0, 0);
    ctx.globalCompositeOperation = "destination-out";
    ctx.globalAlpha = FADE;
    ctx.fillRect(0, 0, width, height);
    ctx.globalCompositeOperation = "source-over";

    const paths = FLOW_BANDS.map(() => new Path2D());
    for (let i = 0; i < streaks.length; i += 4) {
      const lon = streaks[i];
      const lat = streaks[i + 1];
      const wind = this.sample(lon, lat);
      if (!wind || --streaks[i + 2] <= 0) {
        this.place(i / 4, view);
        continue;
      }
      const from = map.project([lon, lat]);
      const x = from.x + wind[0] * PX_PER_S_PER_UNIT * seconds;
      const y = from.y - wind[1] * PX_PER_S_PER_UNIT * seconds;
      if (x < 0 || y < 0 || x > width || y > height) {
        this.place(i / 4, view);
        continue;
      }
      const to = map.unproject([x, y]);
      streaks[i] = to.lng;
      streaks[i + 1] = to.lat;
      // Near the field's edge only some streaks are drawn, fewer the nearer it is.
      const weight = this.inside(lon, lat, extent);
      if (weight < 1 && (i / 4) % 10 >= weight * 10) continue;
      const path = paths[band(Math.hypot(wind[0], wind[1]))];
      path.moveTo(from.x, from.y);
      path.lineTo(x, y);
    }

    ctx.lineCap = "round";
    // The dark edge first, a little wider, then the light line on top of it.
    ctx.globalAlpha = 0.4;
    ctx.strokeStyle = this.edge;
    FLOW_BANDS.forEach((b, n) => {
      ctx.lineWidth = b.width + 1.4;
      ctx.stroke(paths[n]);
    });
    ctx.globalAlpha = 0.95;
    ctx.strokeStyle = this.ink;
    FLOW_BANDS.forEach((b, n) => {
      ctx.lineWidth = b.width;
      ctx.stroke(paths[n]);
    });
    ctx.globalAlpha = 1;
  };

  /** One arrow at each point of a grid on the screen, pointing where the air is going. */
  drawStill(): void {
    this.wipe();
    if (!this.running) return;
    const { ctx, map } = this;
    const width = this.canvas.width / this.scale;
    const height = this.canvas.height / this.scale;
    ctx.setTransform(this.scale, 0, 0, this.scale, 0, 0);
    ctx.lineCap = "round";
    ctx.lineJoin = "round";
    const arrows = FLOW_BANDS.map(() => new Path2D());
    for (let y = ARROW_EVERY / 2; y < height; y += ARROW_EVERY) {
      for (let x = ARROW_EVERY / 2; x < width; x += ARROW_EVERY) {
        const at = map.unproject([x, y]);
        const wind = this.sample(at.lng, at.lat);
        if (!wind) continue;
        const speed = Math.hypot(wind[0], wind[1]);
        if (speed < 0.5) continue;
        // Longer for stronger, but never so long that neighbours touch.
        const length = Math.min(ARROW_EVERY * 0.8, 10 + speed * 1.2);
        const dx = (wind[0] / speed) * length;
        const dy = (-wind[1] / speed) * length;
        const tipX = x + dx / 2;
        const tipY = y + dy / 2;
        const path = arrows[band(speed)];
        path.moveTo(x - dx / 2, y - dy / 2);
        path.lineTo(tipX, tipY);
        // The head: two short strokes back from the tip.
        const head = 5;
        const angle = Math.atan2(dy, dx);
        for (const turn of [-0.5, 0.5]) {
          path.moveTo(tipX, tipY);
          path.lineTo(tipX - head * Math.cos(angle + turn), tipY - head * Math.sin(angle + turn));
        }
      }
    }
    ctx.globalAlpha = 0.45;
    ctx.strokeStyle = this.edge;
    FLOW_BANDS.forEach((b, n) => {
      ctx.lineWidth = b.width + 2;
      ctx.stroke(arrows[n]);
    });
    ctx.globalAlpha = 1;
    ctx.strokeStyle = this.ink;
    FLOW_BANDS.forEach((b, n) => {
      ctx.lineWidth = b.width;
      ctx.stroke(arrows[n]);
    });
  }
}
