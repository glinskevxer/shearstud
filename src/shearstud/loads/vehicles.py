"""The vehicle catalogue: design, legal, specialized hauling and emergency.

Each vehicle is in a class, and the class decides which load factor it is rated
with and what a failing rating means. A design vehicle failing is a design
check. A legal vehicle failing is a posting. An emergency vehicle failing is a
conversation with the fire district. Keeping the class on the vehicle rather
than on the call site is what stops those three getting mixed up in a report.

The design lane load is not a vehicle and is not in here. It is a uniform load
and lives with the influence line arithmetic that applies it.
"""

from __future__ import annotations

import functools
from typing import Final

from shearstud.errors import ConfigError
from shearstud.loads.axles import AxleTrain, train

#: Vehicle classes, in the order a rating report lists them.
CLASS_DESIGN: Final[str] = "design"
CLASS_LEGAL: Final[str] = "legal"
CLASS_SHV: Final[str] = "shv"
CLASS_EMERGENCY: Final[str] = "emergency"
CLASSES: Final[tuple[str, ...]] = (CLASS_DESIGN, CLASS_LEGAL, CLASS_SHV, CLASS_EMERGENCY)

#: Uniform lane load that rides with the design truck, kips per foot of lane.
DESIGN_LANE_KLF: Final[float] = 0.64

#: The rear axle gap on the design truck is variable between these two, and the
#: analysis has to try both because the wide one governs negative moment over a
#: pier while the tight one governs everything else.
DESIGN_REAR_GAP_MIN_FT: Final[float] = 14.0
DESIGN_REAR_GAP_MAX_FT: Final[float] = 30.0

#: The design truck's axles, LRFD 3.6.1.2.2: a light steer axle and two equal
#: drive axles. Written out here rather than in the function because the fixed
#: front gap is a specified number and the rear one is not, and having them in
#: two different places is how the wrong one gets varied.
DESIGN_STEER_KIP: Final[float] = 8.0
DESIGN_DRIVE_KIP: Final[float] = 32.0
DESIGN_FRONT_GAP_FT: Final[float] = 14.0

_DEFINITIONS: Final[dict[str, tuple[str, list[float], list[float]]]] = {
    "HL93-TRUCK": (CLASS_DESIGN, [8.0, 32.0, 32.0], [14.0, 14.0]),
    "HL93-TANDEM": (CLASS_DESIGN, [25.0, 25.0], [4.0]),
    "TYPE3": (CLASS_LEGAL, [16.0, 17.0, 17.0], [15.0, 4.0]),
    "TYPE3S2": (CLASS_LEGAL, [10.0, 15.5, 15.5, 15.5, 15.5], [11.0, 4.0, 22.0, 4.0]),
    "TYPE3-3": (CLASS_LEGAL, [12.0, 12.0, 12.0, 16.0, 14.0, 14.0], [15.0, 4.0, 15.0, 16.0, 4.0]),
    "NRL": (CLASS_LEGAL, [12.0, 12.0, 12.0, 17.0, 17.0, 10.0], [6.0, 14.0, 4.0, 6.0, 6.0]),
    "SU4": (CLASS_SHV, [12.0, 8.0, 17.0, 17.0], [10.0, 4.0, 4.0]),
    "SU5": (CLASS_SHV, [12.0, 8.0, 8.0, 17.0, 17.0], [10.0, 4.0, 4.0, 4.0]),
    "SU6": (CLASS_SHV, [11.5, 10.0, 10.0, 16.0, 11.0, 11.0], [10.0, 4.0, 4.0, 6.0, 4.0]),
    "SU7": (
        CLASS_SHV,
        [11.5, 10.0, 10.0, 16.0, 10.0, 10.0, 10.0],
        [10.0, 4.0, 4.0, 6.0, 4.0, 4.0],
    ),
    "EV2": (CLASS_EMERGENCY, [24.0, 33.5], [15.0]),
    "EV3": (CLASS_EMERGENCY, [24.0, 31.0, 31.0], [15.0, 4.0]),
}


def _key(name: str) -> str:
    """Normalise a catalogue name, or say which one was not found.

    Normalisation happens here rather than inside the cached builder, because a
    cache keyed on the raw string hands back a different object for every way of
    spelling the same vehicle.
    """
    key = name.strip().upper()
    if key not in _DEFINITIONS:
        raise ConfigError(f"unknown vehicle {name!r}")
    return key


@functools.cache
def _build(key: str) -> AxleTrain:
    _, weights_kip, spacings_ft = _DEFINITIONS[key]
    return train(key, weights_kip, spacings_ft)


def vehicle(name: str) -> AxleTrain:
    """One catalogue vehicle by name, case insensitive."""
    return _build(_key(name))


def vehicle_class(name: str) -> str:
    """Which class a catalogue vehicle is in."""
    return _DEFINITIONS[_key(name)][0]


def names(vehicle_class_name: str | None = None) -> list[str]:
    """Catalogue names, optionally filtered to one class."""
    if vehicle_class_name is None:
        return list(_DEFINITIONS)
    if vehicle_class_name not in CLASSES:
        raise ConfigError(f"unknown vehicle class {vehicle_class_name!r}")
    return [k for k, v in _DEFINITIONS.items() if v[0] == vehicle_class_name]


def design_truck(rear_gap_ft: float = DESIGN_REAR_GAP_MIN_FT) -> AxleTrain:
    """The design truck with its rear axle gap set.

    The gap is variable by specification, and the two ends of its range govern
    different load effects, so it is a parameter rather than a constant.
    """
    if not DESIGN_REAR_GAP_MIN_FT <= rear_gap_ft <= DESIGN_REAR_GAP_MAX_FT:
        raise ConfigError(
            f"rear axle gap {rear_gap_ft} ft is outside "
            f"{DESIGN_REAR_GAP_MIN_FT} to {DESIGN_REAR_GAP_MAX_FT}"
        )
    return train(
        "HL93-TRUCK",
        [DESIGN_STEER_KIP, DESIGN_DRIVE_KIP, DESIGN_DRIVE_KIP],
        [DESIGN_FRONT_GAP_FT, rear_gap_ft],
    )


def legal_fleet() -> list[AxleTrain]:
    """Every legal and specialized hauling vehicle, which is what a posting
    analysis has to clear before the structure stays open to all of them."""
    wanted = names(CLASS_LEGAL) + names(CLASS_SHV)
    return [vehicle(name) for name in wanted]
