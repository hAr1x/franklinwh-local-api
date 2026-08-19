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
test_battery_discharge.py - Verification test for async_start_battery_discharge().

Mirror of test_battery_charge.py, testing battery DISCHARGE instead of charge.

Usage:
    python scripts/test_battery_discharge.py
"""

import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv  # noqa: E402

from franklinwh_local_api import (  # noqa: E402
    FranklinWHLocalClient,
    FranklinWHConnectionError,
    FranklinWHWriteError,
)

TEST_POWER_W = 500
OBSERVE_DURATION_S = 30
TEST_DURATION_S = 90
OBSERVE_WAIT_S = 5


def _line(title: str = None) -> None:
    print("\n" + "=" * 70)
    if title:
        print(title)
        print("=" * 70)


def _print_status_summary(label: str, status) -> None:
    print(f"[{label}]")
    print(f"  mode:                 {status.operating_mode.value}")
    print(f"  battery_power_w:      {status.battery_power_w:.1f} W")
    print(f"  battery_charging_w:   {status.battery_charging_w:.1f} W")
    print(f"  battery_discharging_w:{status.battery_discharging_w:.1f} W")
    print(f"  grid_power_w:         {status.grid_power_w:.1f} W")
    print(f"  grid_import_w:        {status.grid_import_w:.1f} W")
    print(f"  grid_export_w:        {status.grid_export_w:.1f} W")
    print(f"  home_load_w:          {status.home_load_w:.1f} W")
    print(f"  solar_power_w:        {status.solar_power_w:.1f} W")
    print(f"  battery_command_active:    {status.battery_command_active}")
    print(f"  battery_command_discharge_w:{status.battery_command_discharge_w:.1f} W")
    print(f"  battery_command_pct_raw:   {status.battery_command_pct_raw}")


def _print_cmd_status(label: str, cmd: dict) -> None:
    print(f"[{label}] wset_ena={cmd['wset_ena']}  wset_mod={cmd['wset_mod']}  wset_pct={cmd['wset_pct']:.1f}%  wset_pct_raw={cmd['wset_pct_raw']}")


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

        _line("STEP 1: Starting state")
        status0 = await client.async_get_status()
        _print_status_summary("BEFORE", status0)

        _line(f"STEP 2: async_start_battery_discharge(power_w={TEST_POWER_W}, duration_s={TEST_DURATION_S})")
        try:
            await client.async_start_battery_discharge(power_w=TEST_POWER_W, duration_s=TEST_DURATION_S)
            print("SUCCESS - M704 command accepted and verified by hardware readback.")
        except FranklinWHWriteError as e:
            print(f"FAILED - M704 command was rejected: {e}")
            return

        _line("STEP 3: Immediate command status readback")
        cmd1 = await client.async_get_battery_command_status()
        _print_cmd_status("IMMEDIATELY AFTER COMMAND", cmd1)
        expected_pct = TEST_POWER_W / 5000.0 * 100.0
        print(f"  (expected wset_pct approx +{expected_pct:.1f}% if discharge rating is ~5000W; positive = discharging)")

        _line(f"STEP 4: Sampling every {OBSERVE_WAIT_S}s for {OBSERVE_DURATION_S}s")
        n_samples = OBSERVE_DURATION_S // OBSERVE_WAIT_S
        print(f"{'t(s)':>6}  {'batt_W':>9}  {'batt_dis_W':>11}  {'grid_W':>9}  {'grid_imp_W':>11}  {'grid_exp_W':>11}  {'cmd_pct_raw':>11}")
        for i in range(1, n_samples + 1):
            await asyncio.sleep(OBSERVE_WAIT_S)
            elapsed = i * OBSERVE_WAIT_S
            status_i = await client.async_get_status()
            print(f"{elapsed:>6}  {status_i.battery_power_w:>9.0f}  {status_i.battery_discharging_w:>11.0f}  {status_i.grid_power_w:>9.0f}  {status_i.grid_import_w:>11.0f}  {status_i.grid_export_w:>11.0f}  {status_i.battery_command_pct_raw:>11}")
        status1 = status_i
        print()
        _print_status_summary("FINAL SAMPLE DURING COMMAND", status1)

        _line("STEP 5: async_stop_battery_command()")
        await client.async_stop_battery_command()
        print("Command released (two-stage handshake completed).")

        _line("STEP 6: Confirm release")
        cmd2 = await client.async_get_battery_command_status()
        _print_cmd_status("AFTER RELEASE", cmd2)
        status2 = await client.async_get_status()
        _print_status_summary("AFTER RELEASE", status2)

        if not cmd2["wset_ena"]:
            print("\nSUCCESS - battery_command_active is False; native mode scheduling resumed.")
        else:
            print("\nWARNING - WSetEna is still 1 after release!")

    except FranklinWHConnectionError as e:
        print(f"CONNECTION ERROR: {e}")
        sys.exit(1)
    finally:
        try:
            await client.async_stop_battery_command(handshake_wait_s=0)
        except Exception:
            pass
        await client.close()


if __name__ == "__main__":
    asyncio.run(main())
