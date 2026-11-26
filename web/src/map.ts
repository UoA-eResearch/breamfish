// The map: a self-hosted OpenStreetMap basemap of the bay, the no-take marine
// reserve, boat ramps, and one tappable marker per forecast zone.

import { layers, namedFlavor } from "@protomaps/basemaps";
import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { Protocol } from "pmtiles";
import { comfortClass } from "./comfort";

/** The study area: Bream Head to Bream Tail, out to the Hen and Chickens. */
const BAY: [[number, number], [number, number]] = [
  [174.4, -36.1],
  [174.8, -35.8],
];

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

  constructor(container: HTMLElement, private onZone: (id: string) => void) {
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
    this.map.on("load", () => this.addOverlays());
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

    const describe = (layer: string, text: (name: string) => string) => {
      map.on("click", layer, (event) => {
        const name = String(event.features?.[0]?.properties?.name ?? "");
        new maplibregl.Popup({ closeButton: false, maxWidth: "240px" })
          .setLngLat(event.lngLat)
          .setText(text(name))
          .addTo(map);
      });
      map.on("mouseenter", layer, () => (map.getCanvas().style.cursor = "pointer"));
      map.on("mouseleave", layer, () => (map.getCanvas().style.cursor = ""));
    };
    describe("ramps", (name) => `${name} (from OpenStreetMap; check access before you tow)`);
    describe("reserves-fill", (name) => `${name}: no-take. All fishing is prohibited here.`);
  }

  /** Keep the bay centred in the part of the map the panel does not cover. */
  setPadding(padding: { top: number; right: number; bottom: number; left: number }): void {
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
