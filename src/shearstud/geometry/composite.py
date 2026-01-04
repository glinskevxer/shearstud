"""Transformed composite sections, and the three stage stress stack.

A composite girder is not one section. It is three, and which one carries a
given load depends on when that load arrived:

* steel alone carries its own weight and the wet deck, because there is nothing
  else there yet;
* the long term composite section carries the barrier, the future wearing
  surface and anything else permanent, with the concrete softened by a factor
  of three for creep;
* the short term composite section carries live load, which comes and goes too
  fast for the concrete to creep.

Stresses from the three add. Nothing in this package ever computes a composite
stress by applying every load to one section, and ``check_layers`` will not let
a caller reach past this module to do it.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Final

from shearstud.errors import GeometryError
from shearstud.geometry.plate import Plate
from shearstud.geometry.section import Section
from shearstud.units import STEEL_E_KSI

#: Creep factor on the concrete for sustained load, AASHTO 6.10.1.1.1b.
CREEP_FACTOR: Final[float] = 3.0

#: Coefficient in the elastic modulus expression when f'c is in ksi. This is
#: 57000 sqrt(f'c in psi) rewritten, and it is the form the old rating sheets
#: for this inventory were worked in.
CONCRETE_MODULUS_COEFF: Final[float] = 1820.0

#: Label the deck plate carries in every transformed section. Callers look the
#: deck up by this name to get its transformed width back.
DECK_LABEL: Final[str] = "deck"


def concrete_modulus_ksi(fc_ksi: float) -> float:
    """Elastic modulus of normal weight concrete from its cylinder strength."""
    if fc_ksi <= 0.0:
        raise GeometryError(f"concrete strength {fc_ksi} is not a strength")
    return CONCRETE_MODULUS_COEFF * math.sqrt(fc_ksi)


def modular_ratio(fc_ksi: float) -> float:
    """Steel modulus over concrete modulus, unrounded.

    Old sheets rounded this to an integer from a table. The unrounded value is
    used here and the difference is under two percent on every mix in this
    inventory, which is smaller than the spread in the cylinder breaks.
    """
    return STEEL_E_KSI / concrete_modulus_ksi(fc_ksi)


@dataclass(frozen=True, slots=True)
class DeckSlab:
    """The concrete deck as it bears on one girder.

    ``effective_width_in`` is already the tributary width for this girder, not
    the full deck width. Working that out is the job of the effective width
    rules, and doing it here would hide the assumption inside the arithmetic.
    """

    thickness_in: float
    effective_width_in: float
    haunch_in: float
    fc_ksi: float

    def __post_init__(self) -> None:
        if self.thickness_in <= 0.0:
            raise GeometryError(f"deck thickness {self.thickness_in} is not a thickness")
        if self.effective_width_in <= 0.0:
            raise GeometryError(f"effective width {self.effective_width_in} is not a width")
        if self.haunch_in < 0.0:
            raise GeometryError("haunch cannot be negative")
        if self.fc_ksi <= 0.0:
            raise GeometryError(f"concrete strength {self.fc_ksi} is not a strength")

    @property
    def gross_area_in2(self) -> float:
        """Untransformed concrete area, which no section property uses but a
        dead load calculation does."""
        return self.thickness_in * self.effective_width_in

    def transformed_width_in(self, *, creep: bool) -> float:
        """Effective width divided by n, or by 3n when the load is sustained."""
        n = modular_ratio(self.fc_ksi)
        divisor = CREEP_FACTOR * n if creep else n
        return self.effective_width_in / divisor


def compose(steel: Section, deck: DeckSlab, *, creep: bool) -> Section:
    """Add the transformed deck to a steel section.

    The steel section is rebased first, so the returned section is measured from
    the bottom of the bottom flange whatever datum the caller was working in.
    """
    base = steel.rebased()
    deck_bottom_in = base.y_top_in + deck.haunch_in
    slab = Plate(
        DECK_LABEL,
        width_in=deck.transformed_width_in(creep=creep),
        height_in=deck.thickness_in,
        y_center_in=deck_bottom_in + deck.thickness_in / 2.0,
    )
    suffix = "3n" if creep else "n"
    return Section(f"{base.label}+{suffix}", (*base.plates, slab))


@dataclass(frozen=True, slots=True)
class CompositeGirder:
    """The three sections a composite girder is rated with."""

    steel: Section
    deck: DeckSlab

    @property
    def noncomposite(self) -> Section:
        """Steel alone, based at the bottom flange."""
        return self.steel.rebased()

    @property
    def long_term(self) -> Section:
        """Composite with the deck softened by the creep factor."""
        return compose(self.steel, self.deck, creep=True)

    @property
    def short_term(self) -> Section:
        """Composite at the full modular ratio, for live load."""
        return compose(self.steel, self.deck, creep=False)

    @property
    def steel_top_in(self) -> float:
        """Datum height of the top of the steel, where the haunch starts."""
        return self.noncomposite.y_top_in

    def stage_section(self, stage: str) -> Section:
        """Section for a named load stage.

        The three names are the ones the load tables use, so a caller reading a
        stage out of a file can hand it straight in.
        """
        if stage == "noncomposite":
            return self.noncomposite
        if stage == "long_term":
            return self.long_term
        if stage == "short_term":
            return self.short_term
        raise GeometryError(f"unknown load stage {stage!r}")
