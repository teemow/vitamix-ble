"""Light-weight unit tests for :class:`VitamixClient` helpers that do
not require a real BLE stack.

We avoid mocking ``bleak`` here; instead we test only behaviour that is
purely Python (input validation, default routing of high-level helpers
to the right register) by inspecting what would have been encoded.
"""

from __future__ import annotations

import pytest

from vitamix_ble.client import VitamixClient
from vitamix_ble.const import REG_RECIPE
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
