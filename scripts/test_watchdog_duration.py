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
test_watchdog_duration.py - Verify the 0.1.1 watchdog behavior.

Two quick scenarios (a few seconds each):

  A. start a discharge command with duration_s=WATCHDOG_S passed to the
     start call itself; it must auto-release ~WATCHDOG_S later.

  B. start a discharge command with NO duration, then call the public
     client.arm_watchdog(WATCHDOG_S) (the exact call the Home Assistant
     integration will make to re-arm after a restart); the command must
     auto-release ~WATCHDOG_S later. Also verifies disarm_watchdog()
     cancels a pending watchdog without touching the command.

The whole run lasts only a few seconds per scenario. Usage:
    python scripts/test_watchdog_duration.py
"""

import asyncio
import logging
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

from franklinwh_local_api import (
    FranklinWHConnectionError,
    FranklinWHLocalClient,
)

POWER_W = 300
WATCHDOG_S = 5
CHECK_AFTER_S = 9  # > WATCHDOG_S, still short


def _line(title: str) -> None:
    print("\n" + "=" * 70)
    print(title)
    print("=" * 70)


async def _wait_and_check(client, label: str) -> bool:
    """Wait for the watchdog to fire and report whether the command was
    auto-released."""
    print(f"  waiting {CHECK_AFTER_S}s for the watchdog to auto-release...")
    await asyncio.sleep(CHECK_AFTER_S)
    cmd = await client.async_get_battery_command_status()
    print(f"  [{label}] after wait: wset_ena={cmd['wset_ena']}  wset_pct={cmd['wset_pct']:.1f}%")
    if cmd["wset_ena"]:
        print("  FAIL - watchdog did NOT auto-release the command")
        return False
    print(f"  PASS - [{label}] command auto-released by watchdog")
    return True


async def main() -> None:
    env_path = Path(__file__).resolve().parent.parent / ".env"
    load_dotenv(dotenv_path=env_path)

    host = os.getenv("AGATE_IP")
    if not host:
        print("ERROR: AGATE_IP not set in .env")
        sys.exit(1)
    port = int(os.getenv("AGATE_PORT", "502"))
    unit_id = int(os.getenv("AGATE_UNIT_ID", "0"))
    timeout = float(os.getenv("AGATE_TIMEOUT", "10.0"))

    client = FranklinWHLocalClient(host=host, port=port, unit_id=unit_id, timeout=timeout)

    try:
        await client.connect()
        print(f"Connected to aGate at {host}:{port} (unit_id={unit_id})")

        # -------------------------------------------------------------
        _line(f"SCENARIO A: start discharge {POWER_W}W with duration_s={WATCHDOG_S}")
        await client.async_start_battery_discharge(power_w=POWER_W, duration_s=WATCHDOG_S)
        cmd = await client.async_get_battery_command_status()
        print(f"  immediately after start: wset_ena={cmd['wset_ena']}  wset_pct={cmd['wset_pct']:.1f}%")
        ok_a = await _wait_and_check(client, "A")

        # -------------------------------------------------------------
        _line(f"SCENARIO B: start discharge {POWER_W}W (no duration) + public arm_watchdog({WATCHDOG_S})")
        await client.async_start_battery_discharge(power_w=POWER_W)
        cmd = await client.async_get_battery_command_status()
        print(f"  immediately after start: wset_ena={cmd['wset_ena']}  wset_pct={cmd['wset_pct']:.1f}%")
        client.arm_watchdog(WATCHDOG_S)
        print(f"  arm_watchdog({WATCHDOG_S}) called (public API, the HA re-arm path)")
        ok_b = await _wait_and_check(client, "B")

        # -------------------------------------------------------------
        _line("SCENARIO C: disarm_watchdog() cancels a pending watchdog")
        await client.async_start_battery_discharge(power_w=POWER_W)
        client.arm_watchdog(2)  # would fire in 2s if not disarmed
        await asyncio.sleep(0.5)
        client.disarm_watchdog()
        await asyncio.sleep(3)  # longer than the 2s watchdog
        cmd = await client.async_get_battery_command_status()
        print(f"  after 3s (watchdog was 2s, disarmed): wset_ena={cmd['wset_ena']}  wset_pct={cmd['wset_pct']:.1f}%")
        if not cmd["wset_ena"]:
            print("  FAIL - command was released although the watchdog was disarmed")
        else:
            print("  PASS - disarmed watchdog did not release the command")
            await client.async_stop_battery_command()

        if ok_a and ok_b:
            print("\nPASS - watchdog behaves as expected in both scenarios.")
        else:
            print("\nFAIL - see FAIL lines above.")
            sys.exit(1)

    except FranklinWHConnectionError as e:
        print(f"CONNECTION ERROR: {e}")
        sys.exit(1)
    finally:
        if client.is_connected:
            try:
                await client.async_stop_battery_command(handshake_wait_s=0)
            except FranklinWHConnectionError:
                pass
        await client.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
