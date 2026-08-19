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
FranklinWHLocalClient - the main async client for talking to a FranklinWH
aGate gateway over local Modbus TCP.

This client is intentionally "local-only": it never talks to the
FranklinWH cloud, needs no account credentials, and works entirely on
the LAN. It uses pymodbus's native AsyncModbusTcpClient so it integrates
cleanly into any asyncio application (e.g. Home Assistant) without
needing executor-thread wrapping.
"""

import asyncio
import logging
from typing import List, Optional

from pymodbus.client import AsyncModbusTcpClient

from . import const
from .exceptions import FranklinWHConnectionError, FranklinWHWriteError
from .models import FranklinWHDeviceInfo, FranklinWHStatus, OperatingMode

_LOGGER = logging.getLogger(__name__)


def _to_signed16(value: int) -> int:
    """Convert a raw uint16 register value into a signed int16."""
    return value - 0x10000 if value >= 0x8000 else value


def _to_uint32(hi: int, lo: int) -> int:
    """Combine two uint16 registers (big-endian) into a uint32."""
    return (hi << 16) | lo


def _to_unsigned16(value: int) -> int:
    """Convert a signed int16 (-32768..32767) into its unsigned uint16
    two's-complement representation (0..65535), suitable for writing via
    pymodbus's write_register() which requires an unsigned value."""
    return value & 0xFFFF


def _apply_scale(raw: int, scale_factor: int) -> float:
    """Apply a SunSpec-style scale factor: value = raw * 10^scale_factor."""
    return raw * (10 ** scale_factor)


def _decode_sunspec_string(registers: List[int]) -> str:
    """Decode a SunSpec-style string field: a sequence of uint16
    registers, each holding 2 ASCII characters big-endian (high byte
    first), null-padded to the field's fixed length. Strips trailing
    NUL bytes/whitespace.
    """
    raw_bytes = bytearray()
    for reg in registers:
        raw_bytes.append((reg >> 8) & 0xFF)
        raw_bytes.append(reg & 0xFF)
    return raw_bytes.split(b"\x00", 1)[0].decode("ascii", errors="replace").strip()


class FranklinWHLocalClient:
    """Async client for local Modbus TCP access to a FranklinWH aGate.

    Usage:
        client = FranklinWHLocalClient(host="192.168.1.50")
        await client.connect()
        status = await client.async_get_status()
        await client.async_set_operating_mode(OperatingMode.TOU)
        await client.close()
    """

    def __init__(
        self,
        host: str,
        port: int = const.DEFAULT_PORT,
        unit_id: int = const.DEFAULT_UNIT_ID,
        timeout: float = const.DEFAULT_TIMEOUT_S,
    ):
        """Create a new client.

        Args:
            host: aGate IP address on the local network.
            port: Modbus TCP port (default 502).
            unit_id: Modbus unit/slave ID (default 0 - the aGate has been
                observed to alias/ignore this field, responding
                identically regardless of the ID used).
            timeout: Socket timeout in seconds for each Modbus operation.
        """
        self._host = host
        self._port = port
        self._unit_id = unit_id
        self._timeout = timeout

        self._client: Optional[AsyncModbusTcpClient] = None
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # Connection lifecycle
    # ------------------------------------------------------------------

    async def connect(self) -> None:
        """Open the Modbus TCP connection to the aGate."""
        self._client = AsyncModbusTcpClient(
            host=self._host,
            port=self._port,
            timeout=self._timeout,
        )
        connected = await self._client.connect()
        if not connected:
            raise FranklinWHConnectionError(
                f"Could not connect to aGate at {self._host}:{self._port}"
            )
        _LOGGER.debug("Connected to aGate at %s:%s", self._host, self._port)

    async def close(self) -> None:
        """Close the Modbus TCP connection."""
        if self._client is not None:
            self._client.close()
            self._client = None

    async def __aenter__(self) -> "FranklinWHLocalClient":
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.close()

    @property
    def is_connected(self) -> bool:
        return self._client is not None and self._client.connected

    # ------------------------------------------------------------------
    # Low-level register helpers
    # ------------------------------------------------------------------

    async def _read_registers(self, address: int, count: int) -> List[int]:
        """Read `count` holding registers starting at `address`.

        Raises FranklinWHConnectionError on any Modbus-level failure.
        """
        if self._client is None or not self._client.connected:
            raise FranklinWHConnectionError("Not connected to aGate")

        async with self._lock:
            result = await self._client.read_holding_registers(
                address=address, count=count, device_id=self._unit_id
            )

        if result.isError():
            raise FranklinWHConnectionError(
                f"Modbus read error at address {address} (count={count}): {result}"
            )
        return result.registers

    async def _write_register(self, address: int, value: int) -> None:
        """Write a single holding register.

        Raises FranklinWHConnectionError on any Modbus-level failure.
        """
        if self._client is None or not self._client.connected:
            raise FranklinWHConnectionError("Not connected to aGate")

        async with self._lock:
            result = await self._client.write_register(
                address=address, value=value, device_id=self._unit_id
            )

        if result.isError():
            raise FranklinWHConnectionError(
                f"Modbus write error at address {address} (value={value}): {result}"
            )

    async def _read_and_verify_register(self, address: int) -> int:
        """Read back a single register value (used to verify writes)."""
        regs = await self._read_registers(address, 1)
        return regs[0]

    # ------------------------------------------------------------------
    # Status reading
    # ------------------------------------------------------------------

    async def async_get_status(self) -> FranklinWHStatus:
        """Read a full status snapshot from the aGate.

        Performs 6 Modbus read operations (M701, M713, M714, extension
        block, M704, and the undocumented high-res home load register)
        and assembles a fully-normalized FranklinWHStatus object.
        """
        m701 = await self._read_registers(const.M701_BASE, const.M701_COUNT)
        m713 = await self._read_registers(const.M713_BASE, const.M713_COUNT)
        m714 = await self._read_registers(const.M714_BASE, const.M714_COUNT)
        ext = await self._read_registers(const.EXT_BASE, const.EXT_COUNT)
        m704 = await self._read_registers(const.M704_BASE, const.M704_COUNT)
        home_load_hires = await self._read_registers(const.EXT_HOME_LOAD_HIRES_ADDR, 1)

        # --- M701: AC measurement / grid ---
        w_sf = _to_signed16(m701[const.M701_OFF_W_SF])
        v_sf = _to_signed16(m701[const.M701_OFF_V_SF])
        hz_sf = _to_signed16(m701[const.M701_OFF_HZ_SF])
        tmp_sf = _to_signed16(m701[const.M701_OFF_TMP_SF])

        conn_st_raw = m701[const.M701_OFF_CONN_ST]
        grid_connected = conn_st_raw == const.CONN_STATE_CONNECTED

        grid_power_raw = _to_signed16(m701[const.M701_OFF_W])
        grid_power_w = _apply_scale(grid_power_raw, w_sf)
        grid_import_w = max(grid_power_w, 0.0)
        grid_export_w = max(-grid_power_w, 0.0)

        grid_voltage_ll_v = _apply_scale(m701[const.M701_OFF_LLV], v_sf)
        grid_voltage_ln_v = _apply_scale(m701[const.M701_OFF_LNV], v_sf)

        hz_hi = m701[const.M701_OFF_HZ]
        hz_lo = m701[const.M701_OFF_HZ + 1]
        grid_frequency_hz = _apply_scale(_to_uint32(hz_hi, hz_lo), hz_sf)

        ambient_temp_c = _apply_scale(
            _to_signed16(m701[const.M701_OFF_TMP_AMB]), tmp_sf
        )
        cabinet_temp_c = _apply_scale(
            _to_signed16(m701[const.M701_OFF_TMP_CAB]), tmp_sf
        )

        alrm_hi = m701[const.M701_OFF_ALRM]
        alrm_lo = m701[const.M701_OFF_ALRM + 1]
        raw_alarm_bits = _to_uint32(alrm_hi, alrm_lo)
        alarms = [
            name for bit, name in const.ALARM_BITS.items()
            if raw_alarm_bits & (1 << bit)
        ]

        # --- M713: battery capacity / SOC ---
        wh_sf = _to_signed16(m713[const.M713_OFF_WH_SF])
        pct_sf = _to_signed16(m713[const.M713_OFF_PCT_SF])

        battery_capacity_wh = _apply_scale(m713[const.M713_OFF_WHRTG], wh_sf)
        battery_energy_wh = _apply_scale(m713[const.M713_OFF_WHAVAIL], wh_sf)
        battery_soc_pct_rounded = _apply_scale(m713[const.M713_OFF_SOC], pct_sf)
        battery_soh_pct = _apply_scale(m713[const.M713_OFF_SOH], pct_sf)

        if battery_capacity_wh > 0:
            battery_soc_pct = round(
                battery_energy_wh / battery_capacity_wh * 100.0, 3
            )
        else:
            battery_soc_pct = battery_soc_pct_rounded

        # --- M714: battery DC power ---
        dcw_sf = _to_signed16(m714[const.M714_OFF_DCW_SF])
        battery_power_raw = _to_signed16(m714[const.M714_OFF_DCW])
        battery_power_w = _apply_scale(battery_power_raw, dcw_sf)

        battery_charging_w = max(-battery_power_w, 0.0)
        battery_discharging_w = max(battery_power_w, 0.0)

        # --- Extension registers: solar / home load / mode / reserves ---
        solar_power_raw = ext[const.EXT_OFF_PV_TOTAL]
        if solar_power_raw == 0xFFFF or solar_power_raw > const.MAX_PLAUSIBLE_SOLAR_W:
            solar_power_w = 0.0
        else:
            solar_power_w = float(solar_power_raw)

        home_load_raw = home_load_hires[0]
        if home_load_raw == 0xFFFF or home_load_raw > const.MAX_PLAUSIBLE_LOAD_W:
            home_load_w = 0.0
        else:
            home_load_w = float(home_load_raw)

        mode_raw = ext[const.EXT_OFF_ONGRID_MODE]
        try:
            operating_mode = OperatingMode.from_register_value(mode_raw)
        except ValueError:
            _LOGGER.warning("Unrecognized native operating mode value: %s", mode_raw)
            operating_mode = OperatingMode.MANUAL

        self_reserve_pct = ext[const.EXT_OFF_SELF_RESERVE]
        tou_reserve_pct = ext[const.EXT_OFF_TOU_RESERVE]

        tou_dispatch_state: Optional[str] = None
        tou_dispatch_raw: Optional[int] = None
        if operating_mode == OperatingMode.TOU:
            tou_dispatch_raw = ext[const.EXT_OFF_TOU_DISPATCH]
            tou_dispatch_state = const.TOU_DISPATCH_MAP.get(
                tou_dispatch_raw, f"Unknown({tou_dispatch_raw})"
            )

        # --- M704: battery command state ---
        wsetena_raw = m704[const.M704_OFF_WSETENA]
        battery_command_active = wsetena_raw == const.WSETENA_ENABLED

        wsetpct_sf = _to_signed16(m704[const.M704_OFF_WSETPCT_SF])
        wsetpct_raw = _to_signed16(m704[const.M704_OFF_WSETPCT])
        wsetpct_scaled = _apply_scale(wsetpct_raw, wsetpct_sf)

        battery_command_charge_w = 0.0
        battery_command_discharge_w = 0.0
        if battery_command_active:
            if wsetpct_scaled < 0:
                max_w = self._get_charge_rate_max_w_cached()
                battery_command_charge_w = abs(wsetpct_scaled) / 100.0 * max_w
            elif wsetpct_scaled > 0:
                max_w = self._get_discharge_rate_max_w_cached()
                battery_command_discharge_w = wsetpct_scaled / 100.0 * max_w

        return FranklinWHStatus(
            battery_capacity_wh=battery_capacity_wh,
            battery_energy_wh=battery_energy_wh,
            battery_soc_pct=battery_soc_pct,
            battery_soc_pct_rounded=battery_soc_pct_rounded,
            battery_soh_pct=battery_soh_pct,
            battery_power_w=battery_power_w,
            battery_charging_w=battery_charging_w,
            battery_discharging_w=battery_discharging_w,
            grid_power_w=grid_power_w,
            grid_import_w=grid_import_w,
            grid_export_w=grid_export_w,
            grid_connected=grid_connected,
            grid_voltage_ln_v=grid_voltage_ln_v,
            grid_voltage_ll_v=grid_voltage_ll_v,
            grid_frequency_hz=grid_frequency_hz,
            solar_power_w=solar_power_w,
            home_load_w=home_load_w,
            operating_mode=operating_mode,
            self_reserve_pct=self_reserve_pct,
            tou_reserve_pct=tou_reserve_pct,
            tou_dispatch_state=tou_dispatch_state,
            tou_dispatch_raw=tou_dispatch_raw,
            ambient_temp_c=ambient_temp_c,
            cabinet_temp_c=cabinet_temp_c,
            alarms=alarms,
            alarm_active=len(alarms) > 0,
            raw_alarm_bits=raw_alarm_bits,
            battery_command_active=battery_command_active,
            battery_command_charge_w=battery_command_charge_w,
            battery_command_discharge_w=battery_command_discharge_w,
            battery_command_pct_raw=wsetpct_raw,
        )

    async def async_get_device_info(self) -> FranklinWHDeviceInfo:
        """Read device identification from SunSpec Model 1 (Common).

        Performs a single Modbus read covering the whole Model 1 body
        (manufacturer, model, firmware version, serial number) and
        decodes each field from its packed SunSpec string encoding.

        This is intentionally NOT part of async_get_status() - it's
        meant to be called once at integration setup/reload time (e.g.
        to populate a UI's device info card), not on every poll cycle.
        """
        model1 = await self._read_registers(const.MODEL1_BASE, const.MODEL1_COUNT)

        manufacturer = _decode_sunspec_string(
            model1[const.MODEL1_OFF_MN:const.MODEL1_OFF_MD]
        )
        model = _decode_sunspec_string(
            model1[const.MODEL1_OFF_MD:const.MODEL1_OFF_VR]
        )
        firmware_version = _decode_sunspec_string(
            model1[const.MODEL1_OFF_VR:const.MODEL1_OFF_SN]
        )
        serial_number = _decode_sunspec_string(
            model1[const.MODEL1_OFF_SN:const.MODEL1_COUNT]
        )

        return FranklinWHDeviceInfo(
            manufacturer=manufacturer,
            model=model,
            firmware_version=firmware_version,
            serial_number=serial_number,
        )

    # ------------------------------------------------------------------
    # Mode / reserve control
    # ------------------------------------------------------------------

    async def async_set_operating_mode(self, mode: OperatingMode) -> None:
        """Switch the aGate's native operating mode."""
        if mode in (OperatingMode.STANDBY, OperatingMode.MANUAL):
            raise FranklinWHWriteError(
                f"{mode.value} is not a user-selectable target mode; it is "
                f"a hardware-internal state only. Valid targets are "
                f"EMERGENCY_BACKUP, SELF_CONSUMPTION, and TOU."
            )

        cmd_status = await self.async_get_battery_command_status()
        if cmd_status.get("wset_ena"):
            _LOGGER.info(
                "Active M704 battery command detected before mode switch "
                "to %s - releasing it first", mode.value
            )
            await self.async_stop_battery_command()

        target_value = mode.to_register_value()
        await self._write_register(const.EXT_ADDR_ONGRID_MODE, target_value)

        await asyncio.sleep(0.5)
        actual_value = await self._read_and_verify_register(const.EXT_ADDR_ONGRID_MODE)
        if actual_value != target_value:
            raise FranklinWHWriteError(
                f"Mode change to {mode.value} was not accepted by hardware "
                f"(register still reads {actual_value}). Extension register "
                f"writes require the installer-level SPAN Modbus unlock."
            )

        _LOGGER.info("Operating mode changed to %s", mode.value)

    async def async_set_self_reserve_pct(self, pct: int) -> None:
        """Write the Self-Consumption reserve % directly to hardware
        register 15508 (SelfReserve) and verify the write stuck."""
        self._validate_pct(pct)
        await self._write_register(const.EXT_ADDR_SELF_RESERVE, pct)
        await asyncio.sleep(0.5)
        actual = await self._read_and_verify_register(const.EXT_ADDR_SELF_RESERVE)
        if actual != pct:
            raise FranklinWHWriteError(
                f"Self-Consumption reserve % write was not accepted by "
                f"hardware (register still reads {actual}%, wanted {pct}%). "
                f"Extension register writes require the installer-level "
                f"SPAN Modbus unlock."
            )

    async def async_set_tou_reserve_pct(self, pct: int) -> None:
        """Write the TOU reserve % directly to hardware register 15509
        (TouReserve) and verify the write stuck."""
        self._validate_pct(pct)
        await self._write_register(const.EXT_ADDR_TOU_RESERVE, pct)
        await asyncio.sleep(0.5)
        actual = await self._read_and_verify_register(const.EXT_ADDR_TOU_RESERVE)
        if actual != pct:
            raise FranklinWHWriteError(
                f"TOU reserve % write was not accepted by hardware "
                f"(register still reads {actual}%, wanted {pct}%). "
                f"Extension register writes require the installer-level "
                f"SPAN Modbus unlock."
            )

    @staticmethod
    def _validate_pct(pct: int) -> None:
        if not (0 <= pct <= 100):
            raise ValueError(f"Reserve percentage must be 0-100, got {pct}")

    # ------------------------------------------------------------------
    # Battery command (M704 manual battery charge/discharge control)
    # ------------------------------------------------------------------

    async def async_start_battery_charge(
        self, power_w: float, duration_s: Optional[float] = None
    ) -> None:
        """Command the battery to charge at the given power via M704."""
        if power_w <= 0:
            raise ValueError(f"power_w must be positive, got {power_w}")

        max_w = await self._read_charge_rate_max_w()
        pct = min(power_w / max_w * 100.0, 100.0) if max_w > 0 else 0.0
        await self._send_wsetpct_command(-pct)
        self._arm_watchdog(duration_s)
        _LOGGER.info(
            "Battery charge command sent: %.0fW (%.1f%% of %.0fW rating)",
            power_w, pct, max_w
        )

    async def async_start_battery_discharge(
        self, power_w: float, duration_s: Optional[float] = None
    ) -> None:
        """Command the battery to discharge at the given power via M704."""
        if power_w <= 0:
            raise ValueError(f"power_w must be positive, got {power_w}")

        max_w = await self._read_discharge_rate_max_w()
        pct = min(power_w / max_w * 100.0, 100.0) if max_w > 0 else 0.0
        await self._send_wsetpct_command(pct)
        self._arm_watchdog(duration_s)
        _LOGGER.info(
            "Battery discharge command sent: %.0fW (%.1f%% of %.0fW rating)",
            power_w, pct, max_w
        )

    async def async_stop_battery_command(self, handshake_wait_s: float = 1.0) -> None:
        """Release the active M704 command and restore native mode scheduling."""
        self._cancel_watchdog()

        await self._write_register(const.M704_ADDR_WSETMOD, const.WSETMOD_PERCENT)
        await self._write_register(const.M704_ADDR_WSETPCT, 0)
        if handshake_wait_s > 0:
            await asyncio.sleep(handshake_wait_s)

        await self._write_register(const.M704_ADDR_WSETENA, const.WSETENA_DISABLED)
        await self._write_register(const.M704_ADDR_WSETPCT, 0)

        _LOGGER.info("Battery command released; native mode scheduling resumed")

    async def async_get_battery_command_status(self) -> dict:
        """Read the current M704 remote control state."""
        m704 = await self._read_registers(const.M704_BASE, const.M704_COUNT)
        wset_ena = m704[const.M704_OFF_WSETENA] == const.WSETENA_ENABLED
        wset_mod = m704[const.M704_OFF_WSETMOD]
        wsetpct_sf = _to_signed16(m704[const.M704_OFF_WSETPCT_SF])
        wsetpct_raw = _to_signed16(m704[const.M704_OFF_WSETPCT])
        wset_pct = _apply_scale(wsetpct_raw, wsetpct_sf)
        return {
            "wset_ena": wset_ena,
            "wset_mod": wset_mod,
            "wset_pct": wset_pct,
            "wset_pct_raw": wsetpct_raw,
        }

    # --- Internal helpers for battery command ---

    async def _send_wsetpct_command(self, pct: float) -> None:
        """Execute the standard SunSpec 4-phase M704 command sequence."""
        sf_raw = await self._read_and_verify_register(const.M704_ADDR_WSETPCT_SF)
        sf = _to_signed16(sf_raw)
        pct_raw = int(round(pct / (10 ** sf)))

        await self._write_register(const.M704_ADDR_WSETENA, const.WSETENA_DISABLED)
        await asyncio.sleep(0.1)

        await self._write_register(const.M704_ADDR_WSETMOD, const.WSETMOD_PERCENT)
        await asyncio.sleep(0.1)
        await self._write_register(const.M704_ADDR_WSETPCT, _to_unsigned16(pct_raw))
        await asyncio.sleep(0.2)

        await self._write_register(const.M704_ADDR_WSETENA, const.WSETENA_ENABLED)
        await asyncio.sleep(0.5)

        actual_pct_raw = await self._read_and_verify_register(const.M704_ADDR_WSETPCT)
        actual_pct_raw_signed = _to_signed16(actual_pct_raw)
        actual_ena = await self._read_and_verify_register(const.M704_ADDR_WSETENA)

        if actual_ena != const.WSETENA_ENABLED or actual_pct_raw_signed != pct_raw:
            raise FranklinWHWriteError(
                f"M704 battery command was not accepted by hardware "
                f"(WSetEna={actual_ena}, WSetPct={actual_pct_raw_signed}, "
                f"expected WSetEna=1, WSetPct={pct_raw})."
            )

    async def _read_charge_rate_max_w(self) -> float:
        """Read M702.WChaRteMaxRtg (charge rate max rating, Watts)."""
        m702 = await self._read_registers(const.M702_BASE, const.M702_COUNT)
        sf = _to_signed16(m702[const.M702_OFF_W_SF])
        value = _apply_scale(m702[const.M702_OFF_WCHARTEMAXRTG], sf)
        self._cached_charge_rate_max_w = value
        self._cached_discharge_rate_max_w = _apply_scale(
            m702[const.M702_OFF_WDISCHARTEMAXRTG], sf
        )
        return value

    async def _read_discharge_rate_max_w(self) -> float:
        """Read M702.WDisChaRteMaxRtg (discharge rate max rating, Watts)."""
        m702 = await self._read_registers(const.M702_BASE, const.M702_COUNT)
        sf = _to_signed16(m702[const.M702_OFF_W_SF])
        value = _apply_scale(m702[const.M702_OFF_WDISCHARTEMAXRTG], sf)
        self._cached_discharge_rate_max_w = value
        self._cached_charge_rate_max_w = _apply_scale(
            m702[const.M702_OFF_WCHARTEMAXRTG], sf
        )
        return value

    def _get_charge_rate_max_w_cached(self) -> float:
        """Synchronous fallback used only inside async_get_status()."""
        return getattr(self, "_cached_charge_rate_max_w", 5000.0)

    def _get_discharge_rate_max_w_cached(self) -> float:
        """See _get_charge_rate_max_w_cached()."""
        return getattr(self, "_cached_discharge_rate_max_w", 5000.0)

    def _arm_watchdog(self, duration_s: Optional[float]) -> None:
        """Start (or replace) the software auto-release watchdog timer."""
        self._cancel_watchdog()
        if duration_s is not None and duration_s > 0:
            loop = asyncio.get_event_loop()
            self._watchdog_task = loop.create_task(self._watchdog_fire(duration_s))

    def _cancel_watchdog(self) -> None:
        task = getattr(self, "_watchdog_task", None)
        if task is not None and not task.done():
            task.cancel()
        self._watchdog_task = None

    async def _watchdog_fire(self, duration_s: float) -> None:
        try:
            await asyncio.sleep(duration_s)
            _LOGGER.warning(
                "Battery command watchdog timeout (%.0fs) reached - auto-releasing",
                duration_s
            )
            await self.async_stop_battery_command()
        except asyncio.CancelledError:
            pass
