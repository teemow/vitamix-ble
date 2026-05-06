"""Print a snapshot of the blender state.

Usage:

    python examples/read_state.py <BLE-MAC>
"""

from __future__ import annotations

import asyncio
import sys

from vitamix_ble import VitamixClient


async def main(address: str) -> None:
    client = await VitamixClient.from_address(address)
    async with client as vmx:
        state = await vmx.read_state()
    print(f"motor running:  {state.motor_running}")
    print(f"armed/ready:    {state.armed}")
    if state.container is not None:
        print(f"container:      {state.container.name}")
        print(f"  short id:     {state.container.short_name}")
        print(f"  max runtime:  {state.container.max_runtime_s} s")
    else:
        print(f"container:      unknown (hardware id {state.container_hardware_id})")
    print(f"recipe slot:    {state.recipe_slot}")
    print(f"rated power:    {state.rated_power_w} W")
    print(f"max RPM:        {state.max_rpm}")
    print(f"rated RPM:      {state.rated_rpm}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(f"usage: {sys.argv[0]} <BLE-MAC>", file=sys.stderr)
        raise SystemExit(2)
    asyncio.run(main(sys.argv[1]))
