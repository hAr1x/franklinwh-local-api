# Changelog

All notable changes to `franklinwh_local_api` are documented in this
file. Format loosely follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [0.1.1]

### Added

- `async_get_battery_limits()` - reads SunSpec M702 once and returns
  `(charge_max_w, discharge_max_w)` nameplate ratings (both cached
  internally). Intended to be called once at integration init time.
- `arm_watchdog(duration_s)` / `disarm_watchdog()` - the software
  auto-release watchdog is now publicly armable/disarmable with a plain
  duration in seconds. The API has no notion of an absolute deadline;
  clients (e.g. the Home Assistant integration) that need to re-arm
  after a restart compute the remaining seconds themselves.

### Changed

- `async_start_battery_charge()` / `async_start_battery_discharge()`:
  when a command in the same direction is already active, the setpoint
  is now rewritten in place (single WSetPct register write + read-back
  verify, no disable/enable cycle) - the live power-adjustment fast
  path. Changing power does not reset an existing watchdog unless a new
  `duration_s` is explicitly passed. Opposite-direction or fresh starts
  still run the full standard M704 sequence (releasing anything active
  first).

## [0.1.0] - Initial release

### Added

- `FranklinWHLocalClient` - fully async client for local Modbus TCP
  access to a FranklinWH aGate.
- `async_get_status()` - single consolidated status snapshot in 6
  Modbus round-trips, including `home_load_w` from an undocumented
  high-resolution register at address `16000` (~1W precision).
- `async_get_device_info()` - reads manufacturer, model, firmware
  version, and serial number from SunSpec Model 1 (Common).
- `async_set_operating_mode()`, `async_set_self_reserve_pct()`,
  `async_set_tou_reserve_pct()` - writes with read-back verification.
- `async_start_battery_charge()` / `async_start_battery_discharge()` /
  `async_stop_battery_command()` - direct battery power control via
  SunSpec Model 704, with software watchdog (`duration_s`).
- `OperatingMode` enum, `FranklinWHStatus` data model,
  `FranklinWHDeviceInfo` data model,
  `FranklinWHConnectionError`/`FranklinWHWriteError` exceptions.
