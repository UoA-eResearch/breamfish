#!/usr/bin/env bash
# Build the self-hosted basemap: a small OpenStreetMap vector-tile extract of
# the bay, plus the fonts and icons the map style needs. The outputs are
# committed, so this only needs re-running to refresh the map data.
#
# Needs the `pmtiles` CLI (macOS: brew install pmtiles).
# Usage: scripts/make_basemap.sh [BUILD_DATE]   e.g. scripts/make_basemap.sh 20261125
set -euo pipefail

cd "$(dirname "$0")/.."
PUBLIC=web/public
BUILD="${1:-}"

if [ -z "$BUILD" ]; then
  # Newest daily Protomaps build of OpenStreetMap.
  BUILD=$(curl -fsS https://build-metadata.protomaps.dev/builds.json |
    python3 -c 'import json,sys; print(sorted(b["key"] for b in json.load(sys.stdin))[-1].removesuffix(".pmtiles"))')
fi

# Wider than the study box so there is context when panning.
BBOX="174.10,-36.35,175.10,-35.55"

mkdir -p "$PUBLIC/tiles" "$PUBLIC/fonts" "$PUBLIC/sprites"

echo "Extracting tiles from Protomaps build $BUILD ..."
pmtiles extract "https://build.protomaps.com/$BUILD.pmtiles" "$PUBLIC/tiles/breambay.pmtiles" \
  --bbox="$BBOX" --maxzoom=14

# Only the glyph ranges New Zealand place names use: basic Latin, Latin
# Extended-A (macrons) and general punctuation.
ASSETS=https://protomaps.github.io/basemaps-assets
for font in "Noto Sans Regular" "Noto Sans Medium" "Noto Sans Italic"; do
  mkdir -p "$PUBLIC/fonts/$font"
  for range in 0-255 256-511 8192-8447; do
    curl -fsS "$ASSETS/fonts/${font// /%20}/$range.pbf" -o "$PUBLIC/fonts/$font/$range.pbf"
  done
done

for file in light.json light.png light@2x.json light@2x.png dark.json dark.png dark@2x.json dark@2x.png; do
  curl -fsS "$ASSETS/sprites/v4/$file" -o "$PUBLIC/sprites/$file"
done

echo "$BUILD" > "$PUBLIC/tiles/BUILD"
du -sh "$PUBLIC/tiles" "$PUBLIC/fonts" "$PUBLIC/sprites"
