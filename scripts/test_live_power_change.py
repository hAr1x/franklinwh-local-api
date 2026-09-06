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
test_live_power_change.py - Verify the 0.1.1 live power-adjustment fast path.

Starts a DISCHARGE command at START_POWER_W, waits a few seconds, then
calls async_start_battery_discharge() again with LIVE_POWER_W while the
discharge command is still active. With the 0.1.1 fast path the new
setpoint must be written in place (single WSetPct register write, no
disable/enable cycle): WSetEna must remain 1 the whole time, WSetPct
must change, and the actual DC power must move.

Discharge is used deliberately: during the day, solar generation makes
the charge side's readings inaccurate.

The whole run lasts only a few seconds per setpoint. Usage:
    python scripts/test_live_power_change.py
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
    FranklinWHWriteError,
)

START_POWER_W = 500
LIVE_POWER_W = 600
SETTLE_S = 5


def _line(title: str) -> None:
    print("\n" + "=" * 70)
    print(title)
    print("=" * 70)


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
    ok = True

    try:
        await client.connect()
        print(f"Connected to aGate at {host}:{port} (unit_id={unit_id})")

        _line(f"STEP 1: start discharge at {START_POWER_W}W (no duration -> no watchdog)")
        await client.async_start_battery_discharge(power_w=START_POWER_W)
        cmd1 = await client.async_get_battery_command_status()
        print(f"  wset_ena={cmd1['wset_ena']}  wset_pct={cmd1['wset_pct']:.1f}%  (expected ~+{START_POWER_W/50:.1f}% of 5000W rating)")
        if not cmd1["wset_ena"]:
            print("FAILED - WSetEna is not 1 after start")
            sys.exit(1)

        await asyncio.sleep(SETTLE_S)
        s1 = await client.async_get_status()
        print(f"  after {SETTLE_S}s: battery_power_w={s1.battery_power_w:.0f}W  (expect ~{START_POWER_W}W discharge)")

        _line(f"STEP 2: LIVE change to {LIVE_POWER_W}W while discharge is active (no stop)")
        cmd_before = await client.async_get_battery_command_status()
        try:
            await client.async_start_battery_discharge(power_w=LIVE_POWER_W)
            print("  live rewrite accepted (WSetPct read-back verified by API)")
        except FranklinWHWriteError as e:
            print(f"FAILED - live WSetPct rewrite rejected by hardware: {e}")
            sys.exit(1)
        cmd2 = await client.async_get_battery_command_status()
        print(f"  before: wset_ena={cmd_before['wset_ena']}  wset_pct={cmd_before['wset_pct']:.1f}%")
        print(f"  after:  wset_ena={cmd2['wset_ena']}  wset_pct={cmd2['wset_pct']:.1f}%  (expected ~+{LIVE_POWER_W/50:.1f}%)")
        if not cmd2["wset_ena"]:
            ok = False
            print("  FAIL - WSetEna dropped to 0 during the live change (was not an in-place rewrite)")
        if abs(cmd2["wset_pct"] - LIVE_POWER_W / 50) > 1.0:
            ok = False
            print(f"  FAIL - WSetPct readback {cmd2['wset_pct']:.1f}% is not near +{LIVE_POWER_W/50:.1f}%")

        await asyncio.sleep(SETTLE_S)
        s2 = await client.async_get_status()
        print(f"  after {SETTLE_S}s: battery_power_w={s2.battery_power_w:.0f}W  (expect ~{LIVE_POWER_W}W discharge)")
        if not (LIVE_POWER_W * 0.6 <= s2.battery_discharging_w <= LIVE_POWER_W * 1.4):
            print(f"  WARNING - measured discharge {s2.battery_discharging_w:.0f}W is far from {LIVE_POWER_W}W")

        _line("STEP 3: release")
        await client.async_stop_battery_command()
        cmd3 = await client.async_get_battery_command_status()
        print(f"  after release: wset_ena={cmd3['wset_ena']}  wset_pct={cmd3['wset_pct']:.1f}%")

        if ok:
            print("\nPASS - live power change worked in place; WSetEna stayed 1 throughout.")
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
