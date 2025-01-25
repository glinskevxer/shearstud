"""The three stage composite stack, and the ordering that has to hold between
its sections."""

from __future__ import annotations

import pytest

from shearstud.errors import GeometryError
from shearstud.geometry.composite import (
    CREEP_FACTOR,
    DECK_LABEL,
    CompositeGirder,
    DeckSlab,
    compose,
    concrete_modulus_ksi,
    modular_ratio,
)
from shearstud.geometry.section import Section

pytestmark = pytest.mark.geometry


def test_four_ksi_concrete_comes_out_near_thirty_six_hundred_ksi() -> None:
    assert concrete_modulus_ksi(4.0) == pytest.approx(3640.0, rel=1e-3)


def test_a_stronger_mix_is_stiffer_but_not_proportionally() -> None:
    weak = concrete_modulus_ksi(3.0)
    strong = concrete_modulus_ksi(6.0)
    assert strong > weak
    assert strong < 2.0 * weak


def test_the_modular_ratio_for_four_ksi_is_the_familiar_eight() -> None:
    assert modular_ratio(4.0) == pytest.approx(8.0, abs=0.05)


def test_a_stronger_mix_lowers_the_modular_ratio() -> None:
    assert modular_ratio(6.0) < modular_ratio(3.0)


@pytest.mark.parametrize("fc_ksi", [0.0, -4.0])
def test_a_mix_with_no_strength_is_refused(fc_ksi: float) -> None:
    with pytest.raises(GeometryError, match="not a strength"):
        concrete_modulus_ksi(fc_ksi)


def test_the_creep_width_is_a_third_of_the_short_term_width(deck: DeckSlab) -> None:
    short = deck.transformed_width_in(creep=False)
    long = deck.transformed_width_in(creep=True)
    assert short / long == pytest.approx(CREEP_FACTOR)


def test_the_transformed_width_is_much_narrower_than_the_real_deck(deck: DeckSlab) -> None:
    assert deck.transformed_width_in(creep=False) < deck.effective_width_in / 5.0


def test_gross_area_is_the_untransformed_concrete(deck: DeckSlab) -> None:
    assert deck.gross_area_in2 == pytest.approx(8.0 * 90.0)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"thickness_in": 0.0},
        {"effective_width_in": 0.0},
        {"haunch_in": -1.0},
        {"fc_ksi": 0.0},
    ],
)
def test_a_deck_with_a_bad_dimension_is_refused(kwargs: dict[str, float]) -> None:
    base = {"thickness_in": 8.0, "effective_width_in": 90.0, "haunch_in": 2.0, "fc_ksi": 4.0}
    with pytest.raises(GeometryError):
        DeckSlab(**{**base, **kwargs})


def test_composing_adds_exactly_one_plate(positive_moment_girder: Section, deck: DeckSlab) -> None:
    composed = compose(positive_moment_girder, deck, creep=False)
    assert len(composed) == len(positive_moment_girder) + 1
    assert composed.plate(DECK_LABEL).height_in == pytest.approx(8.0)


def test_the_deck_sits_a_haunch_above_the_steel(
    positive_moment_girder: Section, deck: DeckSlab
) -> None:
    composed = compose(positive_moment_girder, deck, creep=False)
    steel_top = positive_moment_girder.rebased().y_top_in
    assert composed.plate(DECK_LABEL).y_bottom_in == pytest.approx(steel_top + deck.haunch_in)


def test_composing_labels_the_section_with_its_stage(
    positive_moment_girder: Section, deck: DeckSlab
) -> None:
    assert compose(positive_moment_girder, deck, creep=False).label.endswith("+n")
    assert compose(positive_moment_girder, deck, creep=True).label.endswith("+3n")


def test_the_deck_raises_the_neutral_axis(composite_girder: CompositeGirder) -> None:
    bare = composite_girder.noncomposite
    short = composite_girder.short_term
    assert short.centroid_in > bare.centroid_in


def test_creep_leaves_the_axis_lower_than_the_short_term_one(
    composite_girder: CompositeGirder,
) -> None:
    assert composite_girder.long_term.centroid_in < composite_girder.short_term.centroid_in
    assert composite_girder.long_term.centroid_in > composite_girder.noncomposite.centroid_in


def test_stiffness_ranks_the_three_stages(composite_girder: CompositeGirder) -> None:
    bare = composite_girder.noncomposite.inertia_in4
    long = composite_girder.long_term.inertia_in4
    short = composite_girder.short_term.inertia_in4
    assert bare < long < short


def test_the_bottom_modulus_grows_with_every_stage(composite_girder: CompositeGirder) -> None:
    # The bottom flange is the fibre a positive moment rating turns on, and each
    # stage puts more section under it.
    bare = composite_girder.noncomposite.section_modulus_bottom_in3
    long = composite_girder.long_term.section_modulus_bottom_in3
    short = composite_girder.short_term.section_modulus_bottom_in3
    assert bare < long < short


def test_the_short_term_section_is_deeper_by_the_haunch_and_the_slab(
    composite_girder: CompositeGirder,
) -> None:
    bare_depth = composite_girder.noncomposite.depth_in
    composed_depth = composite_girder.short_term.depth_in
    assert composed_depth == pytest.approx(bare_depth + 2.0 + 8.0)


def test_the_steel_top_is_where_the_haunch_starts(composite_girder: CompositeGirder) -> None:
    assert composite_girder.steel_top_in == pytest.approx(composite_girder.noncomposite.y_top_in)


@pytest.mark.parametrize("stage", ["noncomposite", "long_term", "short_term"])
def test_every_named_stage_resolves(composite_girder: CompositeGirder, stage: str) -> None:
    assert composite_girder.stage_section(stage).area_in2 > 0.0


def test_an_unknown_stage_is_refused(composite_girder: CompositeGirder) -> None:
    with pytest.raises(GeometryError, match="unknown load stage"):
        composite_girder.stage_section("cracked")


def test_composing_a_girder_on_a_raised_datum_gives_the_same_properties(
    deck: DeckSlab,
) -> None:
    from shearstud.geometry.plate import flange, web

    raised = Section(
        "raised",
        (
            flange("bottom", width_in=18.0, thickness_in=1.5, y_center_in=200.75),
            web("web", thickness_in=0.5, depth_in=54.0, y_center_in=228.5),
            flange("top", width_in=14.0, thickness_in=1.0, y_center_in=256.0),
        ),
    )
    based = Section(
        "based",
        (
            flange("bottom", width_in=18.0, thickness_in=1.5, y_center_in=0.75),
            web("web", thickness_in=0.5, depth_in=54.0, y_center_in=28.5),
            flange("top", width_in=14.0, thickness_in=1.0, y_center_in=56.0),
        ),
    )
    a = compose(raised, deck, creep=False)
    b = compose(based, deck, creep=False)
    assert a.inertia_in4 == pytest.approx(b.inertia_in4)
    assert a.section_modulus_bottom_in3 == pytest.approx(b.section_modulus_bottom_in3)
