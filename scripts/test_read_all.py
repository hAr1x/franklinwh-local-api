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
test_read_all.py - Manual debug/verification script for franklinwh_local_api.

Reads connection settings from a ".env" file, connects to the aGate over
local Modbus TCP, fetches a full FranklinWHStatus snapshot, and prints
every field in a human-readable, grouped format.

Usage:
    python scripts/test_read_all.py
    python scripts/test_read_all.py --watch
    python scripts/test_read_all.py --watch --interval 10
"""

import argparse
import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv  # noqa: E402

from franklinwh_local_api import (  # noqa: E402
    FranklinWHLocalClient,
    FranklinWHConnectionError,
)


def load_config() -> dict:
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if not env_path.exists():
        print(f"ERROR: no .env file found at {env_path}")
        print("Copy .env.example to .env and set AGATE_IP before running.")
        sys.exit(1)

    load_dotenv(dotenv_path=env_path)

    host = os.getenv("AGATE_IP")
    if not host:
        print("ERROR: AGATE_IP is not set in .env")
        sys.exit(1)

    port = int(os.getenv("AGATE_PORT", "502"))
    unit_id = int(os.getenv("AGATE_UNIT_ID", "0"))
    timeout = float(os.getenv("AGATE_TIMEOUT", "10.0"))

    return {
        "host": host,
        "port": port,
        "unit_id": unit_id,
        "timeout": timeout,
    }


def print_status(status) -> None:
    line = "=" * 70
    print(line)
    print("BATTERY")
    print(line)
    print(f"  Capacity (rated):       {status.battery_capacity_wh:>10.1f} Wh")
    print(f"  Energy (available):     {status.battery_energy_wh:>10.1f} Wh")
    print(f"  SOC (derived):          {status.battery_soc_pct:>10.3f} %")
    print(f"  SOC (raw register):     {status.battery_soc_pct_rounded:>10.1f} %")
    print(f"  SOH (health):           {status.battery_soh_pct:>10.1f} %")
    print(f"  DC power (raw signed):  {status.battery_power_w:>10.1f} W")
    print(f"  Charging power:         {status.battery_charging_w:>10.1f} W")
    print(f"  Discharging power:      {status.battery_discharging_w:>10.1f} W")

    print()
    print(line)
    print("GRID")
    print(line)
    print(f"  Connected:              {status.grid_connected}")
    print(f"  Power (raw signed):     {status.grid_power_w:>10.1f} W")
    print(f"  Import power:           {status.grid_import_w:>10.1f} W")
    print(f"  Export power:           {status.grid_export_w:>10.1f} W")
    print(f"  Voltage L-N (~120V):    {status.grid_voltage_ln_v:>10.1f} V")
    print(f"  Voltage L-L (~240V):    {status.grid_voltage_ll_v:>10.1f} V")
    print(f"  Frequency:              {status.grid_frequency_hz:>10.3f} Hz")

    print()
    print(line)
    print("SOLAR / HOME LOAD")
    print(line)
    print(f"  Solar production:       {status.solar_power_w:>10.1f} W")
    print(f"  Home load:              {status.home_load_w:>10.1f} W")

    print()
    print(line)
    print("OPERATING MODE / RESERVES")
    print(line)
    print(f"  Mode:                   {status.operating_mode.value}")
    print(f"  Self-Consumption res %: {status.self_reserve_pct}")
    print(f"  TOU reserve %:          {status.tou_reserve_pct}")
    print(f"  TOU dispatch state:     {status.tou_dispatch_state}")
    print(f"  TOU dispatch raw:       {status.tou_dispatch_raw}")

    print()
    print(line)
    print("TEMPERATURE")
    print(line)
    print(f"  Ambient:                {status.ambient_temp_c:>10.1f} C")
    print(f"  Cabinet:                {status.cabinet_temp_c:>10.1f} C")

    print()
    print(line)
    print("BATTERY COMMAND (M704 Remote Control)")
    print(line)
    print(f"  Active:                 {status.battery_command_active}")
    print(f"  Charge Power (active):  {status.battery_command_charge_w:>10.1f} W")
    print(f"  Discharge Power (active):{status.battery_command_discharge_w:>10.1f} W")
    print(f"  WSetPct (raw):          {status.battery_command_pct_raw}")

    print()
    print(line)
    print("ALARMS")
    print(line)
    print(f"  Active:                 {status.alarm_active}")
    print(f"  Raw bits:               0x{status.raw_alarm_bits:08X}")
    if status.alarms:
        for name in status.alarms:
            print(f"    - {name}")
    else:
        print("    (none)")
    print(line)


async def run_once(config: dict) -> None:
    client = FranklinWHLocalClient(
        host=config["host"], port=config["port"],
        unit_id=config["unit_id"], timeout=config["timeout"],
    )
    try:
        await client.connect()
        print(f"Connected to aGate at {config['host']}:{config['port']} (unit_id={config['unit_id']})")
        status = await client.async_get_status()
        print_status(status)
    except FranklinWHConnectionError as e:
        print(f"CONNECTION ERROR: {e}")
        sys.exit(1)
    finally:
        await client.close()


async def run_watch(config: dict, interval: float) -> None:
    client = FranklinWHLocalClient(
        host=config["host"], port=config["port"],
        unit_id=config["unit_id"], timeout=config["timeout"],
    )
    try:
        await client.connect()
        print(f"Connected to aGate at {config['host']}:{config['port']} (unit_id={config['unit_id']})")
        print(f"Watching every {interval}s - press Ctrl+C to stop.\n")
        while True:
            try:
                status = await client.async_get_status()
                print_status(status)
                print()
            except FranklinWHConnectionError as e:
                print(f"READ ERROR (will retry): {e}")
            await asyncio.sleep(interval)
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        await client.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Read and print a full FranklinWH aGate status snapshot for debugging.")
    parser.add_argument("--watch", action="store_true", help="Continuously re-read and print status every --interval seconds.")
    parser.add_argument("--interval", type=float, default=5.0, help="Seconds between reads in --watch mode (default: 5.0).")
    args = parser.parse_args()

    config = load_config()

    if args.watch:
        asyncio.run(run_watch(config, args.interval))
    else:
        asyncio.run(run_once(config))


if __name__ == "__main__":
    main()
