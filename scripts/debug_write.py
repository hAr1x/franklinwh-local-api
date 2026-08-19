#!/usr/bin/env python3
# Copyright (C) 2026 Harry Xue
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

"""
debug_write.py - Low-level Modbus write debugging for register 15507.

Tries writing to the OnGridMode register directly, inspecting the raw
pymodbus response object, and tries a few different unit_ids.

Usage:
    python scripts/debug_write.py
"""

import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv  # noqa: E402
from pymodbus.client import AsyncModbusTcpClient  # noqa: E402


async def try_write(host, port, unit_id, address, value, timeout):
    client = AsyncModbusTcpClient(host=host, port=port, timeout=timeout)
    connected = await client.connect()
    print(f"\n--- unit_id={unit_id} ---")
    print(f"Connected: {connected}")
    if not connected:
        return

    read_before = await client.read_holding_registers(address=address, count=1, device_id=unit_id)
    print(f"Read before: isError={read_before.isError()}, registers={getattr(read_before, 'registers', None)}, raw={read_before}")

    write_result = await client.write_register(address=address, value=value, device_id=unit_id)
    print(f"Write result: isError={write_result.isError()}, raw={write_result}")
    print(f"Write result type: {type(write_result)}")
    if hasattr(write_result, 'exception_code'):
        print(f"Exception code: {write_result.exception_code}")
    if hasattr(write_result, 'function_code'):
        print(f"Function code: {write_result.function_code}")

    await asyncio.sleep(1.0)

    read_after = await client.read_holding_registers(address=address, count=1, device_id=unit_id)
    print(f"Read after (1s): isError={read_after.isError()}, registers={getattr(read_after, 'registers', None)}")

    await asyncio.sleep(2.0)
    read_after2 = await client.read_holding_registers(address=address, count=1, device_id=unit_id)
    print(f"Read after (+2s more): isError={read_after2.isError()}, registers={getattr(read_after2, 'registers', None)}")

    client.close()


async def main():
    env_path = Path(__file__).resolve().parent.parent / ".env"
    load_dotenv(dotenv_path=env_path)

    host = os.getenv("AGATE_IP")
    port = int(os.getenv("AGATE_PORT", "502"))
    timeout = float(os.getenv("AGATE_TIMEOUT", "10.0"))

    address = 15507  # OnGridMode
    value = 3  # TOU

    for unit_id in [0, 1, 2]:
        await try_write(host, port, unit_id, address, value, timeout)


if __name__ == "__main__":
    asyncio.run(main())
