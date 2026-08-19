# franklinwh_local_api

A lightweight, fully **local** (LAN-only) async Python client for the
FranklinWH aGate battery gateway, communicating directly over Modbus TCP.

No FranklinWH account, no cloud API, no internet access required —
everything happens on your local network.

## Why this exists

The official FranklinWH mobile app and cloud API work fine, but they
require an internet connection and an account. This library talks
directly to the aGate's Modbus TCP interface (port 502) on your LAN,
using registers that have been cross-validated against the
[`franklinwh-modbus`](https://github.com/david2069/franklinwh-modbus)
open-source reference project, and further verified against a live
device.

## Features

- Fully async (`pymodbus`'s native `AsyncModbusTcpClient` — no thread
  pool / executor wrapping needed, integrates cleanly with
  asyncio-based apps such as Home Assistant)
- Reads a single consolidated status snapshot in 6 Modbus round-trips:
  - Battery capacity, available energy, SOC (both raw and a
    higher-precision derived value), SOH, charge/discharge power
  - Grid import/export power, connection state, voltage (L-N ~120V,
    L-L ~240V), frequency
  - Solar production, home load (sourced from an undocumented
    high-resolution register — see "Home load precision" below)
  - Native operating mode (Emergency Backup / Self-Consumption / TOU)
  - Self-Consumption reserve % and TOU reserve % (read directly from
    their respective hardware registers — see "Mode / reserve control"
    below)
  - Ambient/cabinet temperature
  - Decoded system alarms
  - Active battery command state (see "Battery charge/discharge
    control" below)
- Device identification via `async_get_device_info()` (SunSpec Model
  1): manufacturer, model, firmware version, serial number — a
  separate, single-shot call intended for populating a UI's device
  info card (not part of the regular polling snapshot)
- Write support for:
  - Switching operating mode
  - Setting Self-Consumption reserve %
  - Setting TOU reserve %
  - **Commanding the battery to charge or discharge at a specific power**
    (see "Battery charge/discharge control" below)

## Home load precision

`home_load_w` is sourced from an undocumented single-register block at
address `16000`, which mirrors the FranklinWH extension block's home
load reading (formerly register `15506`/`LoadActiveP`) but with ~1W
precision instead of ~100W quantization. This register fully replaces
`15506` as the source for `home_load_w` — the coarser register is no
longer read at all.

## Battery charge/discharge control (M704)

`async_start_battery_charge(power_w, duration_s=None)` and
`async_start_battery_discharge(power_w, duration_s=None)` command the
aGate's battery to charge or discharge at a precise wattage, via the
standard SunSpec Model 704 (`WSetEna`/`WSetMod`/`WSetPct`) — **no SPAN
Modbus unlock required**, since these are standard SunSpec registers,
not FranklinWH's proprietary extension block.

Both directions hold the commanded setpoint precisely and consistently
once accepted by hardware (e.g. commanding 500W charge holds
`battery_power_w` at -500W; commanding 500W discharge holds it at
+500W).

**Important: this controls BATTERY power, not a grid-side target.**
Calling `async_start_battery_charge(power_w=4000)` with a 2000W home
load and no solar results in a grid import of ~6000W (4000W for the
battery + 2000W for the home) — not 4000W. The resulting grid
import/export is a side effect of the aGate's internal power balance
(`grid = home_load + battery_charge - solar`), not a value M704 targets
directly. There is no known Modbus path on this hardware/firmware that
directly limits grid-side import/export power (see "Known limitations"
below).

Typical use cases:
- Forcing the battery to charge from the grid during a specific time
  window (e.g. a cheap overnight rate), independent of the aGate's
  native TOU/Self-Consumption reserve % logic.
- Forcing a controlled discharge rate rather than whatever the native
  mode's algorithm would choose.
- Locking the battery at 0W (via `async_stop_battery_command()`) so
  solar can serve the home while grid serves an un-isolated load (e.g.
  an EV charger with no dedicated smart circuit), without the aGate's
  native Self-Consumption logic auto-discharging the battery to cover
  that load.

A software watchdog (`duration_s`) auto-releases the command after a
bounded time, since the hardware's own reversion timer (`WSetRvrtTms`)
is a known no-op on FranklinWH firmware (the countdown runs but never
actually reverts power).

`async_set_operating_mode()` automatically detects and releases any
active battery command before switching native modes, since `WSetEna=1`
suspends the aGate's native mode scheduling entirely.

## Mode / reserve control

This client is a thin, stateless wrapper around three independent
Modbus extension registers - it does not maintain any internal state
between calls:

- `async_set_operating_mode(mode)` writes register `15507` (OnGridMode)
  and reads it back to confirm the write stuck. It does **not** touch
  `15508`/`15509` in any way.
- `async_set_self_reserve_pct(pct)` writes register `15508`
  (SelfReserve) and reads it back to confirm the write stuck. This is a
  plain, unconditional write regardless of the currently active mode.
- `async_set_tou_reserve_pct(pct)` writes register `15509` (TouReserve)
  and reads it back to confirm the write stuck. Also a plain,
  unconditional write regardless of the currently active mode.

**Known FranklinWH firmware defect:** register `15509` (TouReserve)
always mirrors whatever was last written to `15508` (SelfReserve), and
vice versa - there is no way to store two independent reserve values
in hardware at the same time. This client does **not** attempt to work
around or hide that defect - it just performs the write/read you ask
for, exactly as specified. Any business logic to manage "what each
reserve % should be, independent of this firmware defect" belongs in
the calling application - the `ha_franklinwh_modbus` Home Assistant
integration built on top of this library is one example of that kind
of coordination.

## Requirements

There are **two separate, independent installer-side prerequisites**
on the FranklinWH side for the *extension register* features (native
mode switching and reserve % — NOT the battery charge/discharge
commands above, which use standard SunSpec registers and always work).
Both are enabled by your installer or by FranklinWH support - neither
can be turned on from this library or from the standard end-user
mobile app settings:

1. **Modbus TCP enabled** - required for *anything to work at all*,
   including read-only status queries. Without this, the aGate's
   Modbus TCP listener (port 502) is not reachable and `connect()`
   will fail outright.
2. **"SPAN Modbus" write unlock** - required *additionally*, on top of
   (1), for the extension-register writes to succeed: switching
   operating mode (`async_set_operating_mode()`) or setting reserve
   percentages (`async_set_self_reserve_pct()` /
   `async_set_tou_reserve_pct()`). Without this unlock, reads work
   completely normally, but writes to the extension registers
   (15507/15508/15509) are silently discarded by the firmware.

If you can run `scripts/test_read_all.py` successfully but every
extension-register write attempt (mode switch, reserve %) raises
`FranklinWHWriteError`, that means (1) is enabled but (2) is not yet -
contact your installer or FranklinWH support to request the SPAN
Modbus write unlock for your aGate.

**Empirically confirmed behavior when the SPAN unlock is NOT yet
granted:** writes to extension registers (15507/15508/15509) are ACK'd
at the Modbus protocol level but are **silently discarded** by the
aGate firmware - a subsequent read-back shows the register unchanged.
This is why `async_set_operating_mode()` and the reserve % setters
always perform a read-back verification and raise
`FranklinWHWriteError` if the value didn't actually stick.

## Installation

```bash
pip install franklinwh_local_api
```

For local development (editable install from a clone of this repo):

```bash
pip install -e .
```

## Quick start

```python
import asyncio
from franklinwh_local_api import FranklinWHLocalClient, OperatingMode

async def main():
    client = FranklinWHLocalClient(host="192.168.1.50")
    await client.connect()

    status = await client.async_get_status()
    print(f"SOC: {status.battery_soc_pct:.1f}%")
    print(f"Mode: {status.operating_mode.value}")
    print(f"Solar: {status.solar_power_w} W")
    print(f"Home load: {status.home_load_w} W")

    # Device identification (single-shot, e.g. at app startup)
    info = await client.async_get_device_info()
    print(f"{info.manufacturer} {info.model} (fw {info.firmware_version}, SN {info.serial_number})")

    # Switch native mode + reserve % (requires SPAN Modbus unlock)
    await client.async_set_operating_mode(OperatingMode.TOU)
    await client.async_set_tou_reserve_pct(30)

    # Command the battery directly (works regardless of SPAN unlock)
    await client.async_start_battery_charge(power_w=2000, duration_s=3600)
    # ... later ...
    await client.async_stop_battery_command()

    await client.close()

asyncio.run(main())
```

Or using the async context manager:

```python
async with FranklinWHLocalClient(host="192.168.1.50") as client:
    status = await client.async_get_status()
```

## API reference

### `FranklinWHLocalClient`

| Method | Description |
|---|---|
| `connect()` | Open the Modbus TCP connection. Raises `FranklinWHConnectionError` on failure. |
| `close()` | Close the connection. |
| `is_connected` (property) | `True` if currently connected. |
| `async_get_status() -> FranklinWHStatus` | Read a full status snapshot (6 Modbus round-trips). |
| `async_get_device_info() -> FranklinWHDeviceInfo` | Read manufacturer/model/firmware/serial from SunSpec Model 1. |
| `async_set_operating_mode(mode: OperatingMode)` | Switch native operating mode. Requires SPAN Modbus unlock. |
| `async_set_self_reserve_pct(pct: int)` | Write Self-Consumption reserve % (0-100). Requires SPAN Modbus unlock. |
| `async_set_tou_reserve_pct(pct: int)` | Write TOU reserve % (0-100). Requires SPAN Modbus unlock. |
| `async_start_battery_charge(power_w: float, duration_s: float \| None = None)` | Command the battery to charge at `power_w` watts. |
| `async_start_battery_discharge(power_w: float, duration_s: float \| None = None)` | Command the battery to discharge at `power_w` watts. |
| `async_stop_battery_command(handshake_wait_s: float = 1.0)` | Release an active M704 command; native mode scheduling resumes. |
| `async_get_battery_command_status() -> dict` | Lightweight read of just the M704 remote-control state. |

### Data models

- **`FranklinWHStatus`** — full point-in-time status snapshot returned
  by `async_get_status()`. See `models.py` for the complete field list
  and units (all power fields are in Watts, all energy fields in Wh).
- **`FranklinWHDeviceInfo`** — device identification returned by
  `async_get_device_info()`: `manufacturer`, `model`,
  `firmware_version`, `serial_number`.
- **`OperatingMode`** — enum of the three user-selectable native modes
  (`EMERGENCY_BACKUP`, `SELF_CONSUMPTION`, `TOU`), plus two read-only
  hardware states (`STANDBY`, `MANUAL`).

### Exceptions

- **`FranklinWHConnectionError`** — raised on any Modbus-level
  connection/read/write failure.
- **`FranklinWHWriteError`** — raised when a write is ACK'd at the
  protocol level but the read-back verification shows the value did
  not actually change in hardware.

## Debugging / manual verification

Standalone debug scripts are included in `scripts/`:

- `test_read_all.py` — reads connection settings from a `.env` file and
  prints every field of a full status snapshot.
- `monitor_live.py` — continuously polls and redraws a live dashboard
  in place in the terminal.
- `test_battery_charge.py` / `test_battery_discharge.py` — end-to-end
  verification of the M704 battery command path.
- `test_set_mode.py` — round-trip test of `async_set_operating_mode()`
  and the reserve % setters.

```bash
cp .env.example .env
# edit .env and set AGATE_IP

pip install -r requirements.txt
python scripts/test_read_all.py

# or, to continuously re-read every 5 seconds:
python scripts/test_read_all.py --watch

# verify battery charge/discharge control end-to-end:
python scripts/test_battery_charge.py
python scripts/test_battery_discharge.py
```

## Known limitations

- **Grid import/export power limiting is NOT implemented and is not
  believed to be possible on this hardware.** Neither the Modbus
  `WMaxLimPct`/`WChaRteMax` register groups nor the FranklinWH cloud
  API's power control settings reliably enforce a hardware-level
  export/import limit. The battery charge/discharge commands above can
  be used as a workaround for some use cases but do not directly
  target a grid-side power value.
- The battery DC power sign convention (`M714.DCW`) is
  negative = charging, positive = discharging. See `models.py` for
  details.
- Register `15509` (TOU reserve) is a known firmware defect that always
  mirrors `15508`, and vice versa — see "Mode / reserve control" above.

## Acknowledgments

The Modbus register map used by this library was cross-validated against
[`franklinwh-modbus`](https://github.com/david2069/franklinwh-modbus)
by [@david2069](https://github.com/david2069), whose extensive testing
against live hardware helped confirm which registers and modes are
actually usable.

## Changelog

See [CHANGELOG.md](CHANGELOG.md).

## Disclaimer

This project has no affiliation with FranklinWH. See
[DISCLAIMER.md](DISCLAIMER.md) for the full disclaimer.

## License

GNU General Public License v3.0 or later (GPLv3+). See
[LICENSE](LICENSE) for the full text.
