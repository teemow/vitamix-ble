"""Vitamix Self-Detect container hardware-id mappings.

The C-panel firmware reports the attached container as a 16-bit
hardware identifier on register 0x3480 (count=2). The first value is
the hardware id; the second appears to be a sub-variant or container-
present flag. Only the hardware-id is documented here.

The mapping was extracted from the official Vitamix Perfect Blend
Android app's bundled SQLite database (``assets/db/development.sqlite3``,
``containers`` table, ``hardware_info`` YAML field).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final


@dataclass(frozen=True)
class Container:
    """One Self-Detect container variant."""

    hardware_id: int
    name: str
    short_name: str
    max_runtime_s: int
    blend_supported: bool = True
    inverted: bool = False  #: device is meant to be flipped upside down
    typical_weight_g: int | None = None


CONTAINERS: Final[dict[int, Container]] = {
    1: Container(
        hardware_id=1,
        name="Vitamix 64 oz Blender Jar with Self-Detect",
        short_name="64oz_jar",
        max_runtime_s=390,
        typical_weight_g=1249,
    ),
    2: Container(
        hardware_id=2,
        # 20 oz and 8 oz personal cups share the same hardware-id;
        # the firmware can't tell them apart.
        name="Vitamix 20 oz / 8 oz Personal Blender Cup",
        short_name="personal_cup",
        max_runtime_s=75,
        inverted=True,
        typical_weight_g=355,
    ),
    3: Container(
        hardware_id=3,
        name="Vitamix 48 oz Wet Container with Self-Detect",
        short_name="48oz_wet",
        max_runtime_s=450,
        typical_weight_g=1200,
    ),
    4: Container(
        hardware_id=4,
        name="Vitamix 48 oz Dry Container with Self-Detect",
        short_name="48oz_dry",
        max_runtime_s=150,
        typical_weight_g=1200,
    ),
    5: Container(
        hardware_id=5,
        name="Vitamix Food Processor with Self-Detect",
        short_name="food_processor",
        max_runtime_s=150,
        blend_supported=False,
        typical_weight_g=1200,
    ),
}


def lookup_container(hardware_id: int) -> Container | None:
    """Return the :class:`Container` for ``hardware_id`` or ``None``."""
    return CONTAINERS.get(hardware_id)
