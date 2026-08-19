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
test_set_mode.py - Manual round-trip test for mode switching and reserve % writes.

Usage:
    python scripts/test_set_mode.py
"""

import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv  # noqa: E402

from franklinwh_local_api import (  # noqa: E402
    FranklinWHLocalClient,
    OperatingMode,
    FranklinWHWriteError,
)


def _print_header(title: str) -> None:
    print("\n" + "=" * 70)
    print(title)
    print("=" * 70)


def _print_status_summary(label: str, status) -> None:
    print(f"[{label}] mode={status.operating_mode.value}  self_reserve_pct={status.self_reserve_pct}  tou_reserve_pct={status.tou_reserve_pct}")


async def switch_and_verify(client, target_mode: OperatingMode) -> bool:
    print(f"\n--> Attempting switch to {target_mode.value}...")
    try:
        await client.async_set_operating_mode(target_mode)
        print(f"    SUCCESS - hardware readback confirms {target_mode.value}.")
        return True
    except FranklinWHWriteError as e:
        print(f"    FAILED (expected if SPAN Modbus write unlock is not yet granted): {e}")
        return False


async def write_reserve_and_report(client, setter_name: str, setter, pct: int) -> None:
    print(f"\n--> Calling {setter_name}({pct}) [plain unconditional write]")
    try:
        await setter(pct)
        print("    SUCCESS - hardware write accepted and verified.")
    except FranklinWHWriteError as e:
        print(f"    Hardware write attempted and REJECTED (expected if SPAN Modbus write unlock is not yet granted): {e}")


async def main():
    env_path = Path(__file__).resolve().parent.parent / ".env"
    load_dotenv(dotenv_path=env_path)

    host = os.getenv("AGATE_IP")
    port = int(os.getenv("AGATE_PORT", "502"))
    unit_id = int(os.getenv("AGATE_UNIT_ID", "0"))
    timeout = float(os.getenv("AGATE_TIMEOUT", "10.0"))

    client = FranklinWHLocalClient(host=host, port=port, unit_id=unit_id, timeout=timeout)
    await client.connect()
    print(f"Connected to aGate at {host}:{port}")

    try:
        _print_header("STEP 1: Read starting state")
        status0 = await client.async_get_status()
        mode0 = status0.operating_mode
        _print_status_summary("BEFORE", status0)

        if mode0 == OperatingMode.TOU:
            mode_b = OperatingMode.SELF_CONSUMPTION
        else:
            mode_b = OperatingMode.TOU

        _print_header(f"STEP 2: Switch {mode0.value} -> {mode_b.value}")
        switched = await switch_and_verify(client, mode_b)
        status1 = await client.async_get_status()
        _print_status_summary("AFTER SWITCH ATTEMPT", status1)

        _print_header("STEP 3: Write both reserve % registers (15508, 15509)")
        test_self_pct = (status1.self_reserve_pct + 5) % 96
        await write_reserve_and_report(client, "async_set_self_reserve_pct", client.async_set_self_reserve_pct, test_self_pct)
        status2 = await client.async_get_status()
        _print_status_summary("AFTER self_reserve_pct WRITE", status2)

        test_tou_pct = (status2.tou_reserve_pct + 7) % 96
        await write_reserve_and_report(client, "async_set_tou_reserve_pct", client.async_set_tou_reserve_pct, test_tou_pct)
        status3 = await client.async_get_status()
        _print_status_summary("AFTER tou_reserve_pct WRITE", status3)
        print(f"\n  NOTE: if self_reserve_pct == tou_reserve_pct == {test_tou_pct} above, that confirms the known firmware defect where 15509 mirrors 15508.")

        _print_header(f"STEP 4: Switch back {mode_b.value} -> {mode0.value}")
        switched_back = await switch_and_verify(client, mode0)
        status4 = await client.async_get_status()
        _print_status_summary("AFTER SWITCH BACK ATTEMPT", status4)

        _print_header("SUMMARY")
        print(f"Mode switch {mode0.value} -> {mode_b.value}: {'OK' if switched else 'FAILED (expected without SPAN unlock)'}")
        print(f"Mode switch {mode_b.value} -> {mode0.value}: {'OK' if switched_back else 'FAILED (expected without SPAN unlock)'}")
        print(f"Ended in mode: {status4.operating_mode.value} (started in {mode0.value})")

    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(main())
