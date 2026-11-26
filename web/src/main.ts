import "./style.css";
import { drawCharts, type ChartSet } from "./charts";
import { comfortClass, comfortSentence, compass, STYLES } from "./comfort";
import { loadJson, type Conditions, type SeabedManifest, type Status, type Style, type Zone } from "./data";
import { BayMap } from "./map";
import { store, stored } from "./storage";
import { ago, buildDays, fmtDay, fmtHour, fmtTime, isDaylight, localParts, type Day } from "./time";

const REFRESH_MS = 10 * 60_000;
const STALE_MS = 2 * 3_600_000;
const WIDE = window.matchMedia("(min-width: 860px)");

const $ = <T extends HTMLElement>(id: string): T => document.getElementById(id) as T;
const esc = (text: string): string =>
  text.replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]!);

interface Model {
  conditions: Conditions;
  status: Status | null;
  times: number[];
  days: Day[];
  nowIndex: number;
}

const state = {
  zoneId: stored("zone") ?? "entrance",
  style: (stored("style") ?? "boat") as Style,
  dayKey: "",
  /** The hour the readout shows when nothing is hovered. */
  pinned: 0,
  hover: null as number | null,
};

let model: Model | null = null;
let charts: ChartSet | null = null;

const panel = $("panel");
const bayMap = new BayMap($("map"), (id) => selectZone(id), renderSeabedSources);

// ---------------------------------------------------------------- helpers

const shortName = (name: string): string => name.split(/:| and /)[0].trim();
const zone = (): Zone => model!.conditions.zones.find((z) => z.id === state.zoneId) ?? model!.conditions.zones[0];
const day = (): Day => model!.days.find((d) => d.key === state.dayKey) ?? model!.days[0];
const num = (value: number | null | undefined, digits: number, unit: string): string =>
  value == null ? "–" : `${value.toFixed(digits)} ${unit}`;

function applyPadding(): void {
  const bar = 64;
  if (WIDE.matches) {
    bayMap.setPadding({ top: bar, right: panel.offsetWidth + 24, bottom: 24, left: 24 });
  } else {
    bayMap.setPadding({ top: bar, right: 16, bottom: panel.offsetHeight + 8, left: 16 });
  }
  document.documentElement.style.setProperty("--sheet-h", WIDE.matches ? "0px" : `${panel.offsetHeight}px`);
}

/** The best run of daylight hours still to come on a day, as a short phrase. */
function bestWindow(d: Day, values: number[]): string {
  const m = model!;
  const ahead = d.idx.filter((i) => i >= m.nowIndex);
  if (!ahead.some((i) => isDaylight(m.times[i], m.days))) return "Daylight over";
  for (const target of [3, 2]) {
    let best: [number, number] | null = null;
    let run: [number, number] | null = null;
    for (const i of ahead) {
      if (values[i] >= target && isDaylight(m.times[i], m.days)) {
        run = run ? [run[0], i] : [i, i];
        if (!best || run[1] - run[0] > best[1] - best[0]) best = run;
      } else {
        run = null;
      }
    }
    if (best) {
      const label = target === 3 ? "Good" : "Fair";
      const from = fmtHour(m.times[best[0]]);
      const to = fmtHour(m.times[best[1]] + 3_600_000);
      return `${label} ${from} to ${to}`;
    }
  }
  return ahead.some((i) => values[i] > 0) ? "Poor in daylight" : "No forecast";
}

// ---------------------------------------------------------------- rendering

function renderTabs(): void {
  const m = model!;
  $("zone-tabs").innerHTML = m.conditions.zones
    .map(
      (z) =>
        `<button type="button" data-zone="${esc(z.id)}" aria-pressed="${z.id === zone().id}" title="${esc(z.name)}">${esc(shortName(z.name))}</button>`,
    )
    .join("");
  $("style-tabs").innerHTML = STYLES.map(
    (s) => `<button type="button" data-style="${s.id}" aria-pressed="${s.id === state.style}">${s.label}</button>`,
  ).join("");
}

function renderReadout(): void {
  const m = model!;
  const z = zone();
  const i = state.hover ?? state.pinned;
  const value = z.comfort[state.style][i] ?? 0;
  const cls = comfortClass(value);
  const when = i === m.nowIndex ? `Now · ${fmtDay(m.times[i])}, ${fmtHour(m.times[i])}` : `${fmtDay(m.times[i])}, ${fmtHour(m.times[i])}`;
  const rate = m.conditions.tide.rate[i];
  const trend = rate == null ? "" : rate > 0.05 ? "rising" : rate < -0.05 ? "falling" : "slack";
  const waveDetail = [
    z.wave_period_s[i] == null ? "" : `${z.wave_period_s[i]!.toFixed(0)} s`,
    z.wave_dir[i] == null ? "" : `from ${compass(z.wave_dir[i])}`,
  ]
    .filter(Boolean)
    .join(" ");
  const stats: [string, string, string][] = [
    ["Wind", num(z.wind_kn[i], 0, "kn"), z.wind_dir[i] == null ? "" : `from ${compass(z.wind_dir[i])}`],
    ["Gusts", num(z.gust_kn[i], 0, "kn"), ""],
    ["Waves", num(z.wave_m[i], 1, "m"), waveDetail],
    ["Rain", num(z.rain_mm[i], 1, "mm"), ""],
    ["Tide", num(m.conditions.tide.height[i], 1, "m"), trend],
    ["Sea", num(z.sst_c[i], 1, "°C"), ""],
  ];
  $("readout").innerHTML = `
    <p class="readout-place">${esc(z.name)}</p>
    <p class="readout-time">${esc(when)}</p>
    <p class="rating" data-rating="${cls.css}">
      <span class="rating-symbol" aria-hidden="true">${cls.symbol}</span>
      <span>${esc(comfortSentence(value, z.limit[state.style][i] ?? "ok", state.style))}</span>
    </p>
    <dl class="stats">
      ${stats.map(([k, v, d]) => `<div><dt>${k}</dt><dd>${esc(v)}${d ? `<small>${esc(d)}</small>` : ""}</dd></div>`).join("")}
    </dl>`;
}

function renderWeek(): void {
  const m = model!;
  const values = zone().comfort[state.style];
  const ticks = `<div class="week-row week-axis" aria-hidden="true"><span></span><div class="week-cells">${[0, 6, 12, 18]
    .map((h) => `<span style="grid-column:${h + 1} / span 6">${h === 0 ? "12 am" : h === 12 ? "12 pm" : `${h % 12} ${h < 12 ? "am" : "pm"}`}</span>`)
    .join("")}</div></div>`;
  const rows = m.days
    .map((d) => {
      const cells = d.idx
        .map((i) => {
          const cls = comfortClass(values[i]);
          const night = isDaylight(m.times[i], m.days) ? "" : " night";
          const past = i < m.nowIndex ? " past" : "";
          const pinned = i === state.pinned ? " pinned" : "";
          const column = localParts(m.times[i]).hour + 1;
          const title = `${d.label} ${fmtHour(m.times[i])}: ${cls.label}`;
          return `<i class="cell ${cls.css}${night}${past}${pinned}" data-i="${i}" style="grid-column:${column}" title="${esc(title)}"></i>`;
        })
        .join("");
      return `<div class="week-row" data-day="${d.key}" aria-current="${d.key === state.dayKey}">
          <button type="button" class="week-label" data-day="${d.key}">
            <strong>${esc(d.label)}</strong><small>${esc(bestWindow(d, values))}</small>
          </button>
          <div class="week-cells">${cells}</div>
        </div>`;
    })
    .join("");
  $("week").innerHTML = ticks + rows;
}

function renderDay(): void {
  const m = model!;
  const d = day();
  $("day-title").textContent = d.label === "Today" ? `Today, ${fmtDay(d.start)}` : d.label;
  const position = m.days.indexOf(d);
  $<HTMLButtonElement>("day-prev").disabled = position <= 0;
  $<HTMLButtonElement>("day-next").disabled = position >= m.days.length - 1;

  charts?.destroy();
  charts = drawCharts($("charts"), m.conditions, zone(), d, m.times, Date.now(), (i) => {
    if (state.hover === i) return;
    state.hover = i;
    renderReadout();
    renderMarkers();
  });

  const z = zone();
  const rows = d.idx
    .map((i) => {
      const cls = comfortClass(z.comfort[state.style][i]);
      return `<tr>
        <th scope="row">${fmtHour(m.times[i])}</th>
        <td>${cls.symbol} ${cls.label}</td>
        <td>${num(z.wind_kn[i], 0, "kn")} ${compass(z.wind_dir[i])}</td>
        <td>${num(z.gust_kn[i], 0, "kn")}</td>
        <td>${num(z.wave_m[i], 1, "m")}</td>
        <td>${num(z.rain_mm[i], 1, "mm")}</td>
        <td>${num(m.conditions.tide.height[i], 1, "m")}</td>
      </tr>`;
    })
    .join("");
  $("table").innerHTML = `<table>
      <thead><tr><th scope="col">Time</th><th scope="col">Rating</th><th scope="col">Wind</th><th scope="col">Gusts</th><th scope="col">Waves</th><th scope="col">Rain</th><th scope="col">Tide</th></tr></thead>
      <tbody>${rows}</tbody>
    </table>`;
}

function renderMarkers(): void {
  const m = model!;
  const i = state.hover ?? state.pinned;
  bayMap.setZones(
    m.conditions.zones.map((z) => ({
      id: z.id,
      label: shortName(z.name),
      lat: z.lat,
      lon: z.lon,
      value: z.comfort[state.style][i] ?? 0,
    })),
    zone().id,
  );
}

function renderFreshness(): void {
  const badge = $("freshness");
  if (!model) return;
  const now = Date.now();
  const generated = Date.parse(model.conditions.generated_at);
  const troubled = (model.status?.sources ?? []).filter((s) => !s.ok || s.stale).map((s) => s.name);
  const old = now - generated > STALE_MS;
  badge.dataset.state = old ? "bad" : troubled.length ? "warn" : "ok";
  // The prefix is dropped on narrow screens, where only the essentials fit.
  const prefix = old ? "Out of date · " : troubled.length ? "Partly stale · " : "Updated ";
  badge.innerHTML = `<span class="${old || troubled.length ? "" : "freshness-prefix"}">${prefix}</span>${ago(generated, now)}`;
  badge.title =
    `Last pipeline run: ${fmtDay(generated)}, ${fmtTime(generated)}` +
    (troubled.length ? `. Using older data for ${troubled.join(", ")}.` : "");

  const list = (model.status?.sources ?? [])
    .map((s) => {
      const state = !s.ok ? "unavailable" : s.stale ? "using an older copy" : "up to date";
      const fetched = s.fetched_at ? `, fetched ${ago(Date.parse(s.fetched_at), now)}` : "";
      return `<li>${esc(s.name)}: ${state}${fetched}</li>`;
    })
    .join("");
  $("source-status").innerHTML = list ? `<h3>Data status</h3><ul>${list}</ul>` : "";
}

function renderThresholds(): void {
  const styles = model?.conditions.thresholds.styles;
  if (!styles) return;
  const row = (s: (typeof STYLES)[number]) => {
    const t = styles[s.id];
    if (!t) return "";
    const cell = (l: { wind_kn: number; gust_kn: number; wave_m: number }) =>
      `<td>wind ${l.wind_kn} kn, gusts ${l.gust_kn} kn, waves ${l.wave_m} m</td>`;
    return `<tr><th scope="row">${s.label}</th>${cell(t.good)}${cell(t.fair)}</tr>`;
  };
  $("thresholds").innerHTML = `<table>
      <thead><tr><th scope="col"></th><th scope="col">Good, up to</th><th scope="col">Fair, up to</th></tr></thead>
      <tbody>${STYLES.map(row).join("")}</tbody>
    </table>`;
}

/** The About panel's list of depth sources, with how much of the water each one covers. */
function renderSeabedSources(manifest: SeabedManifest): void {
  const sources = manifest.layers.depth_source.classes.filter((c) => (c.cells ?? 0) > 0);
  const sea = sources.reduce((sum, c) => sum + (c.cells ?? 0), 0);
  $("seabed-sources").innerHTML = sources
    .map((c) => {
      const share = (100 * (c.cells ?? 0)) / sea;
      const quality = manifest.quality[c.quality ?? 0];
      return `<li><strong>${esc(c.label)}</strong>, ${share < 1 ? "under 1" : share.toFixed(0)}% of the water.
        ${esc(quality.label)}: ${esc((quality.detail ?? "").replace(/\.$/, ""))}.</li>`;
    })
    .join("");
}

function renderAll(): void {
  renderTabs();
  renderReadout();
  renderWeek();
  renderDay();
  renderMarkers();
  renderFreshness();
  renderThresholds();
}

// ---------------------------------------------------------------- actions

function selectZone(id: string): void {
  if (!model || !model.conditions.zones.some((z) => z.id === id)) return;
  state.zoneId = id;
  store("zone", id);
  renderAll();
}

function selectDay(key: string, pin?: number): void {
  const m = model!;
  const d = m.days.find((x) => x.key === key);
  if (!d) return;
  state.dayKey = key;
  // Pin the chosen hour, or the hour nearest midday on a day picked by its label.
  state.pinned = pin ?? (d.idx.includes(m.nowIndex) ? m.nowIndex : d.idx[Math.min(d.idx.length - 1, Math.max(0, 12 - localParts(m.times[d.idx[0]]).hour))]);
  state.hover = null;
  renderReadout();
  renderWeek();
  renderDay();
  renderMarkers();
}

$("zone-tabs").addEventListener("click", (event) => {
  const id = (event.target as HTMLElement).closest<HTMLElement>("[data-zone]")?.dataset.zone;
  if (id) selectZone(id);
});

$("style-tabs").addEventListener("click", (event) => {
  const id = (event.target as HTMLElement).closest<HTMLElement>("[data-style]")?.dataset.style as Style | undefined;
  if (!id || !model) return;
  state.style = id;
  store("style", id);
  renderAll();
});

$("week").addEventListener("click", (event) => {
  const target = event.target as HTMLElement;
  const cell = target.closest<HTMLElement>("[data-i]");
  const row = target.closest<HTMLElement>("[data-day]");
  if (!row?.dataset.day) return;
  selectDay(row.dataset.day, cell ? Number(cell.dataset.i) : undefined);
});

$("day-prev").addEventListener("click", () => stepDay(-1));
$("day-next").addEventListener("click", () => stepDay(1));
function stepDay(step: number): void {
  if (!model) return;
  const next = model.days[model.days.indexOf(day()) + step];
  if (next) selectDay(next.key);
}

$("charts").addEventListener("mouseleave", () => {
  if (state.hover == null) return;
  state.hover = null;
  renderReadout();
  renderMarkers();
});

$("sheet-toggle").addEventListener("click", () => {
  const expanded = panel.classList.toggle("expanded");
  $("sheet-toggle").setAttribute("aria-expanded", String(expanded));
  window.setTimeout(() => {
    applyPadding();
    charts?.resize();
  }, 260);
});

$("about-open").addEventListener("click", () => $<HTMLDialogElement>("about").showModal());
$<HTMLDialogElement>("about").addEventListener("click", (event) => {
  if (event.target === event.currentTarget) (event.currentTarget as HTMLDialogElement).close();
});

new ResizeObserver(() => charts?.resize()).observe($("charts"));
WIDE.addEventListener("change", applyPadding);
window.addEventListener("resize", applyPadding);

// ---------------------------------------------------------------- data

async function refresh(): Promise<void> {
  try {
    const [conditions, status] = await Promise.all([
      loadJson<Conditions>("/data/conditions.json"),
      loadJson<Status>("/data/status.json").catch(() => null),
    ]);
    const times = conditions.hours.map((h) => Date.parse(h));
    const now = Date.now();
    let nowIndex = 0;
    times.forEach((t, i) => {
      if (t <= now) nowIndex = i;
    });
    const first = model === null;
    model = { conditions, status, times, days: buildDays(conditions, times, now), nowIndex };
    if (first || !model.days.some((d) => d.key === state.dayKey)) {
      state.dayKey = localParts(times[nowIndex]).date;
      state.pinned = nowIndex;
    }
    state.pinned = Math.min(state.pinned, times.length - 1);
    panel.classList.remove("failed");
    renderAll();
  } catch (error) {
    console.error(error);
    if (!model) {
      panel.classList.add("failed");
      $("readout").innerHTML = `<p class="rating" data-rating="none"><span class="rating-symbol" aria-hidden="true">?</span>
        <span>Conditions are not available right now. The map still works; please try again shortly.</span></p>`;
      const badge = $("freshness");
      badge.dataset.state = "bad";
      badge.textContent = "No data";
    }
  }
}

applyPadding();
void refresh();
window.setInterval(() => void refresh(), REFRESH_MS);
window.setInterval(renderFreshness, 60_000);
