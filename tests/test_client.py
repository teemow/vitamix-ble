"""Light-weight unit tests for :class:`VitamixClient` helpers that do
not require a real BLE stack.

We avoid mocking ``bleak`` here; instead we test only behaviour that is
purely Python (input validation, default routing of high-level helpers
to the right register) by inspecting what would have been encoded.
"""

from __future__ import annotations

import pytest

from vitamix_ble.client import VitamixClient
from vitamix_ble.const import (
    CUSTOM_PROGRAM_MAX_STEPS,
    MAX_STEP_SECONDS,
    REG_CUSTOM_PROGRAM_BASE,
    REG_PROGRAM_FLAG,
    REG_RECIPE,
)
from vitamix_ble.protocol import encode_write


class TestLoadProgramSlotValidation:
    """``load_program`` is the only public helper with input rules."""

    async def test_zero_rejected(self) -> None:
        # Slot 0 is reserved for "no program" — callers must use
        # cancel_program() to make intent unambiguous.
        client = VitamixClient.__new__(VitamixClient)
        with pytest.raises(ValueError, match="cancel_program"):
            await client.load_program(0)

    async def test_negative_rejected(self) -> None:
        client = VitamixClient.__new__(VitamixClient)
        with pytest.raises(ValueError):
            await client.load_program(-1)


class TestProgramSlotPackets:
    """Sanity-check the wire packets we'll send for each saved slot."""

    @pytest.mark.parametrize("slot", [1, 2, 3])
    def test_slot_packet_writes_to_recipe_register(self, slot: int) -> None:
        # load_program(slot=N) is exactly: write [N] to REG_RECIPE.
        packet = encode_write(REG_RECIPE, [slot])
        # Header: fn=01, slave=67, reg_hi=02, reg_lo=00, count=01.
        assert packet[:5] == bytes([0x01, 0x67, 0x02, 0x00, 0x01])
        # Value: low byte first (little-endian).
        assert packet[5] == slot
        assert packet[6] == 0x00


class TestCustomProgramValidation:
    """``upload_custom_program`` must reject malformed step lists."""

    async def test_empty_steps_rejected(self) -> None:
        client = VitamixClient.__new__(VitamixClient)
        with pytest.raises(ValueError, match="must not be empty"):
            await client.upload_custom_program([])

    async def test_too_many_steps_rejected(self) -> None:
        client = VitamixClient.__new__(VitamixClient)
        steps = [(1, 1)] * (CUSTOM_PROGRAM_MAX_STEPS + 1)
        with pytest.raises(ValueError, match="at most"):
            await client.upload_custom_program(steps)

    @pytest.mark.parametrize("speed", [-1, 11, 99])
    async def test_speed_out_of_range_rejected(self, speed: int) -> None:
        client = VitamixClient.__new__(VitamixClient)
        with pytest.raises(ValueError, match="speed"):
            await client.upload_custom_program([(speed, 5)])

    async def test_negative_time_rejected(self) -> None:
        client = VitamixClient.__new__(VitamixClient)
        with pytest.raises(ValueError, match="time"):
            await client.upload_custom_program([(5, -1)])


class TestCommitCustomProgramValidation:
    @pytest.mark.parametrize("count", [0, -1, CUSTOM_PROGRAM_MAX_STEPS + 1])
    async def test_step_count_out_of_range(self, count: int) -> None:
        client = VitamixClient.__new__(VitamixClient)
        with pytest.raises(ValueError, match="step_count"):
            await client.commit_custom_program(count)


class TestSetMotorSpeedValidation:
    @pytest.mark.parametrize("speed", [-1, 11])
    async def test_out_of_range(self, speed: int) -> None:
        client = VitamixClient.__new__(VitamixClient)
        with pytest.raises(ValueError, match="speed"):
            await client.set_motor_speed(speed)

    @pytest.mark.parametrize("duration", [0, -5, MAX_STEP_SECONDS + 1])
    async def test_invalid_duration(self, duration: int) -> None:
        client = VitamixClient.__new__(VitamixClient)
        with pytest.raises(ValueError, match="duration"):
            await client.set_motor_speed(5, duration_seconds=duration)


class TestCustomProgramPackets:
    """Concrete wire packets for the staged-program upload + fire path.

    These are exactly what the firmware disassembly's panel-2 path of
    ``setBlenderProgram`` emits, so any mismatch here is a regression we
    want to catch before we ever touch the BLE stack.
    """

    def test_step_buffer_starts_at_0x0201(self) -> None:
        # Step 0 lives at REG_CUSTOM_PROGRAM_BASE.
        assert REG_CUSTOM_PROGRAM_BASE == 0x0201

    def test_single_step_speed_then_time(self) -> None:
        # A 1-step program (speed=5, time=60) is two consecutive u16
        # words at register 0x0201 — speed first, then time.
        packet = encode_write(REG_CUSTOM_PROGRAM_BASE, [5, 60])
        # Header: fn=01, slave=67, reg_hi=02, reg_lo=01, count=02.
        assert packet[:5] == bytes([0x01, 0x67, 0x02, 0x01, 0x02])
        # Speed (LE) — 5 fits in low byte.
        assert packet[5:7] == bytes([0x05, 0x00])
        # Time (LE) — 60.
        assert packet[7:9] == bytes([0x3C, 0x00])

    @pytest.mark.parametrize(
        "step_count,bitmask",
        [(1, 0x01), (2, 0x02), (3, 0x04), (4, 0x08), (5, 0x10), (6, 0x20)],
    )
    def test_commit_bitmask_matches_step_count(
        self, step_count: int, bitmask: int
    ) -> None:
        # The "fire" packet is a single u16 = (1 << (step_count - 1))
        # written to REG_PROGRAM_FLAG (0x3483).
        packet = encode_write(REG_PROGRAM_FLAG, [bitmask])
        assert packet[:5] == bytes([0x01, 0x67, 0x34, 0x83, 0x01])
        assert packet[5:7] == bitmask.to_bytes(2, "little")
        assert (1 << (step_count - 1)) == bitmask
