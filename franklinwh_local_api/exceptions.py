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
Exceptions used by franklinwh_local_api.
"""


class FranklinWHLocalApiError(Exception):
    """Base exception for all franklinwh_local_api errors."""


class FranklinWHConnectionError(FranklinWHLocalApiError):
    """Raised when the Modbus TCP connection to the aGate cannot be
    established or is lost during a read/write operation."""


class FranklinWHWriteError(FranklinWHLocalApiError):
    """Raised when a write operation (mode change, reserve % change) fails
    at the protocol level, or when a write is rejected/ignored by the
    aGate firmware (verified via read-back)."""
