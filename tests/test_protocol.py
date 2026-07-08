"""Unit tests for the pure-Python protocol layer."""

from __future__ import annotations

import pytest

from vitamix_ble.protocol import (
    PacketStatus,
    ProtocolError,
    decode_read_response,
    decode_write_response,
    encode_read,
    encode_write,
)


class TestEncodeRead:
    def test_single_register(self) -> None:
        assert encode_read(0x0200, 1) == bytes.fromhex("0267020001")

    def test_multi_register(self) -> None:
        # NFC read at 0x3480, count=2
        assert encode_read(0x3480, 2) == bytes.fromhex("0267348002")

    def test_explicit_slave(self) -> None:
        assert encode_read(0x3201, 1, slave=0x02) == bytes.fromhex("0202320101")

    def test_register_address_is_big_endian(self) -> None:
        encoded = encode_read(0x1234, 1)
        assert encoded[2] == 0x12, "high byte first"
        assert encoded[3] == 0x34

    def test_invalid_register_rejected(self) -> None:
        with pytest.raises(ValueError):
            encode_read(0x10000, 1)
        with pytest.raises(ValueError):
            encode_read(-1, 1)

    def test_invalid_count_rejected(self) -> None:
        with pytest.raises(ValueError):
            encode_read(0x0100, 0)
        with pytest.raises(ValueError):
            encode_read(0x0100, 100)


class TestEncodeWrite:
    def test_cancel_program_packet(self) -> None:
        # The exact packet the official app sends in cancelCurrentProgram
        # (case C-panel): write 0x0000 to register 0x0200.
        assert encode_write(0x0200, [0x0000]) == bytes.fromhex("01670200010000")

    def test_load_program_slot_packet(self) -> None:
        # load_program(slot=2) must produce: fn=01, slave=67, reg=0200,
        # count=01, value=0002 (little-endian).
        assert encode_write(0x0200, [0x0002]) == bytes.fromhex("01670200010200")

    def test_value_is_little_endian(self) -> None:
        encoded = encode_write(0x3406, [0x4321])
        # header...               value bytes follow
        assert encoded[5] == 0x21, "low byte of value first"
        assert encoded[6] == 0x43

    def test_multi_value(self) -> None:
        encoded = encode_write(0x3406, [0x0001, 0x0002, 0x0003])
        assert encoded[:5] == bytes([0x01, 0x67, 0x34, 0x06, 0x03])
        assert encoded[5:] == bytes([0x01, 0x00, 0x02, 0x00, 0x03, 0x00])

    def test_empty_values_rejected(self) -> None:
        with pytest.raises(ValueError):
            encode_write(0x0200, [])

    def test_value_out_of_range_rejected(self) -> None:
        with pytest.raises(ValueError):
            encode_write(0x0200, [0x10000])
        with pytest.raises(ValueError):
            encode_write(0x0200, [-1])


class TestDecodeReadResponse:
    def test_motor_running(self) -> None:
        # Live capture: motor=running response at register 0x0100
        values, status = decode_read_response(bytes.fromhex("02000100"), 1)
        assert values == [1]
        assert status == 0x00

    def test_motor_constants(self) -> None:
        # Live capture: 4 registers from 0x010A read together
        values, status = decode_read_response(bytes.fromhex("0200e02e881300000000"), 4)
        assert values == [12000, 5000, 0, 0]
        assert status == 0x00

    def test_endianness_round_trip(self) -> None:
        # Live capture from the endianness probe: wrote 0x4321, read back 0x4321
        values, _ = decode_read_response(bytes.fromhex("02002143"), 1)
        assert values == [0x4321]

    def test_truncated_response_rejected(self) -> None:
        with pytest.raises(ProtocolError):
            decode_read_response(b"", 1)
        with pytest.raises(ProtocolError):
            decode_read_response(bytes.fromhex("0200"), 1)

    def test_wrong_function_code_rejected(self) -> None:
        with pytest.raises(ProtocolError):
            decode_read_response(bytes.fromhex("01000100"), 1)


class TestDecodeWriteResponse:
    def test_success(self) -> None:
        status = decode_write_response(b"\x00")
        assert isinstance(status, PacketStatus)
        assert status.ok is True
        assert status.code == 0x00

    def test_exception_code(self) -> None:
        status = decode_write_response(b"\x0a")
        assert status.ok is False
        assert status.code == 0x0A
        assert status.is_exception is True

    def test_empty_response_rejected(self) -> None:
        with pytest.raises(ProtocolError):
            decode_write_response(b"")
