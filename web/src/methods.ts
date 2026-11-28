// The methods page: what the habitat index is built from, the evidence each
// part leans on, how it tests against real records, and its limits. Every
// number and every sentence about the index comes from /habitat/manifest.json,
// which scripts/build_habitat.py writes from the species file; this page lays
// it out and works nothing out itself. The boat count below it is laid out the
// same way from /boats/manifest.json (scripts/build_boats.py).

import "./style.css";
import { loadJson, type BoatsManifest, type Curve, type HabitatFactor, type HabitatManifest, type Season, type ValidationGroup } from "./data";

type Child = Node | string;

function el<K extends keyof HTMLElementTagNameMap>(tag: K, ...children: Child[]): HTMLElementTagNameMap[K] {
  const node = document.createElement(tag);
  node.append(...children);
  return node;
}

const capital = (text: string): string => text.charAt(0).toUpperCase() + text.slice(1);
const share = (part: number, whole: number): string => `${Math.round((100 * part) / whole)}%`;

function table(head: string[], rows: Child[][], caption = ""): HTMLElement {
  const wrap = el("div");
  wrap.className = "doc-table";
  const body = el("tbody", ...rows.map((cells) => el("tr", ...cells.map((cell, i) => (i === 0 ? el("th", cell) : el("td", cell))))));
  const t = el("table", el("thead", el("tr", ...head.map((h) => el("th", h)))), body);
  if (caption) t.prepend(el("caption", caption));
  for (const th of t.querySelectorAll("thead th")) th.setAttribute("scope", "col");
  for (const th of t.querySelectorAll("tbody th")) th.setAttribute("scope", "row");
  wrap.append(t);
  return wrap;
}

/** A curve as two rows: the value, and how well it suits (0 to 1). */
function curveTable(points: Curve, unit: string, what: string, caption: string): HTMLElement {
  const wrap = el("div");
  wrap.className = "doc-table";
  const row = (label: string, cells: string[]) => {
    const th = el("th", label);
    th.setAttribute("scope", "row");
    return el("tr", th, ...cells.map((c) => el("td", c)));
  };
  const t = el(
    "table",
    el("caption", caption),
    el(
      "tbody",
      row(`${what} (${unit})`, points.map(([value], i) => (i === points.length - 1 ? `${value} and over` : String(value)))),
      row("Suits", points.map(([, suits]) => suits.toFixed(2).replace(/0$/, ""))),
    ),
  );
  wrap.append(t);
  return wrap;
}

function factorSection(factor: HabitatFactor, manifest: HabitatManifest): HTMLElement {
  const section = el("section", el("h3", factor.label));
  if (factor.confidence) section.append(el("p", el("strong", "How sure: "), factor.confidence, "."));
  const said = (label: string, text?: string) => text && section.append(el("p", el("strong", `${label} `), text.trim()));

  if (factor.curve) {
    for (const season of Object.keys(manifest.seasons) as Season[]) {
      const curve = factor.curve[season];
      section.append(curveTable(curve.points, factor.unit ?? "", factor.label, capital(season)));
      said("What is published:", curve.basis);
      said("What was decided here:", curve.judgement);
    }
  } else if (factor.points) {
    section.append(curveTable(factor.points, factor.unit ?? "", factor.label, "All year"));
    said("What is published:", factor.basis);
    said("What was decided here:", factor.judgement);
  } else if (factor.scores) {
    const keys = Object.keys(factor.scores).sort((a, b) => factor.scores![b] - factor.scores![a]);
    section.append(
      table(
        ["Bottom", "Suits", "Why"],
        keys.map((key) => [factor.class_labels?.[key] ?? key, factor.scores![key].toFixed(1), factor.judgements?.[key] ?? ""]),
      ),
    );
  }
  said("", factor.note);
  said("What this cannot show:", factor.limits);

  const list = el("ul");
  for (const item of factor.evidence) {
    const ref = manifest.references[item.ref];
    const link = el("a", ref.citation);
    link.href = ref.url;
    link.target = "_blank";
    link.rel = "noopener";
    list.append(el("li", item.says, " ", el("small", link)));
  }
  section.append(el("h4", "What the studies say"), list);
  return section;
}

function validationRow(group: ValidationGroup): Child[] {
  const interval = group.auc_low == null ? "too few to say" : `${group.auc_low.toFixed(2)} to ${group.auc_high!.toFixed(2)}`;
  return [group.label, String(group.places), group.auc.toFixed(2), interval, `${Math.round(100 * group.share_in_top_two_fifths)}%`];
}

function render(manifest: HabitatManifest): Node[] {
  const { species, classes, reach, validation } = manifest;
  const seasons = Object.keys(manifest.seasons) as Season[];
  const out: Node[] = [];

  out.push(
    el("p", el("strong", species.summary)),
    el("p", `It is for: ${species.applies_to.toLowerCase()} (`, el("em", species.scientific_name), ")."),
    el(
      "p",
      "Nobody publishes where fish are caught in this bay at a scale that would let a catch forecast be built or tested. So this is built the other way round: from what studies of north-east New Zealand say about where snapper live, applied to the map of the seabed. Each number below is given with the study it leans on, and with what had to be decided without one.",
    ),
  );

  out.push(el("h2", "The three things it looks at"));
  out.push(
    el(
      "p",
      "Each turns something known about a 100 m square of seabed into a figure from 0 (does not suit) to 1 (suits best). Between the values in a table the figure runs in a straight line.",
    ),
  );
  for (const factor of manifest.factors) out.push(factorSection(factor, manifest));

  out.push(el("h2", "How they are put together"));
  const weights = manifest.factors.map((f) => `${f.label.toLowerCase()} ${f.weight}`).join(", ");
  out.push(
    el(
      "p",
      `${manifest.index.how} The weights are: ${weights}. A geometric mean is used so that a square is only as good as its factors together: one poor factor cannot be averaged away by two good ones. Where the bottom type is not mapped, that factor is left out for the square and the other two carry it.`,
    ),
    el("p", classes.note),
    table(
      ["Season", ...classes.labels],
      seasons.map((season) => {
        const cells = classes.cells[season];
        const all = cells.reduce((sum, n) => sum + n, 0);
        return [capital(season), ...cells.map((n) => share(n, all))];
      }),
      "Share of the rated water in each class",
    ),
  );

  out.push(el("h2", "Where it is not shown, and reach"));
  const limit = reach.within_m_of_mainland_shore;
  out.push(
    el("p", manifest.not_rated.note),
    el(
      "p",
      `When Kayak is chosen, water more than ${(limit.kayak ?? 0) / 1000} km from the mainland shore is greyed out. When Shore is chosen, everything beyond a cast (${limit.shore} m) is greyed out and the shore is drawn as a line of points, each rated by the water within reach of it. ${reach.note}`,
    ),
  );

  out.push(el("h2", "How it tests against real records"));
  const overall = validation.groups.filter((g) => g.season == null);
  out.push(
    el(
      "p",
      `The index was not built from records of snapper, so the few public ones can be used to test it. There are ${validation.records} places and times in the bay where snapper were caught for tagging, taken in a research trawl or photographed. Each is compared with the index for its own season.`,
    ),
    el("p", validation.how_to_read),
    table(["Records", "Places", "AUC", "95% interval", "In the top two fifths"], overall.map(validationRow)),
    el(
      "p",
      `${validation.unused.no_month} records give no month and ${validation.unused.outside_or_no_water} have no rated water nearby; those are not used. The figures by season are in the build report in the source repository.`,
    ),
    el("p", el("strong", "Read these with care:")),
    el("ul", ...validation.cautions.map((text) => el("li", text))),
  );

  out.push(el("h2", "What it cannot tell you"), el("ul", ...manifest.limits.map((text) => el("li", text))));

  out.push(el("h2", "Sources"));
  const sources = el("ul");
  sources.className = "doc-sources";
  for (const ref of Object.values(manifest.references).sort((a, b) => a.citation.localeCompare(b.citation))) {
    const link = el("a", ref.url.replace(/^https?:\/\//, ""));
    link.href = ref.url;
    link.target = "_blank";
    link.rel = "noopener";
    sources.append(el("li", ref.citation, " ", link, " ", el("small", `Read: ${ref.read}.`)));
  }
  out.push(sources, el("p", el("small", `Built ${manifest.built} from the seabed grids of ${(manifest as { seabed_built?: string }).seabed_built ?? "the same day"}.`)));
  return out;
}

const target = document.getElementById("methods")!;
loadJson<HabitatManifest>("/habitat/manifest.json")
  .then((manifest) => target.replaceChildren(...render(manifest)))
  .catch((error) => {
    console.error(error);
    target.replaceChildren(el("p", "The habitat index could not be loaded just now. Please try again shortly."));
  });

function renderBoats(manifest: BoatsManifest): Node[] {
  const { check } = manifest;
  const link = el("a", manifest.source.label);
  link.href = manifest.source.url;
  link.target = "_blank";
  link.rel = "noopener";
  return [
    el("h2", "Boats seen from space"),
    el(
      "p",
      el("strong", "On trial. "),
      `A second map layer shows where boats were seen in pictures taken by the Sentinel-2 satellites, from ${manifest.first_pass} to ${manifest.last_pass}. It says where people take their boats, in ${manifest.square_m / 1000} km squares. It is not a count of fish, and many of the boats are going somewhere, not fishing.`,
    ),
    el("p", manifest.how),
    table(
      ["Passes", "Clear passes used", "Boats", "Boats a pass"],
      manifest.groups.map((g) => [g.label, String(g.passes), String(g.boats), String(g.boats_per_pass)]),
    ),
    el(
      "p",
      `A further ${manifest.passes_left_out} passes were left out as too rough or too broken by cloud to tell a boat from a whitecap. ${manifest.fixed_squares} squares hold something seen on most passes (moorings, rocks or buoys); they are outlined, and boats right beside those things are not counted.`,
    ),
    el("h3", "How well it finds boats"),
    el(
      "p",
      `${check.sample} of the boats it kept were picked at random and their pictures looked at: ${check.certain} were certainly boats, ${check.likely} were likely boats, ${check.cloud_or_rock} were cloud or rock, and ${check.unclear} could not be told. ${check.note} Judged by ${check.judged_by}. These ${check.sample} were not used to set the checks.`,
    ),
    el("h3", "What it cannot tell you"),
    el("ul", ...manifest.limits.map((text) => el("li", text))),
    el("p", el("small", "From: ", link, `. ${manifest.source.licence}. Built ${manifest.built}.`)),
  ];
}

const boatsTarget = document.getElementById("boats");
if (boatsTarget) {
  loadJson<BoatsManifest>("/boats/manifest.json")
    .then((manifest) => {
      boatsTarget.replaceChildren(...renderBoats(manifest));
      if (window.location.hash === "#boats") boatsTarget.scrollIntoView();
    })
    .catch((error) => console.error(error));
}
