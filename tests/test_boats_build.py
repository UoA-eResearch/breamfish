"""The boat layer build: on a made-up count, and then the files that are committed."""

import json
from pathlib import Path

import pytest

import build_boats

ROOT = Path(__file__).parent.parent
PUBLISHED = ROOT / "web" / "public" / "boats"
RING = [[174.60, -35.90], [174.61, -35.90], [174.61, -35.91], [174.60, -35.91]]


def square(all_seen, all_boats, weekend_seen, weekend_boats, fixed=False):
    return {
        "ring": [list(corner) for corner in RING],
        "fixed": fixed,
        "all": {"seen": all_seen, "boats": all_boats},
        "weekend": {"seen": weekend_seen, "boats": weekend_boats},
        "weekday": {"seen": all_seen - weekend_seen, "boats": all_boats - weekend_boats},
    }


def site(*squares):
    boats = {g: sum(s[g]["boats"] for s in squares) for g in build_boats.GROUPS}
    return {
        "schema": 1,
        "made": "2026-11-28T04:00:00Z",
        "first_pass": "2017-07-14",
        "last_pass": "2026-11-19",
        "square_m": 1000,
        "summary": {
            "passes": {"all": 300, "weekend": 90, "weekday": 210},
            "boats": boats,
            "scenes_left_out": 7,
        },
        "squares": list(squares),
    }


def test_band_runs_from_none_seen_to_the_busiest():
    assert build_boats.band(0, 200) == 0
    assert build_boats.band(1, 200) == 1  # 0.5 per 100 passes
    assert build_boats.band(1, 75) == 1  # 1.33: a single boat stays in the lowest band
    assert build_boats.band(5, 200) == 2  # 2.5
    assert build_boats.band(10, 200) == 3  # 5
    assert build_boats.band(20, 200) == 4  # 10
    assert build_boats.band(30, 200) == 5  # 15


def test_one_label_per_band():
    labels = build_boats.band_labels()
    assert len(labels) == len(build_boats.BREAKS) + 2
    assert labels[0].startswith("Clear water")


def test_build_writes_counts_bands_and_a_closed_ring():
    geojson, manifest = build_boats.build(
        site(square(200, 30, 60, 20), square(150, 0, 50, 0, fixed=True)), "2026-11-28"
    )
    first, second = (f["properties"] for f in geojson["features"])
    assert first["all_band"] == 5 and first["weekend_band"] == 5 and first["weekday_band"] == 4
    assert first["all_seen"] == 200 and first["weekday_boats"] == 10
    assert second["all_band"] == 0 and second["fixed"] is True
    ring = geojson["features"][0]["geometry"]["coordinates"][0]
    assert ring[0] == ring[-1] and len(ring) == 5
    assert manifest["fixed_squares"] == 1
    assert [g["boats"] for g in manifest["groups"]] == [30, 20, 10]
    assert manifest["groups"][0]["boats_per_pass"] == 0.1


def test_a_group_never_clear_has_no_band():
    geojson, _ = build_boats.build(site(square(40, 1, 0, 0)), "2026-11-28")
    assert geojson["features"][0]["properties"]["weekend_band"] == -1


@pytest.mark.parametrize(
    "spoil, message",
    [
        (lambda s: s.update(schema=2), "schema"),
        (lambda s: s["squares"][0]["ring"][0].__setitem__(0, 170.0), "outside the bay"),
        (lambda s: s["squares"][0]["weekend"].__setitem__("boats", 25), "do not add up"),
        (lambda s: s["squares"][0]["all"].__setitem__("seen", 0), "never seen"),
        (lambda s: s["squares"][0]["all"].__setitem__("boats", -1), "negative"),
        (lambda s: s["summary"]["boats"].__setitem__("all", 3), "more boats"),
    ],
)
def test_a_file_that_does_not_add_up_is_refused(spoil, message):
    bad = site(square(200, 30, 60, 20))
    spoil(bad)
    with pytest.raises(ValueError, match=message):
        build_boats.build(bad, "2026-11-28")


def test_committed_files_agree_with_each_other():
    manifest = json.loads((PUBLISHED / "manifest.json").read_text())
    geojson = json.loads((PUBLISHED / manifest["file"]).read_text())
    features = geojson["features"]
    assert len(features) == manifest["squares"]
    assert sum(f["properties"]["fixed"] for f in features) == manifest["fixed_squares"]
    for group in manifest["groups"]:
        gid = group["id"]
        assert sum(f["properties"][f"{gid}_boats"] for f in features) == group["boats"]
        for f in features:
            props = f["properties"]
            expected = (
                build_boats.band(props[f"{gid}_boats"], props[f"{gid}_seen"])
                if props[f"{gid}_seen"]
                else -1
            )
            assert props[f"{gid}_band"] == expected
    assert len(manifest["bands"]["labels"]) == len(manifest["bands"]["breaks_per_100_passes"]) + 2
    check = manifest["check"]
    assert (
        check["certain"] + check["likely"] + check["cloud_or_rock"] + check["unclear"]
        == check["sample"]
    )
