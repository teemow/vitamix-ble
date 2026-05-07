"""Async Python library for Vitamix Bluetooth Low Energy blenders.

Speaks the proprietary register-mapped BLE protocol of Vitamix
Ascent and Venturist series blenders (e.g. A2300/A2500/A3300/A3500,
Venturist 330/350) — the ones with the "Self-Detect" containers
and the Vitamix Perfect Blend companion app.

This is a clean-room, observation-based implementation. Reads are
non-destructive; writes are exposed only as the high-level commands
that the official app actually uses.

Quick start:

    import asyncio
    from vitamix_ble import VitamixClient

    async def main() -> None:
        async with VitamixClient.from_address("C9:FF:B3:03:1F:DF") as vmx:
            state = await vmx.read_state()
            print(state)

    asyncio.run(main())
"""

from .client import VitamixClient
from .const import (
    NOTIFY_CHARACTERISTIC_UUID,
    SERVICE_UUID,
    SLAVE_BPANEL,
    SLAVE_CPANEL,
    WRITE_CHARACTERISTIC_UUID,
)
from .containers import CONTAINERS, Container, lookup_container
from .models import VitamixState
from .protocol import (
    PacketStatus,
    decode_read_response,
    decode_write_response,
    encode_read,
    encode_write,
)

__version__ = "0.3.0"

__all__ = [
    "CONTAINERS",
    "NOTIFY_CHARACTERISTIC_UUID",
    "SERVICE_UUID",
    "SLAVE_BPANEL",
    "SLAVE_CPANEL",
    "WRITE_CHARACTERISTIC_UUID",
    "Container",
    "PacketStatus",
    "VitamixClient",
    "VitamixState",
    "decode_read_response",
    "decode_write_response",
    "encode_read",
    "encode_write",
    "lookup_container",
]
