"""Async :class:`VitamixClient` — a thin wrapper around :mod:`bleak`.

Exchanges are correlated by sequencing them: only one outstanding
request per connection, so the next notify is always the response.
That matches the firmware behaviour we observed (no asynchronous
push-notifications in normal operation; the official app polls).
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from types import TracebackType
from typing import Self

from bleak import BleakClient, BleakScanner
from bleak.backends.device import BLEDevice

from .const import (
    CUSTOM_PROGRAM_MAX_STEPS,
    DEFAULT_MTU,
    MAX_SPEED,
    MAX_STEP_SECONDS,
    MIN_SPEED,
    NOTIFY_CHARACTERISTIC_UUID,
    REG_CUSTOM_PROGRAM_BASE,
    REG_MOTOR_MAX_RPM,
    REG_MOTOR_RATED_W,
    REG_MOTOR_RUN,
    REG_NFC_HARDWARE,
    REG_PANEL_ARMED,
    REG_PROGRAM_FLAG,
    REG_RECIPE,
    SLAVE_CPANEL,
    WRITE_CHARACTERISTIC_UUID,
)
from .containers import lookup_container
from .models import VitamixState
from .protocol import (
    PacketStatus,
    ProtocolError,
    decode_read_response,
    decode_write_response,
    encode_read,
    encode_write,
)

_LOGGER = logging.getLogger(__name__)


DEFAULT_REQUEST_TIMEOUT = 2.0
DEFAULT_SCAN_TIMEOUT = 30.0
DEFAULT_CONNECT_TIMEOUT = 30.0


class VitamixError(RuntimeError):
    """Base class for vitamix-ble runtime errors."""


class VitamixTimeoutError(VitamixError):
    """Raised when a request does not produce a response in time."""


class VitamixWriteRejectedError(VitamixError):
    """Raised when the firmware returns a non-zero status for a write."""

    def __init__(self, status: PacketStatus) -> None:
        super().__init__(f"write rejected, status=0x{status.code:02x}")
        self.status = status


class VitamixClient:
    """High-level async client for a single Vitamix blender."""

    def __init__(
        self,
        ble_device: BLEDevice | str,
        *,
        slave: int = SLAVE_CPANEL,
        request_timeout: float = DEFAULT_REQUEST_TIMEOUT,
        connect_timeout: float = DEFAULT_CONNECT_TIMEOUT,
    ) -> None:
        self._ble_device = ble_device
        self._slave = slave
        self._request_timeout = request_timeout
        self._connect_timeout = connect_timeout
        self._client: BleakClient | None = None
        self._lock = asyncio.Lock()
        self._notifications: asyncio.Queue[bytes] = asyncio.Queue()

    # -- construction ------------------------------------------------------

    @classmethod
    async def from_address(
        cls,
        address: str,
        *,
        scan_timeout: float = DEFAULT_SCAN_TIMEOUT,
        **kwargs: object,
    ) -> Self:
        """Resolve ``address`` into a BLEDevice via a fresh scan, then return a client.

        On Linux/BlueZ the underlying scan can take a while because Vitamix
        blenders advertise sparingly while idle. Callers that already have a
        cached :class:`BLEDevice` should pass it to ``__init__`` directly.
        """
        device = await BleakScanner.find_device_by_address(
            address, timeout=scan_timeout
        )
        if device is None:
            # Fall back to direct connect by address: BlueZ will use its
            # own cache if the device is known.
            return cls(address, **kwargs)  # type: ignore[arg-type]
        return cls(device, **kwargs)  # type: ignore[arg-type]

    # -- async context-manager protocol ------------------------------------

    async def __aenter__(self) -> Self:
        await self.connect()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.disconnect()

    async def connect(self) -> None:
        """Open the BLE connection and subscribe to notifications."""
        if self._client is not None and self._client.is_connected:
            return
        self._client = BleakClient(
            self._ble_device, timeout=self._connect_timeout
        )
        await self._client.__aenter__()
        await self._client.start_notify(
            NOTIFY_CHARACTERISTIC_UUID, self._on_notify
        )
        # Give the device a moment to settle before the first request.
        await asyncio.sleep(0.1)

    async def disconnect(self) -> None:
        """Stop notifications and close the BLE connection."""
        if self._client is None:
            return
        try:
            with contextlib.suppress(Exception):
                # bleak best-effort; some backends raise on stop_notify after
                # the device has already disconnected.
                await self._client.stop_notify(NOTIFY_CHARACTERISTIC_UUID)
            await self._client.__aexit__(None, None, None)
        finally:
            self._client = None

    @property
    def is_connected(self) -> bool:
        return self._client is not None and self._client.is_connected

    # -- low-level register IO ---------------------------------------------

    async def read_registers(self, register: int, count: int = 1) -> list[int]:
        """Read ``count`` consecutive 16-bit registers starting at ``register``."""
        client = self._require_client()
        request = encode_read(register, count, slave=self._slave)
        async with self._lock:
            self._drain_notifications()
            await client.write_gatt_char(
                WRITE_CHARACTERISTIC_UUID, request, response=True
            )
            response = await self._wait_notification()
        try:
            values, _status = decode_read_response(response, count)
        except ProtocolError as exc:
            raise VitamixError(
                f"could not parse read response {response.hex()}: {exc}"
            ) from exc
        return values

    async def read_register(self, register: int) -> int:
        """Convenience: read a single register and return its value."""
        return (await self.read_registers(register, 1))[0]

    async def write_registers(
        self, register: int, values: list[int] | tuple[int, ...]
    ) -> PacketStatus:
        """Write one or more 16-bit values starting at ``register``.

        Raises:
            VitamixWriteRejected: if the firmware returned a non-zero status
                code (Modbus-style exception).
        """
        client = self._require_client()
        request = encode_write(register, values, slave=self._slave)
        async with self._lock:
            self._drain_notifications()
            await client.write_gatt_char(
                WRITE_CHARACTERISTIC_UUID, request, response=True
            )
            response = await self._wait_notification()
        status = decode_write_response(response)
        if not status.ok:
            raise VitamixWriteRejectedError(status)
        return status

    async def write_register(self, register: int, value: int) -> PacketStatus:
        """Convenience wrapper around :meth:`write_registers`."""
        return await self.write_registers(register, [value])

    # -- high-level helpers -------------------------------------------------

    async def read_state(self) -> VitamixState:
        """Read enough registers to reconstruct a :class:`VitamixState`."""
        motor_run = await self.read_register(REG_MOTOR_RUN)
        max_rpm, rated_rpm = (await self.read_registers(REG_MOTOR_MAX_RPM, 2))[0:2]
        rated_w = await self.read_register(REG_MOTOR_RATED_W)
        recipe = await self.read_register(REG_RECIPE)
        armed = await self.read_register(REG_PANEL_ARMED)
        nfc = await self.read_registers(REG_NFC_HARDWARE, 2)
        container_hw = nfc[0]
        return VitamixState(
            motor_running=bool(motor_run),
            armed=bool(armed),
            container=lookup_container(container_hw),
            container_hardware_id=container_hw,
            recipe_slot=recipe,
            rated_power_w=rated_w,
            max_rpm=max_rpm,
            rated_rpm=rated_rpm,
        )

    async def cancel_program(self) -> PacketStatus:
        """Send the official "cancel current program" command.

        This is the same packet the Vitamix Perfect Blend app emits in
        ``cancelCurrentProgram`` for C-panel devices. Idempotent if the
        device is already idle.
        """
        return await self.write_register(REG_RECIPE, 0)

    async def load_program(self, slot: int) -> PacketStatus:
        """Arm a saved program slot.

        The Ascent / Venturist series ships with several factory program
        slots (Smoothie, Frozen Dessert, Spreads…). Writing the slot
        number to register :data:`REG_RECIPE` is the same primitive the
        Perfect Blend app's ``setBlenderProgram`` uses as the very last
        step after staging the program-step buffer.

        For built-in saved programs the staging is unnecessary because
        the firmware already has them, so this single write is enough to
        select the slot.

        Whether the motor *also* spins immediately depends on whether
        the user has the dial in an "armed" position (see
        :data:`REG_PANEL_ARMED`). On an idle / un-armed device the slot
        is just primed; the user still has to physically engage Start.

        Args:
            slot: 1-indexed saved-program slot. ``0`` is reserved for
                "no program" — use :meth:`cancel_program` for that to
                make intent explicit.

        Raises:
            ValueError: if ``slot`` is not strictly positive.
            VitamixWriteRejectedError: if the firmware rejects the
                write (e.g. invalid slot number for this model).
        """
        if slot <= 0:
            raise ValueError(
                f"slot must be >= 1; use cancel_program() for slot 0 (got {slot})"
            )
        return await self.write_register(REG_RECIPE, slot)

    # -- custom-program / motor control (0.3.0+) ----------------------------
    #
    # The Ascent C-panel exposes a 12-u16 "scratch" program buffer at
    # registers 0x0201..0x020C and fires the staged buffer when a bitmask
    # is written to register 0x3483 (REG_PROGRAM_FLAG). Each step is a
    # (speed, time) pair, so we can build anything from a single
    # constant-speed run to a 6-step recipe by uploading the buffer and
    # then writing ``1 << (step_count - 1)`` to REG_PROGRAM_FLAG.
    #
    # Speed values use the same 0..10 dial scale the firmware exposes on
    # its physical interface; time values are in seconds.

    async def upload_custom_program(
        self,
        steps: list[tuple[int, int]] | tuple[tuple[int, int], ...],
    ) -> None:
        """Stage a custom program of up to 6 (speed, time) steps.

        This writes the step buffer to registers 0x0201.. but does NOT
        start the program — call :meth:`commit_custom_program` (or one of
        the higher-level helpers like :meth:`set_motor_speed`) afterwards
        to fire it.

        Args:
            steps: list of ``(speed, seconds)`` tuples. ``speed`` must be
                in the range 0..10 (Vitamix variable-speed dial). 0 stops
                the motor; 10 is full speed. ``seconds`` is a u16 timer
                (max ``0xFFFF`` ≈ 18h, used as "run forever" sentinel).

        Raises:
            ValueError: if ``steps`` is empty, contains too many entries,
                or has speed/time values outside the supported range.
        """
        self._validate_steps(steps)
        # Flatten into the wire layout: [speed_0, time_0, speed_1, ...].
        payload: list[int] = []
        for speed, seconds in steps:
            payload.append(speed)
            payload.append(seconds)
        # The full block is 12 u16s on the wire — pad unused slots with
        # zeros so the firmware sees a deterministic state and old data
        # from a previous program can't leak into the next run.
        while len(payload) < CUSTOM_PROGRAM_MAX_STEPS * 2:
            payload.append(0)
        # Default MTU only fits 9 u16s per write packet; chunk the upload.
        # The firmware disassembly shows the official app issues one
        # write per u16, but writing in MTU-sized batches is faster and
        # equivalent on the wire.
        batch = (DEFAULT_MTU - 5) // 2
        for offset in range(0, len(payload), batch):
            slice_ = payload[offset : offset + batch]
            await self.write_registers(
                REG_CUSTOM_PROGRAM_BASE + offset, slice_
            )

    async def commit_custom_program(self, step_count: int) -> PacketStatus:
        """Fire the staged custom program.

        Writes ``1 << (step_count - 1)`` to :data:`REG_PROGRAM_FLAG`. The
        firmware uses the bitmask both as a "go" trigger and as the
        step-count signal, mirroring the official app's panel-2 path.

        Args:
            step_count: must match the number of populated steps from the
                preceding :meth:`upload_custom_program` call.

        Raises:
            ValueError: if ``step_count`` is not in 1..6.
        """
        if not 1 <= step_count <= CUSTOM_PROGRAM_MAX_STEPS:
            raise ValueError(
                f"step_count must be 1..{CUSTOM_PROGRAM_MAX_STEPS} "
                f"(got {step_count})"
            )
        bitmask = 1 << (step_count - 1)
        return await self.write_register(REG_PROGRAM_FLAG, bitmask)

    async def run_custom_program(
        self,
        steps: list[tuple[int, int]] | tuple[tuple[int, int], ...],
    ) -> PacketStatus:
        """Upload + commit a custom program in one shot.

        Equivalent to::

            await self.upload_custom_program(steps)
            await self.commit_custom_program(len(steps))
        """
        self._validate_steps(steps)
        await self.upload_custom_program(steps)
        return await self.commit_custom_program(len(steps))

    async def set_motor_speed(
        self,
        speed: int,
        *,
        duration_seconds: int = MAX_STEP_SECONDS,
    ) -> PacketStatus:
        """Run the motor at ``speed`` for up to ``duration_seconds``.

        Internally this stages and fires a 1-step custom program. Calling
        :meth:`set_motor_speed` again while the motor is already running
        re-stages the buffer with the new speed and refires it — that's
        the protocol-level mechanism we use for live speed changes
        (0.3.0) and for melody playback (0.5.0).

        Args:
            speed: 0..10. ``0`` stops the motor (use :meth:`stop_motor`
                for that to make intent explicit; this method delegates).
            duration_seconds: u16 seconds. Defaults to the firmware
                "run forever" sentinel ``0xFFFF`` so you can call
                :meth:`stop_motor` at your leisure.

        Raises:
            ValueError: if ``speed`` is out of range.
        """
        if speed == 0:
            return await self.cancel_program()
        if not MIN_SPEED <= speed <= MAX_SPEED:
            raise ValueError(
                f"speed must be {MIN_SPEED}..{MAX_SPEED} (got {speed})"
            )
        if not 0 < duration_seconds <= MAX_STEP_SECONDS:
            raise ValueError(
                f"duration_seconds must be 1..{MAX_STEP_SECONDS} "
                f"(got {duration_seconds})"
            )
        return await self.run_custom_program([(speed, duration_seconds)])

    @staticmethod
    def _validate_steps(
        steps: list[tuple[int, int]] | tuple[tuple[int, int], ...],
    ) -> None:
        if not steps:
            raise ValueError("steps must not be empty")
        if len(steps) > CUSTOM_PROGRAM_MAX_STEPS:
            raise ValueError(
                f"at most {CUSTOM_PROGRAM_MAX_STEPS} steps supported "
                f"(got {len(steps)})"
            )
        for index, (speed, seconds) in enumerate(steps):
            if not MIN_SPEED <= speed <= MAX_SPEED:
                raise ValueError(
                    f"step {index}: speed must be {MIN_SPEED}..{MAX_SPEED} "
                    f"(got {speed})"
                )
            if not 0 <= seconds <= MAX_STEP_SECONDS:
                raise ValueError(
                    f"step {index}: time must be 0..{MAX_STEP_SECONDS} "
                    f"(got {seconds})"
                )

    # -- internals ----------------------------------------------------------

    def _require_client(self) -> BleakClient:
        if self._client is None or not self._client.is_connected:
            raise VitamixError("client is not connected")
        return self._client

    def _on_notify(self, _handle: int, data: bytearray) -> None:
        # Bleak calls this from a background task; queue.put_nowait is safe
        # because the queue is unbounded.
        self._notifications.put_nowait(bytes(data))

    def _drain_notifications(self) -> None:
        while True:
            try:
                self._notifications.get_nowait()
            except asyncio.QueueEmpty:
                return

    async def _wait_notification(self) -> bytes:
        try:
            return await asyncio.wait_for(
                self._notifications.get(), timeout=self._request_timeout
            )
        except TimeoutError as exc:
            raise VitamixTimeoutError(
                f"no response within {self._request_timeout}s"
            ) from exc


@asynccontextmanager
async def open_vitamix(
    address: str,
    **kwargs: object,
) -> AsyncIterator[VitamixClient]:
    """Convenience: ``async with open_vitamix(addr) as vmx:``."""
    client = await VitamixClient.from_address(address, **kwargs)  # type: ignore[arg-type]
    async with client as connected:
        yield connected
