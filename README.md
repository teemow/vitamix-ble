# vitamix-ble

[![PyPI - Python Version](https://img.shields.io/pypi/pyversions/vitamix-ble.svg)](https://pypi.org/project/vitamix-ble/)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

Async Python library for talking to Bluetooth-enabled Vitamix blenders
(Ascent A2300 / A2500 / A3300 / A3500 and Venturist 330 / 350 — the
"Self-Detect" generation).

The library implements the proprietary register-mapped BLE protocol that
the official *Vitamix Perfect Blend* app uses, derived from clean-room
observation of the wire and offline analysis of the app's bundled native
library.

> [!IMPORTANT]
> This is an **unofficial** project. It is not endorsed by, affiliated
> with, or supported by Vita-Mix Corporation. Use at your own risk.
> Writes that arm a saved program slot can cause the blade to spin if
> the user subsequently presses Start, so keep your hands clear.

## Status

- Read protocol: **fully working** (validated on a live A3500-class device)
- Write protocol: **fully working** for the cancel-program command and
  for round-tripping arbitrary register values; higher-level program
  authoring is a work in progress
- Tested on Linux/BlueZ via [bleak](https://github.com/hbldh/bleak)

## Install

```bash
pip install vitamix-ble
```

Python 3.11+ is required.

## Quick start

```python
import asyncio
from vitamix_ble import VitamixClient

async def main() -> None:
    client = await VitamixClient.from_address("AA:BB:CC:DD:EE:FF")
    async with client as vmx:
        state = await vmx.read_state()
        print(state)

asyncio.run(main())
```

Output (idle blender, 64 oz wet jar attached):

```
VitamixState(motor_running=False, armed=True,
             container=Container(hardware_id=1, name='Vitamix 64 oz Blender Jar with Self-Detect', ...),
             container_hardware_id=1, recipe_slot=0,
             rated_power_w=1200, max_rpm=12000, rated_rpm=5000)
```

## What you can read

The blender exposes a register space that includes:

| Register | Meaning |
|----------|---------|
| `0x0100` | Motor run flag (0/1) |
| `0x0101` | Live blade RPM (jittery — sampled at high rate) |
| `0x010A` | Max motor RPM (firmware constant, e.g. `12000`) |
| `0x010B` | Rated continuous RPM (e.g. `5000`) |
| `0x0111` | Max %                                          |
| `0x0113` | Rated wattage (e.g. `1200` W)                  |
| `0x0200` | Active program slot (`0` = idle)               |
| `0x347F` | "Armed/ready" flag                             |
| `0x3480` | Container hardware id (Self-Detect NFC)        |

See `vitamix_ble.const` for the full list and `vitamix_ble.containers`
for the hardware-id → name mapping (extracted from the official app's
bundled SQLite database).

## What you can do

The official app's commands are exposed as high-level methods. Today:

- `await vmx.cancel_program()` — sends the canonical "cancel current
  program" packet (writes `0x0000` to register `0x0200`). Idempotent on
  an idle device.
- `await vmx.read_registers(reg, count)` and `await vmx.write_registers(reg, values)`
  — low-level escape hatches.

## Wire protocol

```
read  request  : [0x02] [slave] [reg_hi] [reg_lo] [count]
read  response : [0x02] [status] [val0_lo] [val0_hi] ...           (LE values)
write request  : [0x01] [slave] [reg_hi] [reg_lo] [count] [val0_lo] [val0_hi] ...
write response : [status]                                          (0x00 = ACK)
```

- Register addresses are **big-endian** in requests.
- Values are **little-endian** in both directions.
- Slave `0x67` is the C-panel (Ascent / Venturist); `0x02` is the older B-panel.

## Hacking on it

```bash
git clone https://github.com/teemow/vitamix-ble
cd vitamix-ble
python -m venv .venv && source .venv/bin/activate
pip install -e .[dev]
pytest
```

## Related

- [hass-vitamix](https://github.com/teemow/hass-vitamix) — Home Assistant
  custom component built on top of this library.

## License

MIT — see [LICENSE](LICENSE).
