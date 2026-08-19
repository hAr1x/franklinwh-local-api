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
Data models for franklinwh_local_api.

Contains:
    OperatingMode      - enum for the FranklinWH aGate operating mode
                          register (15507). Values 1, 2, 3 are the three
                          "real" user-selectable modes (Emergency Backup,
                          Self-Consumption, TOU). Values 0 (Standby) and
                          4 (Manual) exist in hardware but are read-only
                          states, not valid write targets.
    FranklinWHStatus   - a full point-in-time snapshot of the system
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional


class OperatingMode(Enum):
    """Native FranklinWH aGate operating modes.

    These map 1:1 to Modbus extension register 15507 (OnGridMode).

    Register value reference:
        0 = STANDBY      - not a user-selectable mode; observed as an
                            idle/uninitialized state. NOT a valid write
                            target.
        1 = EMERGENCY_BACKUP
        2 = SELF_CONSUMPTION
        3 = TOU
        4 = MANUAL        - not a user-selectable mode via this API; a
                            hardware handoff/wait state.
                            NOT a valid write target.

    Only EMERGENCY_BACKUP, SELF_CONSUMPTION, and TOU (values 1, 2, 3)
    are the three "real" user-facing modes exposed by the FranklinWH
    app and supported as write targets via async_set_operating_mode().
    Values 0 and 4 are read-only states - attempting to write them
    raises FranklinWHWriteError.
    """

    STANDBY = "standby"
    EMERGENCY_BACKUP = "emergency_backup"
    SELF_CONSUMPTION = "self_consumption"
    TOU = "tou"
    MANUAL = "manual"

    @classmethod
    def from_register_value(cls, value: int) -> "OperatingMode":
        """Convert the raw 15507 register value into an OperatingMode."""
        mapping = {
            0: cls.STANDBY,
            1: cls.EMERGENCY_BACKUP,
            2: cls.SELF_CONSUMPTION,
            3: cls.TOU,
            4: cls.MANUAL,
        }
        if value not in mapping:
            raise ValueError(f"Unknown native operating mode register value: {value}")
        return mapping[value]

    def to_register_value(self) -> int:
        """Convert this OperatingMode back into the raw 15507 register value."""
        mapping = {
            OperatingMode.STANDBY: 0,
            OperatingMode.EMERGENCY_BACKUP: 1,
            OperatingMode.SELF_CONSUMPTION: 2,
            OperatingMode.TOU: 3,
            OperatingMode.MANUAL: 4,
        }
        return mapping[self]


@dataclass
class FranklinWHStatus:
    """A complete point-in-time snapshot of the FranklinWH aGate system,
    read entirely over local Modbus TCP.

    All power values are in Watts. Positive/negative sign conventions are
    normalized so that callers never need to think about raw hardware
    sign quirks:
        - battery_charging_w / battery_discharging_w are always >= 0
        - grid_import_w / grid_export_w are always >= 0

    NOTE ON BATTERY POWER SIGN:
        The underlying M714.DCW register's sign convention on
        FranklinWH hardware inverts the SunSpec standard: NEGATIVE =
        charging, POSITIVE = discharging.
    """

    battery_capacity_wh: float
    battery_energy_wh: float
    battery_soc_pct: float
    battery_soc_pct_rounded: float
    battery_soh_pct: float

    battery_power_w: float
    battery_charging_w: float
    battery_discharging_w: float

    grid_power_w: float
    grid_import_w: float
    grid_export_w: float
    grid_connected: bool
    grid_voltage_ln_v: float
    grid_voltage_ll_v: float
    grid_frequency_hz: float

    solar_power_w: float
    home_load_w: float

    operating_mode: OperatingMode
    self_reserve_pct: int
    tou_reserve_pct: int
    tou_dispatch_state: Optional[str] = None
    tou_dispatch_raw: Optional[int] = None

    ambient_temp_c: float = 0.0
    cabinet_temp_c: float = 0.0

    alarms: List[str] = field(default_factory=list)
    alarm_active: bool = False
    raw_alarm_bits: int = 0

    battery_command_active: bool = False
    battery_command_charge_w: float = 0.0
    battery_command_discharge_w: float = 0.0
    battery_command_pct_raw: int = 0


@dataclass
class FranklinWHDeviceInfo:
    """Device identification, read once from SunSpec Model 1 (Common)."""

    manufacturer: str
    model: str
    firmware_version: str
    serial_number: str
