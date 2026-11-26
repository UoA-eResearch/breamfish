// The map: a self-hosted OpenStreetMap basemap of the bay, the seabed layers
// (depth, how sure the depth is, bottom type, contours), the no-take marine
// reserve, boat ramps, and one tappable marker per forecast zone.

import { layers, namedFlavor } from "@protomaps/basemaps";
import * as maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
// MapLibre 6 runs its tile parsing in a separate worker module. Left alone it
// looks for that file beside the main bundle, where a bundled build has none;
// `?worker&url` makes Vite build the worker and hand back its real address.
import workerUrl from "maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url";
import { Protocol } from "pmtiles";
import { comfortClass } from "./comfort";
import type { SeabedManifest } from "./data";
import { BOTTOM_COLOUR, DEPTH_BANDS, Seabed, type Overlay, type SeabedPoint } from "./seabed";
import { store, stored } from "./storage";

/** The study area: Bream Head to Bream Tail, out to the Hen and Chickens. */
const BAY: [[number, number], [number, number]] = [
  [174.4, -36.1],
  [174.8, -35.8],
];

type OverlayChoice = Overlay | "none";
const OVERLAYS: { id: OverlayChoice; label: string }[] = [
  { id: "depth", label: "Depth" },
  { id: "quality", label: "How sure the depth is" },
  { id: "bottom", label: "Bottom type" },
  { id: "none", label: "None" },
];

/** A small element with text, built without innerHTML so nothing needs escaping. */
function el<K extends keyof HTMLElementTagNameMap>(tag: K, text = "", className = ""): HTMLElementTagNameMap[K] {
  const node = document.createElement(tag);
  if (text) node.textContent = text;
  if (className) node.className = className;
  return node;
}

/** What a tap on the water says. Everything in it comes from the seabed grids as built. */
function describeSpot(point: SeabedPoint): HTMLElement {
  const box = el("div", "", "spot");
  const measured = point.quality.key === "measured";
  const metres = measured ? Math.abs(point.depth).toFixed(1) : Math.abs(point.depth).toFixed(0);
  const head = el("p", "", "spot-depth");
  if (point.depth < 0) {
    head.append(el("strong", "Dries at low tide"), `, about ${metres} m above the lowest tides`);
  } else {
    head.append(measured ? "" : "About ", el("strong", `${metres} m`), " deep at the lowest tides");
  }
  box.append(head);

  const rows = el("dl");
  const row = (term: string, value: string, detail = "") => {
    const dd = el("dd", value);
    if (detail) dd.append(el("small", detail));
    rows.append(el("dt", term), dd);
  };
  row("Depth from", point.source.label, `${point.quality.label}. ${point.quality.detail ?? ""}`.trim());
  row("Bottom", point.bottom.label, point.bottom.key === "unknown" ? "" : `From: ${point.bottomSource.label}`);
  if (point.slope == null || point.roughness == null) {
    row("Slope, roughness", "Not measured here", "Only where LiDAR or multibeam covers the spot.");
  } else {
    row("Slope", `${point.slope.toFixed(1)}°`);
    row("Roughness", `${point.roughness.toFixed(2)} m`, "How much the depth varies across this 100 m cell.");
  }
  box.append(rows, el("p", "Add the tide height for the depth now. Not for navigation.", "spot-note"));
  return box;
}

export interface ZoneMarker {
  id: string;
  label: string;
  lat: number;
  lon: number;
  value: number;
}

export class BayMap {
  readonly map: maplibregl.Map;
  private markers = new Map<string, { marker: maplibregl.Marker; element: HTMLButtonElement }>();
  private fitted = false;
  private padding = { top: 0, right: 0, bottom: 0, left: 0 };
  private seabed: Seabed | null = null;
  private overlay = (stored("overlay") ?? "depth") as OverlayChoice;
  private contours = stored("contours") !== "off";

  constructor(
    container: HTMLElement,
    private onZone: (id: string) => void,
    private onSeabed: (manifest: SeabedManifest) => void,
  ) {
    maplibregl.setWorkerUrl(workerUrl);
    maplibregl.addProtocol("pmtiles", new Protocol().tile);
    const flavor = window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
    const origin = window.location.origin;

    this.map = new maplibregl.Map({
      container,
      attributionControl: false,
      center: [174.6, -35.95],
      zoom: 9.6,
      minZoom: 8,
      maxZoom: 15.5,
      maxBounds: [
        [173.9, -36.5],
        [175.3, -35.4],
      ],
      style: {
        version: 8,
        glyphs: `${origin}/fonts/{fontstack}/{range}.pbf`,
        sprite: `${origin}/sprites/${flavor}`,
        sources: {
          basemap: {
            type: "vector",
            url: `pmtiles://${origin}/tiles/breambay.pmtiles`,
            attribution:
              '<a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">© OpenStreetMap</a> · ' +
              '<a href="https://protomaps.com" target="_blank" rel="noopener">Protomaps</a> · ' +
              '<a href="https://www.doc.govt.nz" target="_blank" rel="noopener">DOC</a>',
          },
        },
        layers: layers("basemap", namedFlavor(flavor), { lang: "en" }),
      },
    });

    this.map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-left");
    this.map.addControl(new maplibregl.AttributionControl({ compact: true }), "bottom-left");
    this.map.dragRotate.disable();
    this.map.touchZoomRotate.disableRotation();
    this.map.on("load", () => {
      this.addOverlays();
      void this.addSeabed();
    });
  }

  /** A CSS custom property from style.css as [r, g, b, a] for painting. */
  private colour = (name: string): [number, number, number, number] => {
    const hex = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
    const value = parseInt(hex.slice(1), 16);
    return [(value >> 16) & 255, (value >> 8) & 255, value & 255, 255];
  };

  private async addSeabed(): Promise<void> {
    try {
      this.seabed = await Seabed.load();
    } catch (error) {
      // The conditions and the rest of the map still work without the seabed layers.
      console.error(error);
      return;
    }
    this.onSeabed(this.seabed.manifest);
    const map = this.map;
    const css = getComputedStyle(document.documentElement);
    const ink = css.getPropertyValue("--contour").trim() || "#0d366b";
    const surface = css.getPropertyValue("--surface").trim() || "#fcfcfb";
    map.addSource("contours", { type: "geojson", data: `/seabed/${this.seabed.manifest.contours.file}` });
    map.addLayer(
      {
        id: "contours",
        type: "line",
        source: "contours",
        paint: {
          "line-color": ink,
          "line-opacity": 0.55,
          "line-width": ["interpolate", ["linear"], ["zoom"], 9, 0.5, 14, 1.2],
        },
      },
      "reserves-fill",
    );
    map.addLayer(
      {
        id: "contours-label",
        type: "symbol",
        source: "contours",
        minzoom: 10.5,
        layout: {
          "symbol-placement": "line",
          "symbol-spacing": 320,
          "text-field": ["concat", ["to-string", ["get", "depth"]], " m"],
          "text-font": ["Noto Sans Regular"],
          "text-size": 10,
        },
        paint: { "text-color": ink, "text-halo-color": surface, "text-halo-width": 1.2 },
      },
      "reserves-fill",
    );
    // Under the zoom buttons on a wide screen; on a phone the top right is the free corner.
    const wide = window.matchMedia("(min-width: 860px)").matches;
    map.addControl(this.layerControl(this.seabed), wide ? "top-left" : "top-right");
    this.showSeabed();
  }

  /** Show the chosen seabed layer, painting it the first time it is asked for. */
  private showSeabed(): void {
    const map = this.map;
    const seabed = this.seabed;
    if (!seabed) return;
    for (const { id } of OVERLAYS) {
      if (id !== "none" && id !== this.overlay && map.getLayer(`seabed-${id}`)) {
        map.setLayoutProperty(`seabed-${id}`, "visibility", "none");
      }
    }
    if (this.overlay !== "none") {
      const id = `seabed-${this.overlay}`;
      if (!map.getLayer(id)) {
        const [west, south, east, north] = seabed.manifest.bounds;
        map.addSource(id, {
          type: "canvas",
          canvas: seabed.paint(this.overlay, this.colour),
          animate: false,
          coordinates: [
            [west, north],
            [east, north],
            [east, south],
            [west, south],
          ],
        });
        map.addLayer(
          {
            id,
            type: "raster",
            source: id,
            paint: {
              "raster-opacity": 0.8,
              "raster-fade-duration": 0,
              // Depth is a surface, so blend between pixels; classes keep hard edges.
              "raster-resampling": this.overlay === "depth" ? "linear" : "nearest",
            },
          },
          "contours",
        );
      }
      map.setLayoutProperty(id, "visibility", "visible");
    }
    for (const id of ["contours", "contours-label"]) {
      map.setLayoutProperty(id, "visibility", this.contours ? "visible" : "none");
    }
  }

  /** The layer picker and its key, as a map control under the zoom buttons. */
  private layerControl(seabed: Seabed): maplibregl.IControl {
    const { manifest } = seabed;
    const box = el("details", "", "maplibregl-ctrl layers");
    // Open, with its key showing, only where there is room beside the zone markers.
    box.open = window.matchMedia("(min-width: 1200px)").matches;
    const summary = el("summary");
    const key = el("ul", "", "layers-key");
    const note = el("p", "", "layers-note");

    const swatch = (name: string, label: string) => {
      const item = el("li", label);
      const chip = el("i");
      chip.style.background = `var(${name})`;
      item.prepend(chip);
      return item;
    };
    const render = () => {
      const chosen = OVERLAYS.find((o) => o.id === this.overlay)!;
      summary.textContent = this.overlay === "none" ? "Seabed" : `Seabed: ${chosen.label.toLowerCase()}`;
      key.replaceChildren();
      if (this.overlay === "depth") {
        key.append(...DEPTH_BANDS.map((band, i) => swatch(`--depth-${i}`, band.label)));
        note.textContent = "Depth at the lowest tides. Tap the water for details.";
      } else if (this.overlay === "quality") {
        const used = manifest.quality.filter((q) => q.cells > 0);
        key.append(...used.map((q) => swatch(`--quality-${q.key}`, `${q.label}: ${q.detail ?? ""}`)));
        note.textContent = "Where the depth comes from decides how far to trust it.";
      } else if (this.overlay === "bottom") {
        const seen = new Set<string>();
        for (const cls of manifest.layers.bottom.classes) {
          const name = BOTTOM_COLOUR[cls.key];
          if (!name || !cls.cells) continue;
          // Shell and gravel share a colour, so they share a line of the key.
          if (seen.has(name)) continue;
          seen.add(name);
          key.append(swatch(name, name === "--bottom-coarse" ? "Shell, gravel or coarse sediment" : cls.label));
        }
        note.textContent = "From charts and a coarse habitat map. Uncoloured water is not mapped.";
      } else {
        note.textContent = "Tap the water for depth and bottom type.";
      }
    };

    const choices = el("fieldset");
    choices.append(el("legend", "Colour the water by", "visually-hidden"));
    for (const { id, label } of OVERLAYS) {
      const input = el("input");
      input.type = "radio";
      input.name = "seabed-overlay";
      input.value = id;
      input.checked = id === this.overlay;
      input.addEventListener("change", () => {
        this.overlay = id;
        store("overlay", id);
        this.showSeabed();
        render();
      });
      const row = el("label");
      row.append(input, label);
      choices.append(row);
    }
    const lines = el("input");
    lines.type = "checkbox";
    lines.checked = this.contours;
    lines.addEventListener("change", () => {
      this.contours = lines.checked;
      store("contours", lines.checked ? "on" : "off");
      this.showSeabed();
    });
    const linesRow = el("label", "", "layers-contours");
    linesRow.append(lines, "Depth contours");

    box.append(summary, choices, linesRow, key, note);
    render();
    return { onAdd: () => box, onRemove: () => box.remove() };
  }

  private addOverlays(): void {
    const css = getComputedStyle(document.documentElement);
    const poor = css.getPropertyValue("--poor").trim() || "#d03b3b";
    const surface = css.getPropertyValue("--surface").trim() || "#fcfcfb";
    const ink = css.getPropertyValue("--ink").trim() || "#0b0b0b";
    const map = this.map;

    map.addSource("reserves", { type: "geojson", data: "/layers/reserves.geojson" });
    map.addLayer({
      id: "reserves-fill",
      type: "fill",
      source: "reserves",
      paint: { "fill-color": poor, "fill-opacity": 0.28 },
    });
    map.addLayer({
      id: "reserves-line",
      type: "line",
      source: "reserves",
      paint: { "line-color": poor, "line-width": 2 },
    });
    map.addLayer({
      id: "reserves-label",
      type: "symbol",
      source: "reserves",
      minzoom: 10.5,
      layout: {
        "text-field": "No-take reserve",
        "text-font": ["Noto Sans Medium"],
        "text-size": 11,
        "text-offset": [0, 1.2],
      },
      paint: { "text-color": ink, "text-halo-color": surface, "text-halo-width": 1.5 },
    });

    map.addSource("ramps", { type: "geojson", data: "/layers/ramps.geojson" });
    map.addLayer({
      id: "ramps",
      type: "circle",
      source: "ramps",
      minzoom: 9.5,
      paint: {
        "circle-radius": ["interpolate", ["linear"], ["zoom"], 9.5, 2.5, 13, 5],
        "circle-color": surface,
        "circle-stroke-color": ink,
        "circle-stroke-width": 1.5,
      },
    });

    // One tap, one popup: a boat ramp if that is what was tapped, otherwise what is
    // known about the seabed there, with the reserve rule first inside the reserve.
    map.on("click", (event) => {
      const hits = map.queryRenderedFeatures(event.point, { layers: ["ramps", "reserves-fill"] });
      const named = (layer: string) => hits.find((f) => f.layer.id === layer)?.properties?.name as string | undefined;
      const popup = new maplibregl.Popup({ closeButton: false, maxWidth: "280px" }).setLngLat(event.lngLat);
      const ramp = named("ramps");
      if (ramp !== undefined) {
        popup.setText(`${ramp} (from OpenStreetMap; check access before you tow)`).addTo(map);
        return;
      }
      const reserve = named("reserves-fill");
      const spot = this.seabed?.inspect(event.lngLat.lng, event.lngLat.lat);
      if (reserve === undefined && !spot) return;
      const content = el("div");
      if (reserve !== undefined) {
        content.append(el("p", `${reserve}: no-take. All fishing is prohibited here.`, "spot-rule"));
      }
      if (spot) content.append(describeSpot(spot));
      this.reveal(popup.setDOMContent(content).addTo(map));
    });
    map.on("mouseenter", "ramps", () => (map.getCanvas().style.cursor = "pointer"));
    map.on("mouseleave", "ramps", () => (map.getCanvas().style.cursor = ""));
  }

  /** Slide the map just far enough that a popup is not hidden under the panel or the top bar. */
  private reveal(popup: maplibregl.Popup): void {
    const box = popup.getElement()?.getBoundingClientRect();
    if (!box) return;
    const view = this.map.getContainer().getBoundingClientRect();
    const { top, right, bottom, left } = this.padding;
    const dx = Math.max(0, box.right - (view.right - right)) || Math.min(0, box.left - (view.left + left));
    const dy = Math.max(0, box.bottom - (view.bottom - bottom)) || Math.min(0, box.top - (view.top + top));
    if (dx || dy) this.map.panBy([dx, dy], { duration: 250 });
  }

  /** Keep the bay centred in the part of the map the panel does not cover. */
  setPadding(padding: { top: number; right: number; bottom: number; left: number }): void {
    this.padding = padding;
    if (this.fitted) {
      this.map.easeTo({ padding, duration: 250 });
      return;
    }
    this.fitted = true;
    this.map.fitBounds(BAY, { padding, animate: false });
  }

  setZones(zones: ZoneMarker[], selectedId: string): void {
    for (const zone of zones) {
      let entry = this.markers.get(zone.id);
      if (!entry) {
        const element = document.createElement("button");
        element.type = "button";
        element.className = "zone-marker";
        element.addEventListener("click", (event) => {
          event.stopPropagation();
          this.onZone(zone.id);
        });
        const marker = new maplibregl.Marker({ element, anchor: "center" })
          .setLngLat([zone.lon, zone.lat])
          .addTo(this.map);
        entry = { marker, element };
        this.markers.set(zone.id, entry);
      }
      const cls = comfortClass(zone.value);
      entry.element.dataset.rating = cls.css;
      entry.element.setAttribute("aria-pressed", String(zone.id === selectedId));
      entry.element.setAttribute("aria-label", `${zone.label}: ${cls.label}. Show conditions.`);
      entry.element.innerHTML = `<span class="zone-symbol" aria-hidden="true">${cls.symbol}</span><span class="zone-label">${zone.label}</span>`;
    }
  }
}
