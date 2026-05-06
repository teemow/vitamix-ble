"""Constants for the Vitamix BLE protocol.

All values were derived by observing the live wire protocol and from
disassembly of the official Vitamix Perfect Blend Android app's native
``libcore.so`` (``VitamixBLEBlender`` class).
"""

from __future__ import annotations

from typing import Final

# ---------------------------------------------------------------------------
# GATT
# ---------------------------------------------------------------------------

SERVICE_UUID: Final = "4a310001-cf3c-4cb9-bed6-2ea871b8d070"
WRITE_CHARACTERISTIC_UUID: Final = "4a310002-cf3c-4cb9-bed6-2ea871b8d070"
NOTIFY_CHARACTERISTIC_UUID: Final = "4a310003-cf3c-4cb9-bed6-2ea871b8d070"

# Local-name advertised by the device.
ADV_LOCAL_NAME: Final = "Vitamix_2.0"

# Default MTU used by the firmware.
DEFAULT_MTU: Final = 23


# ---------------------------------------------------------------------------
# Wire protocol — function codes (object offsets 0x200/0x201 in libcore.so).
# ---------------------------------------------------------------------------

FN_READ: Final = 0x02
FN_WRITE: Final = 0x01

# Single-byte ACK returned after a successful write.
WRITE_ACK_OK: Final = 0x00


# ---------------------------------------------------------------------------
# Slave addresses — there are multiple sub-devices on the internal bus.
# ---------------------------------------------------------------------------

SLAVE_BPANEL: Final = 0x02   # older "B-panel" interface
SLAVE_CPANEL: Final = 0x67   # Ascent / Venturist "C-panel" interface


# ---------------------------------------------------------------------------
# Known register addresses (all on slave 0x67 unless noted).
# ---------------------------------------------------------------------------

# Motor block (telemetry + device specs).
REG_MOTOR_RUN: Final = 0x0100      # u16: 0 = stopped, 1 = running
REG_MOTOR_RPM_LIVE: Final = 0x0101  # u16: live blade RPM (jittery)
REG_MOTOR_MAX_RPM: Final = 0x010A  # u16: rated max RPM (firmware constant)
REG_MOTOR_RATED_RPM: Final = 0x010B  # u16: rated continuous RPM
REG_MOTOR_MAX_PERCENT: Final = 0x0111  # u16: 100
REG_MOTOR_RATED_W: Final = 0x0113  # u16: rated wattage in watts

# Recipe / program-arm.
REG_RECIPE: Final = 0x0200          # u16: 0 = idle/cancel, 1..N = saved program slot

# Panel / UI block.
REG_PANEL_ARMED: Final = 0x347F     # u16: 1 when device is ready / start-armed
REG_NFC_HARDWARE: Final = 0x3480    # u16 x 2: container hardware identifier
REG_PANEL_3481: Final = 0x3481      # u16: container-related, often equal to REG_NFC_HARDWARE
REG_PANEL_3482: Final = 0x3482      # u16: container variant or sub-type

# Program-load registers (used by the official app's setBlenderProgram).
# Writing to REG_RECIPE with a non-zero slot value arms a saved program;
# the device then waits for a physical "Start" press to spin the blade.
REG_PROGRAM_FLAG: Final = 0x3483    # u16: bitmask of program slot to load
REG_PROGRAM_STEP_BASE: Final = 0x3406  # u16 x N: program step buffer
REG_PROGRAM_LOAD_CMD: Final = 0x3404   # u16: 1 = "begin load"
REG_PROGRAM_READY: Final = 0x3405      # u16: program-ready flag


# ---------------------------------------------------------------------------
# Limits derived from disassembly + wire observation.
# ---------------------------------------------------------------------------

# Maximum number of u16 values that can fit in a single read or write
# request given the default 23-byte MTU.
MAX_REGISTERS_PER_PACKET: Final = (DEFAULT_MTU - 5) // 2  # = 9
