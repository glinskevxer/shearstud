"""Axle trains: the vehicles that get driven across an influence line.

A vehicle here is a list of axle loads and the gaps between them, nose to tail,
with the first axle at the front. Nothing about tyres, tandems as a unit, or
lateral position lives here; a tandem is two axles four feet apart, because that
is what the influence line sees.

Directionality matters and is easy to get wrong. A truck driven backwards over
an unsymmetric influence line gives a different answer, so ``reversed_train``
exists and the traversal routines use it rather than each caller reversing the
list themselves and getting the spacings off by one.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from typing import Final

from shearstud.errors import InputError

#: An axle lighter than this is a lift axle carrying nothing, and including it
#: only moves the reference point.
MIN_AXLE_KIP: Final[float] = 0.1

#: Two axles closer than this are one axle as far as any span in this inventory
#: is concerned.
MIN_SPACING_FT: Final[float] = 1.0


@dataclass(frozen=True, slots=True)
class Axle:
    """One axle: its load, and how far it trails the axle in front of it.

    The lead axle carries ``spacing_ft`` of zero. That is the only axle allowed
    to, and the constructor enforces it through :class:`AxleTrain` rather than
    here, because an axle on its own does not know whether it leads.
    """

    weight_kip: float
    spacing_ft: float

    def __post_init__(self) -> None:
        if self.weight_kip < MIN_AXLE_KIP:
            raise InputError(f"axle weight {self.weight_kip} kip is not an axle")
        if self.spacing_ft < 0.0:
            raise InputError(f"axle spacing {self.spacing_ft} ft is negative")


@dataclass(frozen=True, slots=True)
class AxleTrain:
    """A vehicle as the analysis sees it."""

    name: str
    axles: tuple[Axle, ...]

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise InputError("a vehicle needs a name")
        if not self.axles:
            raise InputError(f"{self.name}: a vehicle needs at least one axle")
        if self.axles[0].spacing_ft != 0.0:
            raise InputError(f"{self.name}: the lead axle cannot trail anything")
        for position, axle in enumerate(self.axles[1:], start=1):
            if axle.spacing_ft < MIN_SPACING_FT:
                raise InputError(
                    f"{self.name}: axle {position + 1} is {axle.spacing_ft} ft "
                    f"behind axle {position}, closer than one axle"
                )

    def __iter__(self) -> Iterator[Axle]:
        return iter(self.axles)

    def __len__(self) -> int:
        return len(self.axles)

    @property
    def axle_count(self) -> int:
        """How many axles the vehicle has."""
        return len(self.axles)

    @property
    def gross_kip(self) -> float:
        """Gross vehicle weight."""
        return sum(axle.weight_kip for axle in self.axles)

    @property
    def length_ft(self) -> float:
        """Lead axle to rear axle. Overhangs are not part of a load model."""
        return sum(axle.spacing_ft for axle in self.axles)

    @property
    def offsets_ft(self) -> tuple[float, ...]:
        """Distance of each axle behind the lead axle."""
        out: list[float] = []
        running_ft = 0.0
        for axle in self.axles:
            running_ft += axle.spacing_ft
            out.append(running_ft)
        return tuple(out)

    @property
    def weights_kip(self) -> tuple[float, ...]:
        """Axle loads in order, front to back."""
        return tuple(axle.weight_kip for axle in self.axles)

    @property
    def heaviest_axle_kip(self) -> float:
        """The single worst axle, which is what a deck check turns on."""
        return max(axle.weight_kip for axle in self.axles)

    def reversed_train(self) -> AxleTrain:
        """The same vehicle driven the other way.

        Spacings have to be rebuilt rather than reversed, because a spacing
        belongs to the gap in front of an axle and reversing the list moves
        every gap onto the wrong axle.
        """
        gaps_ft = [axle.spacing_ft for axle in self.axles[1:]]
        weights = list(reversed(self.weights_kip))
        spacings_ft = [0.0, *reversed(gaps_ft)]
        axles = tuple(
            Axle(weight_kip=w, spacing_ft=s) for w, s in zip(weights, spacings_ft, strict=True)
        )
        return AxleTrain(f"{self.name} reversed", axles)

    def scaled(self, factor: float, name: str | None = None) -> AxleTrain:
        """The same geometry at a different gross weight.

        Permit vehicles are often the legal vehicle at a higher weight with the
        axle spacings unchanged, and posting analysis walks a vehicle down in
        weight until it rates.
        """
        if factor <= 0.0:
            raise InputError(f"scale factor {factor} is not positive")
        axles = tuple(
            Axle(weight_kip=axle.weight_kip * factor, spacing_ft=axle.spacing_ft)
            for axle in self.axles
        )
        return AxleTrain(name or f"{self.name} at {factor:.2f}", axles)


def train(name: str, weights_kip: Sequence[float], spacings_ft: Sequence[float]) -> AxleTrain:
    """Build a train from n weights and the n minus 1 gaps between them."""
    if len(spacings_ft) != len(weights_kip) - 1:
        raise InputError(
            f"{name}: {len(weights_kip)} axles need {len(weights_kip) - 1} spacings, "
            f"got {len(spacings_ft)}"
        )
    axles = tuple(
        Axle(weight_kip=w, spacing_ft=s)
        for w, s in zip(weights_kip, [0.0, *spacings_ft], strict=True)
    )
    return AxleTrain(name, axles)
