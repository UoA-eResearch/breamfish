// Longitude and latitude to New Zealand Transverse Mercator (EPSG:2193), the
// projection the seabed and habitat grids are laid out in.

// By the series LINZ publishes for it. Good to a millimetre here. The seabed
// manifest carries points worked out by PROJ, and Seabed.load() refuses the
// grids if this disagrees. src/breamfish/nztm.py is the same arithmetic.

const A = 6378137;
const F = 1 / 298.257222101;
const K0 = 0.9996;
const LON0 = (173 * Math.PI) / 180;
const FALSE_E = 1_600_000;
const FALSE_N = 10_000_000;
const E2 = 2 * F - F * F;
const E4 = E2 * E2;
const E6 = E4 * E2;
const A0 = 1 - E2 / 4 - (3 * E4) / 64 - (5 * E6) / 256;
const A2 = (3 / 8) * (E2 + E4 / 4 + (15 * E6) / 128);
const A4 = (15 / 256) * (E4 + (3 * E6) / 4);
const A6 = (35 * E6) / 3072;

/** The parts of the projection that depend on latitude alone. */
export function latitudeTerms(latDeg: number) {
  const phi = (latDeg * Math.PI) / 180;
  const sin = Math.sin(phi);
  const cos = Math.cos(phi);
  const t = sin / cos;
  const m = A * (A0 * phi - A2 * Math.sin(2 * phi) + A4 * Math.sin(4 * phi) - A6 * Math.sin(6 * phi));
  const w = 1 - E2 * sin * sin;
  const nu = A / Math.sqrt(w);
  const psi = w / (1 - E2); // nu / rho
  return { sin, cos, t2: t * t, m, nu, psi };
}

export function project(terms: ReturnType<typeof latitudeTerms>, lonDeg: number): [number, number] {
  const { sin, cos, t2, m, nu, psi } = terms;
  const w = (lonDeg * Math.PI) / 180 - LON0;
  const w2c2 = w * w * cos * cos;
  const t4 = t2 * t2;
  const t6 = t4 * t2;
  const psi2 = psi * psi;
  const e1 = (w2c2 / 6) * (psi - t2);
  const e2 = ((w2c2 * w2c2) / 120) * (4 * psi2 * psi * (1 - 6 * t2) + psi2 * (1 + 8 * t2) - psi * 2 * t2 + t4);
  const e3 = ((w2c2 * w2c2 * w2c2) / 5040) * (61 - 479 * t2 + 179 * t4 - t6);
  const n1 = (w2c2 / 12) * (4 * psi2 + psi - t2);
  const n2 =
    ((w2c2 * w2c2) / 360) *
    (8 * psi2 * psi2 * (11 - 24 * t2) - 28 * psi2 * psi * (1 - 6 * t2) + psi2 * (1 - 32 * t2) - psi * 2 * t2 + t4);
  const n3 = ((w2c2 * w2c2 * w2c2) / 20160) * (1385 - 3111 * t2 + 543 * t4 - t6);
  const easting = FALSE_E + K0 * nu * w * cos * (1 + e1 + e2 + e3);
  const northing = FALSE_N + K0 * (m + ((nu * sin * w * w) / 2) * cos * (1 + n1 + n2 + n3));
  return [easting, northing];
}

export const nztm = (lon: number, lat: number): [number, number] => project(latitudeTerms(lat), lon);
