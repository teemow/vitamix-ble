"""Dataclasses for snapshotting the blender state."""

from __future__ import annotations

from dataclasses import dataclass

from .containers import Container


@dataclass(frozen=True)
class VitamixState:
    """A point-in-time snapshot of the blender."""

    motor_running: bool
    """True iff the motor register reports the blade is currently spinning."""

    armed: bool
    """True when the device is on, container detected, ready to start."""

    container: Container | None
    """The currently attached Self-Detect container, if recognised."""

    container_hardware_id: int
    """Raw hardware id from the NFC subsystem (0 = no container)."""

    recipe_slot: int
    """Active program slot (0 = idle, 1..N = saved program loaded)."""

    rated_power_w: int
    """Rated wattage as reported by the firmware (e.g. 1200 W)."""

    max_rpm: int
    """Maximum motor RPM as reported by the firmware (e.g. 12000)."""

    rated_rpm: int
    """Rated continuous motor RPM as reported by the firmware."""
