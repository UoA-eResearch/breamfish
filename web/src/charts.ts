// The four small charts for one zone and one local day: wind, waves, rain, tide.
// They share one time axis and one cursor; each has its own y axis and unit.

import uPlot from "uplot";
import "uplot/dist/uPlot.min.css";
import type { Conditions, Series, Zone } from "./data";
import { fmtHour, fmtTime, localParts, TZ, type Day } from "./time";

interface Theme {
  ink2: string;
  muted: string;
  grid: string;
  surface: string;
  shade: string;
  wind: string;
  gust: string;
  wave: string;
  rain: string;
  tide: string;
}

function readTheme(): Theme {
  const css = getComputedStyle(document.documentElement);
  const v = (name: string) => css.getPropertyValue(name).trim();
  return {
    ink2: v("--ink-2"),
    muted: v("--muted"),
    grid: v("--grid"),
    surface: v("--surface"),
    shade: v("--shade"),
    wind: v("--wind"),
    gust: v("--gust"),
    wave: v("--wave"),
    rain: v("--rain"),
    tide: v("--tide"),
  };
}

export interface ChartSet {
  resize(): void;
  destroy(): void;
}

interface SeriesSpec {
  label: string;
  values: Series;
  color: string;
  bars?: boolean;
  fill?: string;
}

interface ChartSpec {
  title: string;
  unit: string;
  series: SeriesSpec[];
  /** The y axis never tops out below this, so a calm day does not look dramatic. */
  minTop: number;
  /** Extra room above the tallest value, as a fraction, for labels drawn in the plot. */
  headroom: number;
  decimals: number;
  draw?: (u: uPlot) => void;
}

const HEIGHT = 128;
const FONT = '11px system-ui, -apple-system, "Segoe UI", sans-serif';

export function drawCharts(
  host: HTMLElement,
  conditions: Conditions,
  zone: Zone,
  day: Day,
  times: number[],
  now: number,
  onHover: (index: number | null) => void,
): ChartSet {
  const theme = readTheme();
  const dpr = window.devicePixelRatio || 1;
  const xs = day.idx.map((i) => times[i] / 1000);
  const pick = (series: Series) => day.idx.map((i) => series[i] ?? null);
  const startSec = day.start / 1000;
  const endSec = day.end / 1000;
  const syncKey = "breamfish";

  host.replaceChildren();

  // Text drawn inside a plot gets a surface-coloured outline, so it stays readable
  // where a line or the "now" marker runs behind it.
  const label = (ctx: CanvasRenderingContext2D, text: string, x: number, y: number) => {
    ctx.lineJoin = "round";
    ctx.lineWidth = 3 * dpr;
    ctx.strokeStyle = theme.surface;
    ctx.strokeText(text, x, y);
    ctx.fillStyle = theme.ink2;
    ctx.fillText(text, x, y);
  };

  const shadeNight = (u: uPlot) => {
    if (!day.sun) return;
    const { ctx, bbox } = u;
    const left = u.valToPos(startSec, "x", true);
    const sunrise = u.valToPos(Date.parse(day.sun.sunrise) / 1000, "x", true);
    const sunset = u.valToPos(Date.parse(day.sun.sunset) / 1000, "x", true);
    const right = u.valToPos(endSec, "x", true);
    ctx.save();
    ctx.fillStyle = theme.shade;
    ctx.fillRect(left, bbox.top, Math.max(0, sunrise - left), bbox.height);
    ctx.fillRect(sunset, bbox.top, Math.max(0, right - sunset), bbox.height);
    ctx.restore();
  };

  const nowLine = (u: uPlot) => {
    if (now < day.start || now > day.end) return;
    const { ctx, bbox } = u;
    const x = Math.round(u.valToPos(now / 1000, "x", true));
    ctx.save();
    ctx.strokeStyle = theme.ink2;
    ctx.lineWidth = dpr;
    ctx.setLineDash([3 * dpr, 3 * dpr]);
    ctx.beginPath();
    ctx.moveTo(x, bbox.top);
    ctx.lineTo(x, bbox.top + bbox.height);
    ctx.stroke();
    ctx.restore();
  };

  // Small arrows along the top of the wind chart showing where the wind is
  // blowing to, every three hours.
  const windArrows = (u: uPlot) => {
    const { ctx, bbox } = u;
    ctx.save();
    ctx.strokeStyle = theme.ink2;
    ctx.fillStyle = theme.ink2;
    ctx.lineWidth = 1.5 * dpr;
    for (const i of day.idx) {
      const from = zone.wind_dir[i];
      if (from == null || localParts(times[i]).hour % 3 !== 0) continue;
      const x = u.valToPos(times[i] / 1000, "x", true);
      if (x < bbox.left + 8 * dpr || x > bbox.left + bbox.width - 8 * dpr) continue;
      ctx.save();
      ctx.translate(x, bbox.top + 10 * dpr);
      ctx.rotate((((from + 180) % 360) * Math.PI) / 180);
      const r = 6 * dpr;
      ctx.beginPath();
      ctx.moveTo(0, r);
      ctx.lineTo(0, -r);
      ctx.stroke();
      ctx.beginPath();
      ctx.moveTo(0, -r - 1.5 * dpr);
      ctx.lineTo(-3 * dpr, -r + 3.5 * dpr);
      ctx.lineTo(3 * dpr, -r + 3.5 * dpr);
      ctx.closePath();
      ctx.fill();
      ctx.restore();
    }
    ctx.restore();
  };

  // Name each line at its right-hand end, so the two wind series are told
  // apart without relying on colour.
  const endLabels = (names: { text: string; values: Series; above: boolean }[]) => (u: uPlot) => {
    const { ctx, bbox } = u;
    ctx.save();
    ctx.font = `${11 * dpr}px system-ui, -apple-system, "Segoe UI", sans-serif`;
    ctx.textAlign = "right";
    for (const name of names) {
      let last = day.idx.length - 1;
      while (last >= 0 && name.values[day.idx[last]] == null) last--;
      if (last < 0) continue;
      const x = Math.min(u.valToPos(xs[last], "x", true), bbox.left + bbox.width) - 2 * dpr;
      const y = u.valToPos(name.values[day.idx[last]] as number, "y", true);
      ctx.textBaseline = name.above ? "bottom" : "top";
      label(ctx, name.text, x, y + (name.above ? -5 : 5) * dpr);
    }
    ctx.restore();
  };

  // Mark and label each high and low tide that falls on this day.
  const tideEvents = (u: uPlot) => {
    const { ctx, bbox } = u;
    ctx.save();
    ctx.font = `${11 * dpr}px system-ui, -apple-system, "Segoe UI", sans-serif`;
    ctx.textBaseline = "bottom";
    for (const event of conditions.tide.events) {
      const ms = Date.parse(event.t);
      if (ms < day.start || ms > day.end) continue;
      const x = u.valToPos(ms / 1000, "x", true);
      const y = u.valToPos(event.h, "y", true);
      ctx.beginPath();
      ctx.arc(x, y, 4 * dpr, 0, Math.PI * 2);
      ctx.fillStyle = theme.tide;
      ctx.fill();
      ctx.lineWidth = 2 * dpr;
      ctx.strokeStyle = theme.surface;
      ctx.stroke();
      const text = `${event.type === "high" ? "High" : "Low"} ${fmtTime(ms)}, ${event.h.toFixed(1)} m`;
      const half = ctx.measureText(text).width / 2;
      const clamped = Math.min(Math.max(x, bbox.left + half + 2 * dpr), bbox.left + bbox.width - half - 2 * dpr);
      ctx.textAlign = "center";
      label(ctx, text, clamped, y - 8 * dpr);
    }
    ctx.restore();
  };

  const specs: ChartSpec[] = [
    {
      title: "Wind",
      unit: "knots",
      minTop: 20,
      headroom: 0.3,
      decimals: 0,
      series: [
        { label: "Wind", values: zone.wind_kn, color: theme.wind },
        { label: "Gusts", values: zone.gust_kn, color: theme.gust },
      ],
      draw: (u) => {
        windArrows(u);
        endLabels([
          { text: "Gusts", values: zone.gust_kn, above: true },
          { text: "Wind", values: zone.wind_kn, above: false },
        ])(u);
      },
    },
    {
      title: "Waves",
      unit: "metres, open bay",
      minTop: 1.5,
      headroom: 0.1,
      decimals: 1,
      series: [{ label: "Wave height", values: zone.wave_m, color: theme.wave }],
    },
    {
      title: "Rain",
      unit: "mm per hour",
      minTop: 2,
      headroom: 0.1,
      decimals: 0,
      series: [{ label: "Rain", values: zone.rain_mm, color: theme.rain, bars: true, fill: theme.rain }],
    },
    {
      title: "Tide",
      unit: `metres above chart datum, ${conditions.tide.port}`,
      minTop: 3,
      headroom: 0.28,
      decimals: 0,
      series: [{ label: "Tide", values: conditions.tide.height, color: theme.tide }],
      draw: tideEvents,
    },
  ];

  const plots: uPlot[] = [];
  const width = () => Math.max(240, host.clientWidth);

  for (const spec of specs) {
    const figure = document.createElement("figure");
    figure.className = "chart";
    const caption = document.createElement("figcaption");
    const key =
      spec.series.length > 1
        ? `<span class="chart-key">${spec.series
            .map((s) => `<span><i style="background:${s.color}"></i>${s.label}</span>`)
            .join("")}</span>`
        : "";
    caption.innerHTML = `<span class="chart-title">${spec.title}</span><span class="chart-unit">${spec.unit}</span>${key}`;
    const plot = document.createElement("div");
    plot.className = "chart-plot";
    figure.append(caption, plot);
    host.append(figure);

    const options: uPlot.Options = {
      width: width(),
      height: HEIGHT,
      padding: [6, 6, 0, 0],
      tzDate: (ts) => uPlot.tzDate(new Date(ts * 1000), TZ),
      legend: { show: false },
      cursor: {
        sync: { key: syncKey },
        y: false,
        drag: { x: false, y: false },
        points: { size: 9, width: 2, fill: theme.surface },
      },
      scales: {
        x: { time: true, range: [startSec, endSec] },
        y: {
          range: (_u, _min, max) => {
            const top = Math.max(spec.minTop, (max ?? 0) * (1 + spec.headroom));
            return [0, Math.ceil(top * 2) / 2];
          },
        },
      },
      axes: [
        {
          font: FONT,
          stroke: theme.muted,
          size: 26,
          ticks: { show: false },
          grid: { stroke: theme.grid, width: 1 },
          splits: () => [0, 6, 12, 18, 24].map((h) => startSec + h * 3600).filter((s) => s <= endSec),
          values: (_u, splits) => splits.map((s) => (s >= endSec ? "" : fmtHour(s * 1000))),
        },
        {
          font: FONT,
          stroke: theme.muted,
          size: 34,
          space: 30,
          ticks: { show: false },
          grid: { stroke: theme.grid, width: 1 },
          values: (_u, splits) => splits.map((v) => v.toFixed(spec.decimals)),
        },
      ],
      series: [
        {},
        ...spec.series.map(
          (s): uPlot.Series => ({
            label: s.label,
            stroke: s.color,
            width: s.bars ? 0 : 2,
            fill: s.fill,
            points: { show: false },
            spanGaps: false,
            paths: s.bars ? uPlot.paths.bars!({ size: [0.62, 16], radius: 0.25 }) : undefined,
          }),
        ),
      ],
      hooks: {
        drawClear: [shadeNight],
        draw: [nowLine, ...(spec.draw ? [spec.draw] : [])],
        setCursor: [
          (u) => {
            const i = u.cursor.idx;
            onHover(i == null || (u.cursor.left ?? -1) < 0 ? null : day.idx[i]);
          },
        ],
      },
    };

    plots.push(new uPlot(options, [xs, ...spec.series.map((s) => pick(s.values))], plot));
  }

  return {
    resize: () => {
      const w = width();
      for (const plot of plots) plot.setSize({ width: w, height: HEIGHT });
    },
    destroy: () => {
      for (const plot of plots) plot.destroy();
      host.replaceChildren();
    },
  };
}
