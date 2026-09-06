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
franklinwh_local_api
=====================

A lightweight, fully local (LAN-only) async Python client for the
FranklinWH aGate gateway, communicating directly over Modbus TCP.

This package intentionally does NOT depend on the FranklinWH cloud API.
Everything it does works entirely on the local network, with no account
credentials and no internet access required.

Public API:
    FranklinWHLocalClient  - the main async client class
    FranklinWHStatus       - dataclass describing a full system snapshot
    FranklinWHDeviceInfo   - dataclass describing device identification
                             (manufacturer/model/firmware/serial), read
                             once via async_get_device_info()
    OperatingMode          - enum of the three native aGate operating modes
"""

from .client import FranklinWHLocalClient
from .exceptions import (
    FranklinWHConnectionError,
    FranklinWHLocalApiError,
    FranklinWHWriteError,
)
from .models import FranklinWHDeviceInfo, FranklinWHStatus, OperatingMode

__all__ = [
    "FranklinWHConnectionError",
    "FranklinWHDeviceInfo",
    "FranklinWHLocalApiError",
    "FranklinWHLocalClient",
    "FranklinWHStatus",
    "FranklinWHWriteError",
    "OperatingMode",
]

__version__ = "0.1.1"
