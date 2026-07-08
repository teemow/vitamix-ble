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

SLAVE_BPANEL: Final = 0x02  # older "B-panel" interface
SLAVE_CPANEL: Final = 0x67  # Ascent / Venturist "C-panel" interface


# ---------------------------------------------------------------------------
# Known register addresses (all on slave 0x67 unless noted).
# ---------------------------------------------------------------------------

# Motor block (telemetry + device specs).
REG_MOTOR_RUN: Final = 0x0100  # u16: 0 = stopped, 1 = running
REG_MOTOR_RPM_LIVE: Final = 0x0101  # u16: live blade RPM (jittery)
REG_MOTOR_MAX_RPM: Final = 0x010A  # u16: rated max RPM (firmware constant)
REG_MOTOR_RATED_RPM: Final = 0x010B  # u16: rated continuous RPM
REG_MOTOR_MAX_PERCENT: Final = 0x0111  # u16: 100
REG_MOTOR_RATED_W: Final = 0x0113  # u16: rated wattage in watts

# Recipe / program-arm.
REG_RECIPE: Final = 0x0200  # u16: 0 = idle/cancel, 1..N = saved program slot

# Custom-program "step" buffer (Ascent C-panel, panel-type 2).
# The Perfect Blend app's ``setBlenderProgram`` panel-2 path writes one
# u16 per consecutive register starting at 0x0201, then triggers the
# upload by writing a bitmask to :data:`REG_PROGRAM_FLAG`. Each step is
# encoded as a (speed, time) pair, so:
#
#     0x0201  step 0 speed       0x0202  step 0 time
#     0x0203  step 1 speed       0x0204  step 1 time
#     ...
#
# A maximum of 6 steps fit in the 12-u16 buffer (0x0201..0x020C).
REG_CUSTOM_PROGRAM_BASE: Final = 0x0201  # first u16 of the step buffer
CUSTOM_PROGRAM_MAX_STEPS: Final = 6  # 12 u16s ÷ 2 (speed,time) = 6 steps

# Panel / UI block.
REG_PANEL_ARMED: Final = 0x347F  # u16: 1 when device is ready / start-armed
REG_NFC_HARDWARE: Final = 0x3480  # u16 x 2: container hardware identifier
REG_PANEL_3481: Final = 0x3481  # u16: container-related, often equal to REG_NFC_HARDWARE
REG_PANEL_3482: Final = 0x3482  # u16: container variant or sub-type

# Program-load registers (used by the official app's setBlenderProgram).
# Writing to REG_RECIPE with a non-zero slot value arms a saved program;
# the device then waits for a physical "Start" press to spin the blade.
# REG_PROGRAM_FLAG is the panel-2 "fire" register: writing a bitmask
# ``1 << (step_count - 1)`` finalises and starts the previously-uploaded
# custom program in 0x0201..0x020C.
REG_PROGRAM_FLAG: Final = 0x3483  # u16: bitmask, fires the staged custom program
REG_PROGRAM_STEP_BASE_PANEL3: Final = 0x3406  # u16 x N: panel-type-3 step buffer
REG_PROGRAM_LOAD_CMD: Final = 0x3404  # u16: panel-3 "begin load"
REG_PROGRAM_READY: Final = 0x3405  # u16: panel-3 program-ready flag

# Speed / time encoding for custom-program steps. Vitamix dials run from
# 1 ("Variable 1", lowest) to 10 ("Variable 10", highest); 0 means "off".
# The firmware accepts those values verbatim in the speed slot.
MIN_SPEED: Final = 0  # 0 = motor off
MAX_SPEED: Final = 10  # full speed (Variable 10 / High)

# Time slot is u16 seconds. 0xFFFF = ~18h, used as "run forever" sentinel.
MAX_STEP_SECONDS: Final = 0xFFFF


# ---------------------------------------------------------------------------
# Limits derived from disassembly + wire observation.
# ---------------------------------------------------------------------------

# Maximum number of u16 values that can fit in a single read or write
# request given the default 23-byte MTU.
MAX_REGISTERS_PER_PACKET: Final = (DEFAULT_MTU - 5) // 2  # = 9
