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
monitor_live.py - Continuously poll and display a live-refreshing status
dashboard in the terminal.

Unlike test_read_all.py --watch (which scrolls), this clears the screen
and redraws in place every poll, giving a live "dashboard" feel.

Usage:
    python scripts/monitor_live.py
    python scripts/monitor_live.py --interval 2.0
"""

import argparse
import asyncio
import os
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv  # noqa: E402

from franklinwh_local_api import (  # noqa: E402
    FranklinWHLocalClient,
    FranklinWHConnectionError,
)

DEFAULT_INTERVAL_S = 1.0

_CLEAR_SCREEN = "\033[2J\033[H"


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


def render_dashboard(status, host: str, port: int, poll_count: int, interval_s: float, last_error: str = None) -> str:
    now = datetime.now().strftime("%H:%M:%S")
    line = "=" * 70
    out = []

    out.append(f"FranklinWH aGate Live Monitor - {host}:{port}")
    out.append(f"Poll #{poll_count}  |  Updated: {now}  |  Interval: {interval_s}s  |  Ctrl+C to stop")
    out.append(line)

    if last_error:
        out.append(f"LAST READ ERROR (showing previous good data below): {last_error}")
        out.append(line)

    out.append("BATTERY")
    out.append(line)
    out.append(f"  Capacity (rated):       {status.battery_capacity_wh:>10.1f} Wh")
    out.append(f"  Energy (available):     {status.battery_energy_wh:>10.1f} Wh")
    out.append(f"  SOC:                    {status.battery_soc_pct:>10.3f} %")
    out.append(f"  SOH (health):           {status.battery_soh_pct:>10.1f} %")
    out.append(f"  DC power (raw signed):  {status.battery_power_w:>10.1f} W")
    out.append(f"  Charging power:         {status.battery_charging_w:>10.1f} W")
    out.append(f"  Discharging power:      {status.battery_discharging_w:>10.1f} W")

    out.append("")
    out.append(line)
    out.append("GRID")
    out.append(line)
    out.append(f"  Connected:              {status.grid_connected}")
    out.append(f"  Import power:           {status.grid_import_w:>10.1f} W")
    out.append(f"  Export power:           {status.grid_export_w:>10.1f} W")
    out.append(f"  Voltage L-N / L-L:      {status.grid_voltage_ln_v:>6.1f}V / {status.grid_voltage_ll_v:>6.1f}V")
    out.append(f"  Frequency:              {status.grid_frequency_hz:>10.3f} Hz")

    out.append("")
    out.append(line)
    out.append("SOLAR / HOME LOAD")
    out.append(line)
    out.append(f"  Solar production:       {status.solar_power_w:>10.1f} W")
    out.append(f"  Home load:              {status.home_load_w:>10.1f} W")

    out.append("")
    out.append(line)
    out.append("OPERATING MODE / RESERVES")
    out.append(line)
    out.append(f"  Mode:                   {status.operating_mode.value}")
    out.append(f"  Self-Consumption res %: {status.self_reserve_pct}")
    out.append(f"  TOU reserve %:          {status.tou_reserve_pct}")
    if status.tou_dispatch_state:
        out.append(f"  TOU dispatch state:     {status.tou_dispatch_state}")

    out.append("")
    out.append(line)
    out.append("TEMPERATURE")
    out.append(line)
    out.append(f"  Ambient:                {status.ambient_temp_c:>10.1f} C")
    out.append(f"  Cabinet:                {status.cabinet_temp_c:>10.1f} C")

    out.append("")
    out.append(line)
    out.append("BATTERY COMMAND (M704 Remote Control)")
    out.append(line)
    out.append(f"  Active:                 {status.battery_command_active}")
    if status.battery_command_active:
        out.append(f"  Charge Power (active):  {status.battery_command_charge_w:>10.1f} W")
        out.append(f"  Discharge Power (active):{status.battery_command_discharge_w:>10.1f} W")

    out.append("")
    out.append(line)
    out.append("ALARMS")
    out.append(line)
    if status.alarms:
        out.append(f"  ACTIVE: {', '.join(status.alarms)}")
    else:
        out.append("  Active:                 False")
    out.append(line)

    return "\n".join(out)


async def run(config: dict, interval_s: float) -> None:
    client = FranklinWHLocalClient(
        host=config["host"], port=config["port"],
        unit_id=config["unit_id"], timeout=config["timeout"],
    )

    try:
        await client.connect()
    except FranklinWHConnectionError as e:
        print(f"CONNECTION ERROR: {e}")
        sys.exit(1)

    poll_count = 0
    last_status = None
    last_error = None

    try:
        while True:
            poll_count += 1
            try:
                status = await client.async_get_status()
                last_status = status
                last_error = None
            except FranklinWHConnectionError as e:
                last_error = str(e)

            if last_status is not None:
                dashboard = render_dashboard(last_status, config["host"], config["port"], poll_count, interval_s, last_error=last_error)
                sys.stdout.write(_CLEAR_SCREEN)
                sys.stdout.write(dashboard + "\n")
                sys.stdout.flush()
            else:
                sys.stdout.write(_CLEAR_SCREEN)
                sys.stdout.write(f"Poll #{poll_count} - waiting for first successful read...\n")
                if last_error:
                    sys.stdout.write(f"Last error: {last_error}\n")
                sys.stdout.flush()

            await asyncio.sleep(interval_s)
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        await client.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Continuously poll and display a live FranklinWH aGate status dashboard.")
    parser.add_argument("--interval", type=float, default=DEFAULT_INTERVAL_S, help=f"Seconds between polls (default: {DEFAULT_INTERVAL_S}).")
    args = parser.parse_args()

    config = load_config()
    try:
        asyncio.run(run(config, args.interval))
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
