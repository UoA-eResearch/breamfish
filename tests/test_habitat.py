"""The habitat index: curves, the mean, the classes, and the species file itself."""

from math import inf

import pytest

from breamfish import habitat


def test_a_curve_runs_straight_between_its_points_and_holds_beyond_them():
    points = [[0, 0.2], [10, 1.0], [30, 0.5]]
    assert habitat.interpolate(points, -3) == 0.2
    assert habitat.interpolate(points, 0) == 0.2
    assert habitat.interpolate(points, 5) == pytest.approx(0.6)
    assert habitat.interpolate(points, 10) == 1.0
    assert habitat.interpolate(points, 20) == pytest.approx(0.75)
    assert habitat.interpolate(points, 500) == 0.5


def test_the_index_is_a_weighted_geometric_mean():
    weights = {"a": 1.0, "b": 1.0, "c": 2.0}
    assert habitat.combine({"a": 0.5, "b": 0.5, "c": 0.5}, weights) == pytest.approx(0.5)
    # 0.25 and 1.0 average to 0.5 geometrically, not 0.625.
    assert habitat.combine({"a": 0.25, "b": 1.0, "c": None}, weights) == pytest.approx(0.5)
    # The heavier factor pulls harder.
    assert habitat.combine({"a": 1.0, "b": 1.0, "c": 0.25}, weights) == pytest.approx(0.5)


def test_one_hopeless_factor_cannot_be_averaged_away():
    weights = {"depth": 1.0, "bottom": 1.0, "reef": 1.0}
    assert habitat.combine({"depth": 0.0, "bottom": 1.0, "reef": 1.0}, weights) < 0.02


def test_a_factor_with_no_data_is_left_out_not_counted_as_zero():
    weights = {"depth": 1.0, "bottom": 1.0}
    assert habitat.combine({"depth": 0.8, "bottom": None}, weights) == pytest.approx(0.8)
    assert habitat.combine({"depth": None, "bottom": None}, weights) is None


def test_fifths_split_distinct_values_evenly():
    values = [i / 100 for i in range(100)]
    breaks = habitat.fifths(values)
    assert breaks == [0.2, 0.4, 0.6, 0.8]
    classes = [habitat.class_of(v, breaks) for v in values]
    assert [classes.count(c) for c in range(1, 6)] == [20] * 5


def test_water_with_the_same_index_shares_the_class_its_middle_falls_in():
    # A tenth low, a tenth high, and four fifths of the bay all the same.
    values = [0.1] * 10 + [0.5] * 80 + [0.9] * 10
    breaks = habitat.fifths(values)
    assert habitat.class_of(0.5, breaks) == 3  # the middle, not pushed up to the top
    assert habitat.class_of(0.1, breaks) == 1 and habitat.class_of(0.9, breaks) == 5
    # Nothing is in the second or fourth class, and no value falls between boundaries.
    assert breaks == [0.5, 0.5, 0.9, 0.9]


def test_a_class_nothing_reaches_has_a_boundary_at_infinity():
    breaks = habitat.fifths([0.3] * 10)
    assert habitat.class_of(0.3, breaks) == 3
    assert breaks == [0.3, 0.3, inf, inf]


def test_auc_is_the_chance_a_record_outranks_the_background():
    background = [0.1, 0.2, 0.3, 0.4]
    assert habitat.auc([0.5], background) == 1.0
    assert habitat.auc([0.0], background) == 0.0
    assert habitat.auc([0.25], background) == 0.5
    assert habitat.auc([0.2], background) == pytest.approx(0.375)  # one below, one tie
    assert habitat.auc([0.5, 0.0], background) == 0.5


# --- The snapper file ---------------------------------------------------------------------


@pytest.fixture(scope="module")
def snapper():
    return habitat.load_species("snapper")


def test_the_snapper_file_loads_and_every_month_has_a_season(snapper):
    assert snapper.scientific_name == "Chrysophrys auratus"
    assert [f.key for f in snapper.factors] == ["depth", "bottom", "reef"]
    assert snapper.season_of(11) == "spring" and snapper.season_of(12) == "summer"
    assert {snapper.season_of(m) for m in range(1, 13)} == set(snapper.seasons)


def test_every_number_in_the_snapper_file_has_a_source_or_owns_up(snapper):
    """A curve says what is published and what was decided here; evidence cites a
    reference that exists, with a place to read it."""
    references = snapper.spec["reference"]
    cited = set()
    for factor in snapper.factors:
        spec = factor.spec
        assert spec["evidence"], factor.key
        cited |= {item["ref"] for item in spec["evidence"]}
        assert spec["confidence"] and spec["limits"], factor.key
        curves = spec["curve"].values() if "curve" in spec else [spec] if "points" in spec else []
        for curve in curves:
            assert curve["basis"].strip() and curve["judgement"].strip(), factor.key
        if "scores" in spec:
            assert set(spec["judgements"]) == set(spec["scores"]), factor.key
    assert cited == set(references), "a reference nobody cites, or a citation with no reference"
    for key, reference in references.items():
        assert reference["url"].startswith("https://"), key
        assert reference["citation"] and reference["read"], key


def test_depth_suits_the_shallows_in_summer_and_deeper_water_in_winter(snapper):
    depth = snapper.factors[0]
    assert depth.seasonal
    assert depth.suitability(15, "summer") == 1.0
    assert depth.suitability(60, "summer") < 0.4
    assert depth.suitability(60, "winter") == 1.0
    assert depth.suitability(5, "winter") < depth.suitability(5, "summer")
    for season in snapper.seasons:  # nobody catches snapper at 200 m, or on dry sand
        assert depth.suitability(200, season) <= 0.05
        assert depth.suitability(-2, season) <= 0.4
    assert depth.suitability(None, "summer") is None


def test_bottom_scores_are_close_together_with_reef_on_top(snapper):
    bottom = snapper.factors[1]
    scores = bottom.spec["scores"]
    assert max(scores, key=scores.get) == "rock"
    assert min(scores.values()) >= 0.4  # adults are found over every bottom
    assert bottom.suitability("soft", "") == pytest.approx((scores["sand"] + scores["mud"]) / 2)
    assert bottom.suitability(None, "") is None  # not mapped: left out, never zero


def test_distance_from_reef_falls_away_but_never_to_nothing(snapper):
    reef = snapper.factors[2]
    assert not reef.seasonal
    values = [reef.suitability(d, "") for d in (0, 100, 300, 700, 5000)]
    assert values == sorted(values, reverse=True)
    assert values[0] == 1.0 and values[-1] == 0.4


def test_a_broken_species_file_is_refused(tmp_path, snapper):
    text = (habitat.SPECIES_DIR / "snapper.toml").read_text()
    cases = {
        "summer = [12, 1, 2]": "summer = [12, 1]",  # February has no season
        "weight = 1.0": "weight = 0",
        "points = [[0, 1.0], [100, 0.9], [300, 0.6], [700, 0.4]]": "points = [[0, 1.0], "
        "[300, 0.9], [100, 0.6]]",  # values out of order
        'ref = "egli2004"': 'ref = "nobody2099"',
    }
    for old, new in cases.items():
        assert old in text, old
        (tmp_path / "snapper.toml").write_text(text.replace(old, new, 1))
        with pytest.raises(ValueError):
            habitat.load_species("snapper", tmp_path)
