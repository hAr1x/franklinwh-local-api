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
Modbus register map and constant definitions for the FranklinWH aGate.

All register addresses below use "base-1" (PDU / raw Modbus) addressing,
NOT the "base-40000" convention. This matches how pymodbus's
read_holding_registers()/write_register() are normally invoked directly
against raw addresses (e.g. address=72 reads what some SunSpec tooling
would label "40072"). This was cross-validated against the
franklinwh-modbus reference project
(https://github.com/david2069/franklinwh-modbus).

Register groups:
    M701 (AC Measurement)      base=72,    len=121  (extends to Tmp_SF@40192)
    M713 (DER Storage Status)  base=1035,  len=7
    M714 (DER DC Measurement)  base=1042,  len=12   (covers DCW + scale factors)
    Extension (FranklinWH)     base=15500, len=17   (covers dispatch state @15516)

NOTE: All of these registers are READ-ONLY by default. Write access to
the FranklinWH extension registers (15507-15509) requires the
installer-level "SPAN Modbus" unlock (confirmed available on this
project's target hardware).
"""

# ---------------------------------------------------------------------------
# Connection defaults
# ---------------------------------------------------------------------------

DEFAULT_PORT = 502
DEFAULT_UNIT_ID = 0
DEFAULT_TIMEOUT_S = 10.0

# ---------------------------------------------------------------------------
# Model 701 - AC Measurement (grid-side telemetry)
# ---------------------------------------------------------------------------

M701_BASE = 72
M701_COUNT = 121

M701_OFF_CONN_ST = 3
M701_OFF_ALRM = 4
M701_OFF_DERMODE = 6
M701_OFF_W = 8
M701_OFF_LLV = 13
M701_OFF_LNV = 14
M701_OFF_HZ = 15
M701_OFF_TMP_AMB = 33
M701_OFF_TMP_CAB = 34

M701_OFF_A_SF = 111
M701_OFF_V_SF = 112
M701_OFF_HZ_SF = 113
M701_OFF_W_SF = 114
M701_OFF_PF_SF = 115
M701_OFF_VA_SF = 116
M701_OFF_VAR_SF = 117
M701_OFF_TOTWH_SF = 118
M701_OFF_TOTVARH_SF = 119
M701_OFF_TMP_SF = 120

CONN_STATE_DISCONNECTED = 0
CONN_STATE_CONNECTED = 1
CONN_STATE_FAULT = 2

CONN_STATE_NAMES = {
    CONN_STATE_DISCONNECTED: "Disconnected",
    CONN_STATE_CONNECTED: "Connected",
    CONN_STATE_FAULT: "Fault",
}

ALARM_BITS = {
    0: "GROUND_FAULT",
    1: "DC_OVER_VOLT",
    2: "AC_DISCONNECT",
    3: "DC_DISCONNECT",
    4: "GRID_DISCONNECT",
    5: "CABINET_OPEN",
    6: "MANUAL_SHUTDOWN",
    7: "OVER_TEMP",
    8: "OVER_FREQUENCY",
    9: "UNDER_FREQUENCY",
    10: "AC_OVER_VOLT",
    11: "AC_UNDER_VOLT",
    12: "BLOWN_STRING_FUSE",
    13: "UNDER_TEMP",
    14: "MEMORY_LOSS",
    15: "HW_TEST_FAILURE",
}

# ---------------------------------------------------------------------------
# Model 713 - DER Storage Status (battery capacity / SOC)
# ---------------------------------------------------------------------------

M713_BASE = 1035
M713_COUNT = 7

M713_OFF_WHRTG = 0
M713_OFF_WHAVAIL = 1
M713_OFF_SOC = 2
M713_OFF_SOH = 3
M713_OFF_STA = 4
M713_OFF_WH_SF = 5
M713_OFF_PCT_SF = 6

# ---------------------------------------------------------------------------
# Model 714 - DER DC Measurement (battery charge/discharge power)
# ---------------------------------------------------------------------------

M714_BASE = 1042
M714_COUNT = 20

M714_OFF_DCA = 5
M714_OFF_DCW = 6
M714_OFF_DCA_SF = 15
M714_OFF_DCV_SF = 16
M714_OFF_DCW_SF = 17
M714_OFF_DCWH_SF = 18
M714_OFF_TMP_SF = 19

# ---------------------------------------------------------------------------
# Model 702 - DER Capacity (nameplate ratings)
# ---------------------------------------------------------------------------

M702_BASE = 227
M702_COUNT = 44

M702_OFF_WMAXRTG = 0
M702_OFF_WCHARTEMAXRTG = 8
M702_OFF_WDISCHARTEMAXRTG = 9
M702_OFF_W_SF = 43

# ---------------------------------------------------------------------------
# Model 704 - DER Active Power Control (battery charge/discharge command)
# ---------------------------------------------------------------------------

M704_BASE = 318
M704_COUNT = 35

M704_OFF_WSETENA = 0
M704_OFF_WSETMOD = 1
M704_OFF_WSETPCT = 6
M704_OFF_WSETPCT_SF = 34

M704_ADDR_WSETENA = 318
M704_ADDR_WSETMOD = 319
M704_ADDR_WSETPCT = 324
M704_ADDR_WSETPCT_SF = 352

WSETENA_DISABLED = 0
WSETENA_ENABLED = 1

WSETMOD_PRIMARY = 0
WSETMOD_PERCENT = 0

# ---------------------------------------------------------------------------
# Model 1 - Common (device identification)
# ---------------------------------------------------------------------------

MODEL1_BASE = 4
MODEL1_COUNT = 66

MODEL1_OFF_MN = 0
MODEL1_OFF_MD = 16
MODEL1_OFF_VR = 40
MODEL1_OFF_SN = 48

# ---------------------------------------------------------------------------
# Undocumented high-resolution home load mirror
# ---------------------------------------------------------------------------

EXT_HOME_LOAD_HIRES_ADDR = 16000

# ---------------------------------------------------------------------------
# FranklinWH Extension Registers (15500+ proprietary block)
# ---------------------------------------------------------------------------

EXT_BASE = 15500
EXT_COUNT = 17

EXT_OFF_PV_TOTAL = 2
EXT_OFF_ONGRID_MODE = 7
EXT_OFF_SELF_RESERVE = 8
EXT_OFF_TOU_RESERVE = 9
EXT_OFF_TOU_DISPATCH = 16

EXT_ADDR_ONGRID_MODE = EXT_BASE + EXT_OFF_ONGRID_MODE
EXT_ADDR_SELF_RESERVE = EXT_BASE + EXT_OFF_SELF_RESERVE
EXT_ADDR_TOU_RESERVE = EXT_BASE + EXT_OFF_TOU_RESERVE

MAX_PLAUSIBLE_SOLAR_W = 25000
MAX_PLAUSIBLE_LOAD_W = 50000

NATIVE_MODE_EMERGENCY_BACKUP = 1
NATIVE_MODE_SELF_CONSUMPTION = 2
NATIVE_MODE_TOU = 3
NATIVE_MODE_MANUAL = 4

NATIVE_MODE_NAMES = {
    NATIVE_MODE_EMERGENCY_BACKUP: "Emergency Backup",
    NATIVE_MODE_SELF_CONSUMPTION: "Self-Consumption",
    NATIVE_MODE_TOU: "TOU",
    NATIVE_MODE_MANUAL: "Manual",
}

TOU_DISPATCH_MAP = {
    0: "Idle",
    1: "Home Loads",
    2: "Standby",
    3: "Solar Charging",
    4: "Grid Charging",
    5: "Grid Discharge",
    6: "Self Consumption",
    7: "Grid Export",
    8: "Grid Charge",
}
