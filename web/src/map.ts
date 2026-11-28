// The map: a self-hosted OpenStreetMap basemap of the bay, the snapper habitat
// index, the seabed layers (depth, how sure the depth is, bottom type, rough
// ground, contours), boats seen from space, shaded relief where the depth was measured, the forecast
// wind drawn moving, the no-take marine reserve, boat ramps, and one tappable
// marker per forecast zone.

import { layers, namedFlavor } from "@protomaps/basemaps";
import * as maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
// MapLibre 6 runs its tile parsing in a separate worker module. Left alone it
// looks for that file beside the main bundle, where a bundled build has none;
// `?worker&url` makes Vite build the worker and hand back its real address.
import workerUrl from "maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url";
import { Protocol } from "pmtiles";
import { comfortClass } from "./comfort";
import { loadJson, type BoatGroup, type BoatsManifest, type ReliefArchive, type SeabedManifest, type Season, type Style, type VectorField } from "./data";
import { FLOW_BANDS, FlowLayer } from "./flow";
import { Habitat, type HabitatPoint } from "./habitat";
import type { Rgba } from "./paint";
import { BOTTOM_COLOUR, DEPTH_BANDS, Seabed, type Overlay, type SeabedPoint } from "./seabed";
import { store, stored } from "./storage";

/** The study area: Bream Head to Bream Tail, out to the Hen and Chickens. */
const BAY: [[number, number], [number, number]] = [
  [174.4, -36.1],
  [174.8, -35.8],
];

/** Seabed tiles are painted in the page, under this made-up address: seabed://layer/z/x/y. */
const TILE_SCHEME = "seabed";
/** The side of a map tile in CSS pixels. Tiles are painted at the screen's own density. */
const TILE_SIZE = 256;
/** Zoomed in past this, a screen pixel is finer than the 100 m grid can fill: fetch the 20 m one. */
const DRAWING_FROM_ZOOM = 10.5;
/** How strongly the shaded relief is laid over the water: enough to read, not enough to hide a colour. */
const RELIEF_OPACITY = 0.6;

/**
 * The basemap's layers, with the sea moved underneath the land. As Protomaps
 * orders them, all water is drawn over the land; here the sea is drawn first
 * and only lakes and rivers stay on top. The seabed layers go in between, just
 * under the land (before LAND), so the basemap's own coastline trims them: no
 * blocky edge, and nothing painted over a beach.
 */
const LAND = "earth";
function basemapLayers(flavor: "light" | "dark"): maplibregl.LayerSpecification[] {
  const all = layers("basemap", namedFlavor(flavor), { lang: "en" }) as maplibregl.LayerSpecification[];
  const water = all.find((layer) => layer.id === "water");
  const land = all.findIndex((layer) => layer.id === LAND);
  if (!water || water.type !== "fill" || land < 0) return all; // a basemap arranged some other way
  const sea = { ...water, id: "sea", filter: ["all", water.filter, ["==", "kind", "ocean"]] };
  const inland = { ...water, filter: ["all", water.filter, ["!=", "kind", "ocean"]] };
  const rest = all.map((layer) => (layer === water ? inland : layer)) as maplibregl.LayerSpecification[];
  rest.splice(land, 0, sea as maplibregl.LayerSpecification);
  return rest;
}

type OverlayChoice = Overlay | "snapper" | "boats" | "none";
const OVERLAYS: { id: OverlayChoice; label: string }[] = [
  { id: "snapper", label: "Snapper habitat" },
  { id: "boats", label: "Boats seen from space" },
  { id: "depth", label: "Depth" },
  { id: "quality", label: "How sure the depth is" },
  { id: "bottom", label: "Bottom type" },
  { id: "rough", label: "Rough ground" },
  { id: "none", label: "None" },
];

const SEASONS: { id: Season; label: string }[] = [
  { id: "summer", label: "Summer" },
  { id: "autumn", label: "Autumn" },
  { id: "winter", label: "Winter" },
  { id: "spring", label: "Spring" },
];
/** Where the method, the evidence and the checks are set out. */
const METHODS = "/methods.html";
const BOAT_GROUPS: { id: BoatGroup; label: string }[] = [
  { id: "all", label: "All" },
  { id: "weekend", label: "Weekends" },
  { id: "weekday", label: "Weekdays" },
];
/** The boat layer's fill, as laid over the water. */
const BOATS_OPACITY = 0.8;

/** A small element with text, built without innerHTML so nothing needs escaping. */
function el<K extends keyof HTMLElementTagNameMap>(tag: K, text = "", className = ""): HTMLElementTagNameMap[K] {
  const node = document.createElement(tag);
  if (text) node.textContent = text;
  if (className) node.className = className;
  return node;
}

/** What a tap on the water says. Everything in it comes from the seabed grids as built. */
function describeSpot(point: SeabedPoint, reading = ""): HTMLElement {
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
  if (point.roughGround != null) {
    row("Rough ground", `${point.roughGround.toFixed(2)} m`, `Over 10 m, in the roughest patches of this cell. ${reading}`.trim());
  }
  box.append(rows, el("p", "Add the tide height for the depth now. Not for navigation.", "spot-note"));
  return box;
}

/** What the habitat index says about a tapped spot, and what each factor contributed. */
function describeHabitat(point: HabitatPoint, habitat: Habitat, style: Style): HTMLElement {
  const box = el("div", "", "spot spot-habitat");
  const head = el("p", "", "spot-depth");
  const name = habitat.manifest.species.name;
  if (point.class === 0) {
    head.append(el("strong", `${name} habitat: not rated here`));
    box.append(head, el("p", "Inside a no-take reserve, or a 100 m square that is mostly land.", "spot-note"));
    return box;
  }
  const chip = el("i", "", "habitat-chip");
  chip.style.background = `var(--habitat-${point.class})`;
  head.append(chip, `${name} habitat, ${point.season}: `, el("strong", point.label.toLowerCase()));
  box.append(head);

  const rows = el("dl");
  for (const factor of point.factors) {
    const dd = el("dd");
    if (factor.suitability == null) {
      dd.append(el("small", "Not mapped here, so left out"));
    } else {
      const bar = el("span", "", "habitat-bar");
      bar.setAttribute("role", "img");
      bar.setAttribute("aria-label", `suits ${Math.round(factor.suitability * 10)} out of 10`);
      bar.append(el("span"));
      (bar.firstElementChild as HTMLElement).style.width = `${Math.round(factor.suitability * 100)}%`;
      dd.append(bar);
    }
    rows.append(el("dt", factor.label), dd);
  }
  box.append(rows);

  const limit = habitat.manifest.reach.within_m_of_mainland_shore[style];
  const note = el("p", "", "spot-note");
  if (limit != null && !point.reach[style]) {
    note.append(
      style === "shore"
        ? "Beyond a cast from the mainland shore. "
        : `More than ${limit / 1000} km from the mainland shore, taken here as beyond kayak reach. `,
    );
  }
  const link = el("a", "How this is worked out");
  link.href = METHODS;
  note.append("Ranked against the rest of the bay this season; not a catch forecast. ", link, ".");
  box.append(note);
  return box;
}

/** What the boat count says about a tapped 1 km square. Every figure is as published. */
function describeBoats(props: Record<string, unknown>, manifest: BoatsManifest): HTMLElement {
  const box = el("div", "", "spot spot-boats");
  const count = (group: BoatGroup) => {
    const boats = Number(props[`${group}_boats`]);
    const seen = Number(props[`${group}_seen`]);
    return `${boats} ${boats === 1 ? "boat" : "boats"} in ${seen} clear ${seen === 1 ? "pass" : "passes"}`;
  };
  const head = el("p", "", "spot-depth");
  head.append(el("strong", count("all")), ` over this ${manifest.square_m / 1000} km square`);
  const rows = el("dl");
  for (const group of manifest.groups) {
    if (group.id === "all") continue;
    rows.append(el("dt", group.label), el("dd", count(group.id)));
  }
  box.append(head, rows);
  if (props.fixed) {
    box.append(el("p", "Something here is seen on most passes (moorings, a rock or a buoy): boats right beside it are not counted.", "spot-note"));
  }
  const link = el("a", "How this is counted");
  link.href = `${METHODS}#boats`;
  const note = el("p", "", "spot-note");
  note.append(`Sentinel-2 pictures at about 11:25, ${manifest.first_pass.slice(0, 4)} to ${manifest.last_pass.slice(0, 4)}. Where boats were, not where fish are. `, link, ".");
  box.append(note);
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
  private habitat: Habitat | null = null;
  /** Boats seen from space: the manifest, and which passes are shown. */
  private boats: BoatsManifest | null = null;
  private boatGroup = (stored("boatGroup") ?? "all") as BoatGroup;
  private overlay = (stored("overlay") ?? "snapper") as OverlayChoice;
  /** The season the habitat layer shows: the present one until another is picked. */
  private season: Season = "summer";
  private style: Style = "boat";
  private contours = stored("contours") !== "off";
  /** The forecast wind, drawn moving over everything else. */
  private flow: FlowLayer;
  private wind = stored("wind") !== "off";
  /** Shaded relief over the water, where the depth was measured. */
  private relief = stored("relief") !== "off";
  private reliefLayers: string[] = [];
  /** Which picture each painted source is showing now, by source id. */
  private showing = new Map<string, string>();
  private renderControl: () => void = () => {};
  /** Goes up when the tiles would come out differently, so the map asks for them again. */
  private painted = 0;
  private colours = new Map<string, Rgba>();

  constructor(
    container: HTMLElement,
    private onZone: (id: string) => void,
    private onSeabed: (manifest: SeabedManifest) => void,
  ) {
    maplibregl.setWorkerUrl(workerUrl);
    maplibregl.addProtocol("pmtiles", new Protocol().tile);
    maplibregl.addProtocol(TILE_SCHEME, (request) => this.paintTile(request.url));
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
        layers: basemapLayers(flavor),
      },
    });

    this.map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-left");
    this.map.addControl(new maplibregl.AttributionControl({ compact: true }), "bottom-left");
    this.map.dragRotate.disable();
    this.map.touchZoomRotate.disableRotation();
    this.flow = new FlowLayer(this.map);
    this.flow.setShown(this.wind);
    this.map.on("load", () => {
      this.addOverlays();
      void this.addSeabed();
    });
  }

  /** Where the seabed layers go in the stack: under the basemap's land if it has one. */
  private get underLand(): string {
    return this.map.getLayer(LAND) ? LAND : "reserves-fill";
  }

  /** A CSS custom property from style.css as [r, g, b, a] for painting. */
  private colour = (name: string): Rgba => {
    let rgba = this.colours.get(name);
    if (!rgba) {
      const hex = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
      const value = parseInt(hex.slice(1), 16);
      rgba = [(value >> 16) & 255, (value >> 8) & 255, value & 255, 255];
      this.colours.set(name, rgba);
    }
    return rgba;
  };

  /** Answer the map's request for one seabed tile with a picture of it. */
  private async paintTile(url: string): Promise<{ data: ImageBitmap }> {
    const match = /^[a-z]+:\/\/([a-z.]+)\/(\d+)\/(\d+)\/(\d+)/.exec(url);
    if (!match || !this.seabed) throw new Error(`no seabed tile at ${url}`);
    const [layer, which] = match[1].split(".");
    const [z, x, y] = match.slice(2).map(Number);
    // Two picture pixels to a CSS pixel on a dense screen, so nothing is stretched.
    const px = TILE_SIZE * (window.devicePixelRatio > 1.25 ? 2 : 1);
    let image: ImageData;
    if (layer === "snapper" || layer === "veil") {
      if (!this.habitat) throw new Error(`no habitat tile at ${url}`);
      image =
        layer === "snapper"
          ? this.habitat.paintIndex(which as Season, z, x, y, px, this.colour)
          : this.habitat.paintVeil(which as Style, z, x, y, px, this.colour);
    } else {
      image = this.seabed.paintTile(layer as Overlay, z, x, y, px, this.colour);
    }
    return { data: await createImageBitmap(image) };
  }

  /** The address of a painted layer's tiles: "depth", "snapper.spring", "veil.kayak". */
  private tiles = (layer: string): string[] => [`${TILE_SCHEME}://${layer}/{z}/{x}/{y}?${this.painted}`];

  /** Show a painted layer, adding it to the map the first time and repainting it if what it shows has changed. */
  private paintedLayer(id: string, layer: string, opacity: number): void {
    const map = this.map;
    if (!map.getLayer(id)) {
      map.addSource(id, {
        type: "raster",
        tiles: this.tiles(layer),
        tileSize: TILE_SIZE,
        bounds: this.seabed!.manifest.bounds,
        // One level past the map's closest zoom, so the closest view is painted, not stretched.
        maxzoom: Math.ceil(map.getMaxZoom()) + 1,
      });
      // Under the shaded relief, which is under the contours, which are under the land.
      const above = this.reliefLayers[0] ?? "contours";
      map.addLayer({ id, type: "raster", source: id, paint: { "raster-opacity": opacity, "raster-fade-duration": 0 } }, above);
    } else if (this.showing.get(id) !== layer) {
      map.getSource<maplibregl.RasterTileSource>(id)?.setTiles(this.tiles(layer));
    }
    this.showing.set(id, layer);
    map.setLayoutProperty(id, "visibility", "visible");
  }

  /** Zoomed in, fetch the 20 m grid, then have the map paint its tiles again from it. */
  private sharpen(): void {
    if (!this.seabed || this.map.getZoom() < DRAWING_FROM_ZOOM) return;
    this.map.off("zoom", this.sharpenOnZoom);
    void this.seabed.loadDrawing().then((ready) => {
      if (!ready) return;
      this.painted++;
      for (const [id, layer] of this.showing) {
        this.map.getSource<maplibregl.RasterTileSource>(id)?.setTiles(this.tiles(layer));
      }
    });
  }

  private sharpenOnZoom = (): void => this.sharpen();

  private async addSeabed(): Promise<void> {
    try {
      this.seabed = await Seabed.load();
    } catch (error) {
      // The conditions and the rest of the map still work without the seabed layers.
      console.error(error);
      return;
    }
    this.onSeabed(this.seabed.manifest);
    try {
      this.habitat = await Habitat.load(this.seabed.land);
      this.season = this.habitat.seasonNow();
    } catch (error) {
      // The seabed layers still work without the habitat index.
      console.error(error);
    }
    try {
      this.boats = await loadJson<BoatsManifest>("/boats/manifest.json");
      if (!this.boats.groups.some((g) => g.id === this.boatGroup)) this.boatGroup = "all";
    } catch (error) {
      // Everything else works without it.
      console.error(error);
    }
    if (!this.habitat && this.overlay === "snapper") this.overlay = "depth";
    if (!this.boats && this.overlay === "boats") this.overlay = "depth";
    if (!this.seabed.hasRoughGround && this.overlay === "rough") this.overlay = "depth";
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
      this.underLand,
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
      this.underLand,
    );
    this.addRelief(this.seabed.manifest.relief?.archives ?? []);
    // Under the zoom buttons on a wide screen; on a phone the top right is the free corner.
    const wide = window.matchMedia("(min-width: 860px)").matches;
    map.addControl(this.layerControl(this.seabed), wide ? "top-left" : "top-right");
    this.showSeabed();
    map.on("zoom", this.sharpenOnZoom);
    this.sharpen();
  }

  /**
   * The shaded relief: pictures of light and shadow made by scripts/build_relief.py,
   * read from archives on this site through the same protocol as the basemap. They
   * go under the contours, and every painted layer is put under them in turn.
   */
  private addRelief(archives: ReliefArchive[]): void {
    const map = this.map;
    const tileSize = this.seabed?.manifest.relief?.tile_px ?? TILE_SIZE;
    for (const archive of archives) {
      const id = `relief-${archive.key}`;
      map.addSource(id, {
        type: "raster",
        url: `pmtiles://${window.location.origin}${archive.url}?v=${archive.version}`,
        tileSize,
      });
      map.addLayer(
        {
          id,
          type: "raster",
          source: id,
          layout: { visibility: this.relief ? "visible" : "none" },
          paint: { "raster-opacity": RELIEF_OPACITY, "raster-fade-duration": 0 },
        },
        "contours",
      );
      this.reliefLayers.push(id);
    }
  }

  /** Show the chosen layer, adding it to the map the first time it is asked for. */
  private showSeabed(): void {
    const map = this.map;
    if (!this.seabed) return;
    const hide = (id: string) => map.getLayer(id) && map.setLayoutProperty(id, "visibility", "none");
    for (const { id } of OVERLAYS) {
      if (id !== this.overlay) hide(`seabed-${id}`);
    }
    if (this.overlay !== "snapper") {
      hide("seabed-veil");
      hide("shore");
    }
    if (this.overlay !== "boats") {
      hide("boats-fill");
      hide("boats-fixed");
    }
    if (this.overlay === "snapper") void this.showHabitat();
    else if (this.overlay === "boats") this.showBoats();
    else if (this.overlay !== "none") this.paintedLayer(`seabed-${this.overlay}`, this.overlay, 0.8);
    for (const id of ["contours", "contours-label"]) {
      map.setLayoutProperty(id, "visibility", this.contours ? "visible" : "none");
    }
    for (const id of this.reliefLayers) {
      map.setLayoutProperty(id, "visibility", this.relief ? "visible" : "none");
    }
  }

  /**
   * Show the habitat index for the chosen season. For kayak and shore fishing
   * the water out of reach is greyed, and for shore fishing the shore itself is
   * drawn as a line of points, each rated by the water a cast can reach.
   */
  private async showHabitat(): Promise<void> {
    const map = this.map;
    const habitat = this.habitat;
    const season = this.season;
    if (!habitat) return;
    try {
      await habitat.loadSeason(season);
    } catch (error) {
      console.error(error);
      return;
    }
    if (this.overlay !== "snapper" || this.season !== season) return; // another choice was made meanwhile
    this.paintedLayer("seabed-snapper", `snapper.${season}`, 0.85);
    if (this.style === "boat") {
      if (map.getLayer("seabed-veil")) map.setLayoutProperty("seabed-veil", "visibility", "none");
    } else {
      this.paintedLayer("seabed-veil", `veil.${this.style}`, 0.78);
    }

    const colours = habitat.manifest.classes.labels.flatMap((_, i) => {
      const [r, g, b] = this.colour(`--habitat-${i + 1}`);
      return [i + 1, `rgb(${r}, ${g}, ${b})`];
    });
    const fill = ["match", ["get", season], ...colours, "rgba(0, 0, 0, 0)"] as unknown as maplibregl.ExpressionSpecification;
    if (!map.getLayer("shore")) {
      const css = getComputedStyle(document.documentElement);
      map.addSource("shore", { type: "geojson", data: `/habitat/${habitat.manifest.reach.shore_points}` });
      map.addLayer(
        {
          id: "shore",
          type: "circle",
          source: "shore",
          paint: {
            "circle-radius": ["interpolate", ["linear"], ["zoom"], 9, 2, 12, 4, 15, 9],
            "circle-color": fill,
            "circle-stroke-color": css.getPropertyValue("--ink").trim() || "#0b0b0b",
            "circle-stroke-width": ["interpolate", ["linear"], ["zoom"], 9, 0.3, 13, 1],
          },
        },
        "ramps",
      );
    } else {
      map.setPaintProperty("shore", "circle-color", fill);
    }
    map.setLayoutProperty("shore", "visibility", this.style === "shore" ? "visible" : "none");
  }

  /**
   * Boats seen from space, as 1 km squares coloured by how many boats were seen per 100
   * clear passes in the chosen group of passes. Squares holding something seen on most
   * passes (moorings, rocks) are outlined. Under the relief, like the painted layers.
   */
  private showBoats(): void {
    const map = this.map;
    const boats = this.boats;
    if (!boats) return;
    const colours = boats.bands.labels.flatMap((_, i) => {
      const [r, g, b] = this.colour(`--boats-${i}`);
      return [i, `rgb(${r}, ${g}, ${b})`];
    });
    const fill = ["match", ["get", `${this.boatGroup}_band`], ...colours, "rgba(0, 0, 0, 0)"] as unknown as maplibregl.ExpressionSpecification;
    if (!map.getLayer("boats-fill")) {
      const [r, g, b] = this.colour("--boats-fixed");
      map.addSource("boats", { type: "geojson", data: `/boats/${boats.file}`, attribution: boats.source.licence });
      const above = this.reliefLayers[0] ?? "contours";
      map.addLayer({ id: "boats-fill", type: "fill", source: "boats", paint: { "fill-color": fill, "fill-opacity": BOATS_OPACITY } }, above);
      map.addLayer(
        {
          id: "boats-fixed",
          type: "line",
          source: "boats",
          filter: ["==", ["get", "fixed"], true],
          paint: { "line-color": `rgb(${r}, ${g}, ${b})`, "line-width": ["interpolate", ["linear"], ["zoom"], 9, 1, 13, 2.5] },
        },
        above,
      );
    } else {
      map.setPaintProperty("boats-fill", "fill-color", fill);
    }
    map.setLayoutProperty("boats-fill", "visibility", "visible");
    map.setLayoutProperty("boats-fixed", "visibility", "visible");
  }

  /** The style of fishing chosen in the panel: it decides what the habitat layer greys out. */
  setStyle(style: Style): void {
    if (style === this.style) return;
    this.style = style;
    if (this.overlay === "snapper") this.showSeabed();
    this.renderControl();
  }

  /** The forecast wind over the map, or null when there is none fit to show. */
  setWind(field: VectorField | null): void {
    this.flow.setField(field);
    this.renderControl();
  }

  /** Our own finer forecast, for the hours it has; null to draw the public one alone. */
  setFineWind(field: VectorField | null): void {
    this.flow.setFine(field);
    this.renderControl();
  }

  /** The hour the panel is showing, as written in the published files: the wind follows it. */
  setHour(iso: string): void {
    const had = this.flow.available;
    const from = this.flow.source?.id;
    this.flow.setHour(iso);
    if (had !== this.flow.available || from !== this.flow.source?.id) this.renderControl();
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
    const windKey = el("ul", "", "layers-key layers-wind");
    const windNote = el("p", "", "layers-note");
    const reliefNote = el("p", manifest.relief?.note ?? "", "layers-note");

    const swatch = (name: string, label: string) => {
      const item = el("li", label);
      const chip = el("i");
      chip.style.background = `var(${name})`;
      item.prepend(chip);
      return item;
    };
    const seasons = el("div", "", "layers-seasons");
    seasons.setAttribute("role", "group");
    seasons.setAttribute("aria-label", "Season");
    for (const { id, label } of SEASONS) {
      const button = el("button", label);
      button.type = "button";
      button.dataset.season = id;
      button.addEventListener("click", () => {
        this.season = id;
        this.showSeabed();
        render();
      });
      seasons.append(button);
    }
    const groups = el("div", "", "layers-seasons");
    groups.setAttribute("role", "group");
    groups.setAttribute("aria-label", "Which passes");
    for (const { id, label } of BOAT_GROUPS) {
      const button = el("button", label);
      button.type = "button";
      button.dataset.group = id;
      button.addEventListener("click", () => {
        this.boatGroup = id;
        store("boatGroup", id);
        this.showSeabed();
        render();
      });
      groups.append(button);
    }
    const render = () => {
      const chosen = OVERLAYS.find((o) => o.id === this.overlay)!;
      const group = this.boats?.groups.find((g) => g.id === this.boatGroup);
      summary.textContent =
        this.overlay === "none"
          ? "Map layer"
          : this.overlay === "snapper"
            ? `${chosen.label}: ${this.season}`
            : this.overlay === "boats"
              ? `Boats: ${(group?.label ?? "all passes").toLowerCase()}`
              : `Seabed: ${chosen.label.toLowerCase()}`;
      key.replaceChildren();
      seasons.hidden = this.overlay !== "snapper";
      for (const button of seasons.children) {
        button.setAttribute("aria-pressed", String((button as HTMLElement).dataset.season === this.season));
      }
      groups.hidden = this.overlay !== "boats";
      for (const button of groups.children) {
        button.setAttribute("aria-pressed", String((button as HTMLElement).dataset.group === this.boatGroup));
      }
      if (this.overlay === "snapper" && this.habitat) {
        const { classes, reach, species } = this.habitat.manifest;
        const fifths = classes.labels.map((label, i) => swatch(`--habitat-${i + 1}`, label)).reverse();
        fifths[0].append(" for the season");
        key.append(...fifths);
        const limit = reach.within_m_of_mainland_shore[this.style];
        if (this.style === "kayak" && limit != null) {
          key.append(swatch("--veil", `Greyed: more than ${limit / 1000} km from the mainland shore, taken as beyond kayak reach`));
        } else if (this.style === "shore") {
          key.append(swatch("--veil", "Greyed: beyond a cast. The points along the shore are rated by the water a cast can reach"));
        }
        const link = el("a", "How it is worked out");
        link.href = METHODS;
        note.replaceChildren(
          `How well the depth, the bottom and the reef nearby suit ${species.name.toLowerCase()} in ${this.season}, ranked within the bay. Not a catch forecast. `,
          link,
          ".",
        );
      } else if (this.overlay === "boats" && this.boats && group) {
        const boats = this.boats;
        const bands = boats.bands.labels.map((label, i) => swatch(`--boats-${i}`, label)).reverse();
        const fixed = el("li", "Outlined: moorings, rocks or buoys, seen on most passes; not counted");
        const outline = el("i", "", "layers-outline");
        outline.style.borderColor = "var(--boats-fixed)";
        fixed.prepend(outline);
        key.append(...bands, fixed);
        const link = el("a", "How it is counted");
        link.href = `${METHODS}#boats`;
        const { certain, likely, sample } = boats.check;
        note.replaceChildren(
          `On trial. Boats seen by the Sentinel-2 satellite at about 11:25, on ${group.passes} clear passes from ${boats.first_pass.slice(0, 4)} to ${boats.last_pass.slice(0, 4)}: ${group.boats_per_pass} a pass in the bay. Where boats were, not where fish are. Checked by eye, ${certain + likely} of ${sample} were boats. `,
          link,
          ".",
        );
      } else if (this.overlay === "depth") {
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
      } else if (this.overlay === "rough" && manifest.layers.fine_roughness) {
        const { bands_m: bands, reading } = manifest.layers.fine_roughness;
        const metres = (value: number) => value.toFixed(2);
        key.append(
          swatch("--rough-0", `Under ${metres(bands[0])} m`),
          ...bands.slice(1).map((upTo, i) => swatch(`--rough-${i + 1}`, `${metres(bands[i])} to ${metres(upTo)} m`)),
          swatch(`--rough-${bands.length}`, `Over ${metres(bands[bands.length - 1])} m`),
        );
        note.textContent = `How uneven the bottom is over 10 m, in the roughest patches of each 100 m square, where LiDAR measured the depth. A hint of reef, not a bottom type. ${reading}`;
      } else {
        note.textContent = "Tap the water for depth and bottom type.";
      }

      reliefNote.hidden = !this.relief;
      windKey.replaceChildren();
      windKey.hidden = !this.wind || !this.flow.available;
      windNote.hidden = !this.wind;
      const cell = this.flow.cellKm;
      if (!this.flow.available) {
        windNote.textContent = "No wind forecast to draw for this hour.";
      } else {
        for (const [i, band] of FLOW_BANDS.entries()) {
          const item = el("li", band.label);
          const line = el("i");
          line.style.width = `${10 + i * 6}px`;
          line.style.height = `${Math.max(1.5, band.width * 1.4)}px`;
          item.prepend(line);
          windKey.append(item);
        }
        const source = this.flow.source;
        if (source?.model_km != null) {
          // Our own run, on trial. Say so, and say what it has not been through.
          windNote.textContent = `On trial: our own forecast for this hour, worked out in ${source.model_km} km squares. It has not yet been checked against measured wind, and hills narrower than a few kilometres are still too small for it. Faster, longer and heavier is stronger.`;
        } else {
          // The forecast knows nothing finer than its own squares. Say how big they are.
          const squares = cell ? ` in squares about ${Math.round(cell[0])} by ${Math.round(cell[1])} km` : "";
          windNote.textContent = `Forecast wind for the hour shown in the panel: faster, longer and heavier is stronger. The forecast works${squares}, so it does not show shelter close under the hills.`;
        }
      }
    };

    const choices = el("fieldset");
    choices.append(el("legend", "Colour the water by", "visually-hidden"));
    for (const { id, label } of OVERLAYS) {
      if (id === "snapper" && !this.habitat) continue;
      if (id === "boats" && !this.boats) continue;
      if (id === "rough" && !seabed.hasRoughGround) continue;
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

    const shading = el("input");
    shading.type = "checkbox";
    shading.checked = this.relief;
    shading.addEventListener("change", () => {
      this.relief = shading.checked;
      store("relief", shading.checked ? "on" : "off");
      this.showSeabed();
      render();
    });
    const shadingRow = el("label", "", "layers-contours");
    shadingRow.append(shading, "Seabed relief");

    const wind = el("input");
    wind.type = "checkbox";
    wind.checked = this.wind;
    wind.addEventListener("change", () => {
      this.wind = wind.checked;
      store("wind", wind.checked ? "on" : "off");
      this.flow.setShown(this.wind);
      render();
    });
    const windRow = el("label", "", "layers-contours");
    windRow.append(wind, "Wind");

    box.append(summary, choices, seasons, groups, linesRow, key, note);
    if (this.reliefLayers.length) box.append(shadingRow, reliefNote);
    box.append(windRow, windKey, windNote);
    this.renderControl = render;
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
      // Open the popup towards the middle of the map that is not under the panel, and
      // fix that side, so it does not flip over while reveal() slides the map.
      const { top, bottom } = this.padding;
      const middle = (top + map.getContainer().clientHeight - bottom) / 2;
      const anchor = event.point.y > middle ? "bottom" : "top";
      const popup = new maplibregl.Popup({ closeButton: false, maxWidth: "280px", anchor }).setLngLat(event.lngLat);
      const ramp = named("ramps");
      if (ramp !== undefined) {
        popup.setText(`${ramp} (from OpenStreetMap; check access before you tow)`).addTo(map);
        return;
      }
      const reserve = named("reserves-fill");
      // The seabed is read only where the map shows water: a tap on the land says nothing.
      const drawn = map.getLayer(LAND) ? map.queryRenderedFeatures(event.point, { layers: [LAND, "water"] }) : [];
      const onLand = drawn.length > 0 && !drawn.some((f) => f.layer.id === "water");
      const spot = onLand ? null : this.seabed?.inspect(event.lngLat.lng, event.lngLat.lat);
      if (reserve === undefined && !spot) return;
      const content = el("div");
      if (reserve !== undefined) {
        content.append(el("p", `${reserve}: no-take. All fishing is prohibited here.`, "spot-rule"));
      }
      const habitat = this.overlay === "snapper" ? this.habitat : null;
      const rating = el("div");
      if (spot && this.overlay === "boats" && this.boats && map.getLayer("boats-fill")) {
        const square = map.queryRenderedFeatures(event.point, { layers: ["boats-fill"] })[0];
        if (square?.properties) content.append(describeBoats(square.properties, this.boats));
      }
      if (spot) content.append(rating, describeSpot(spot, this.seabed?.manifest.layers.fine_roughness?.reading));
      popup.setDOMContent(content).addTo(map);
      // Once it has been laid out, so its real size and place are known.
      requestAnimationFrame(() => this.reveal(popup));
      if (spot && habitat && this.seabed) {
        const cell = this.seabed.cellAt(event.lngLat.lng, event.lngLat.lat);
        void habitat.inspect(cell, this.season).then((point) => {
          if (!point || !popup.isOpen()) return;
          rating.append(describeHabitat(point, habitat, this.style));
          requestAnimationFrame(() => this.reveal(popup));
        });
      }
    });
    map.on("mouseenter", "ramps", () => (map.getCanvas().style.cursor = "pointer"));
    map.on("mouseleave", "ramps", () => (map.getCanvas().style.cursor = ""));
  }

  /** Shift the map just far enough that a popup is not hidden under the panel or the top bar.
      In one step: an eased move can be cut short by the next camera change. */
  private reveal(popup: maplibregl.Popup): void {
    const box = popup.getElement()?.getBoundingClientRect();
    if (!box) return;
    const view = this.map.getContainer().getBoundingClientRect();
    const { top, right, bottom, left } = this.padding;
    const dx = Math.max(0, box.right - (view.right - right)) || Math.min(0, box.left - (view.left + left));
    const dy = Math.max(0, box.bottom - (view.bottom - bottom)) || Math.min(0, box.top - (view.top + top));
    if (dx || dy) this.map.panBy([dx, dy], { duration: 0 });
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
