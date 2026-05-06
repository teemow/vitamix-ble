"""Pure-Python encoder / decoder for the Vitamix BLE wire protocol.

Wire format
-----------

All multi-byte fields are big-endian for the **register address** and
little-endian for **values**. Every packet sits inside a single GATT
Write or Notify event (no fragmentation).

Read request (5 bytes)::

    [0x02] [slave] [reg_hi] [reg_lo] [count]

Read response (2 + 2*count bytes)::

    [0x02] [status] [val0_lo] [val0_hi] [val1_lo] [val1_hi] ...

The ``status`` byte is 0x00 in the idle state. While the motor is
running, it carries a live ticking byte that we currently treat as
opaque (a sequence counter or live status indicator).

Write request (5 + 2*count bytes)::

    [0x01] [slave] [reg_hi] [reg_lo] [count] [val0_lo] [val0_hi] ...

Write response (1 byte)::

    [status]      0x00 = success ACK; non-zero = exception code

Slave 0x67 is the C-panel (Ascent / Venturist), 0x02 is the older
B-panel.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from .const import FN_READ, FN_WRITE, MAX_REGISTERS_PER_PACKET, SLAVE_CPANEL

__all__ = [
    "PacketStatus",
    "ProtocolError",
    "decode_read_response",
    "decode_write_response",
    "encode_read",
    "encode_write",
]


_HEADER_BYTES: Final = 5


class ProtocolError(ValueError):
    """Raised when a received packet violates the wire format."""


@dataclass(frozen=True)
class PacketStatus:
    """Outcome of a single request/response exchange."""

    ok: bool
    code: int  #: raw status / exception byte
    raw: bytes  #: full response payload as received

    @property
    def is_exception(self) -> bool:
        return not self.ok


# ---------------------------------------------------------------------------
# Encoders
# ---------------------------------------------------------------------------


def encode_read(register: int, count: int = 1, slave: int = SLAVE_CPANEL) -> bytes:
    """Build a read-registers request packet.

    Args:
        register: First register address (0..0xFFFF).
        count: Number of consecutive 16-bit registers to read.
        slave: Bus slave address (defaults to the C-panel).

    Returns:
        Raw packet bytes ready to write to the GATT write characteristic.
    """
    _check_register(register)
    _check_count(count)
    _check_byte(slave, "slave")
    return bytes(
        [
            FN_READ,
            slave,
            (register >> 8) & 0xFF,
            register & 0xFF,
            count,
        ]
    )


def encode_write(
    register: int,
    values: list[int] | tuple[int, ...],
    slave: int = SLAVE_CPANEL,
) -> bytes:
    """Build a write-registers request packet.

    Args:
        register: First register address (0..0xFFFF).
        values: 16-bit values to write into ``register``, ``register+1``, …
        slave: Bus slave address (defaults to the C-panel).

    Returns:
        Raw packet bytes ready to write to the GATT write characteristic.

    Raises:
        ValueError: if any value is outside ``0..0xFFFF`` or the packet
            would exceed the device MTU.
    """
    _check_register(register)
    _check_byte(slave, "slave")
    if not values:
        raise ValueError("values must contain at least one register")
    count = len(values)
    _check_count(count)

    pkt = bytearray(
        [
            FN_WRITE,
            slave,
            (register >> 8) & 0xFF,
            register & 0xFF,
            count,
        ]
    )
    for index, value in enumerate(values):
        if not 0 <= value <= 0xFFFF:
            raise ValueError(
                f"values[{index}] = {value!r} is not a valid u16",
            )
        pkt.append(value & 0xFF)            # low byte first (little-endian)
        pkt.append((value >> 8) & 0xFF)
    return bytes(pkt)


# ---------------------------------------------------------------------------
# Decoders
# ---------------------------------------------------------------------------


def decode_read_response(data: bytes, expected_count: int) -> tuple[list[int], int]:
    """Decode a notify payload received in response to a read request.

    Args:
        data: Raw notify payload.
        expected_count: Number of u16 registers that were requested.

    Returns:
        ``(values, status)``: the decoded register values (little-endian,
        in request order) and the leading status byte.

    Raises:
        ProtocolError: if the payload is malformed.
    """
    if len(data) < 2:
        raise ProtocolError(f"response too short ({len(data)} bytes)")
    if data[0] != FN_READ:
        raise ProtocolError(
            f"unexpected function code 0x{data[0]:02x} (want 0x{FN_READ:02x})",
        )
    status = data[1]
    body = data[2:]
    needed = expected_count * 2
    if len(body) < needed:
        raise ProtocolError(
            f"truncated response: got {len(body)} value bytes, want {needed}",
        )
    values = [body[2 * i] | (body[2 * i + 1] << 8) for i in range(expected_count)]
    return values, status


def decode_write_response(data: bytes) -> PacketStatus:
    """Decode a notify payload received in response to a write request.

    The device sends a single status byte: ``0x00`` on success, otherwise
    an exception code (Modbus-style). The status is returned as-is so
    callers can distinguish success from device-side errors.
    """
    if not data:
        raise ProtocolError("empty write response")
    code = data[0]
    return PacketStatus(ok=code == 0x00, code=code, raw=bytes(data))


# ---------------------------------------------------------------------------
# Internal validation helpers
# ---------------------------------------------------------------------------


def _check_register(register: int) -> None:
    if not 0 <= register <= 0xFFFF:
        raise ValueError(f"register 0x{register:x} out of range")


def _check_count(count: int) -> None:
    if not 1 <= count <= MAX_REGISTERS_PER_PACKET:
        raise ValueError(
            f"count {count} out of range (1..{MAX_REGISTERS_PER_PACKET})",
        )


def _check_byte(value: int, name: str) -> None:
    if not 0 <= value <= 0xFF:
        raise ValueError(f"{name} 0x{value:x} is not an 8-bit value")
