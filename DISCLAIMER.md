# Disclaimer

## No affiliation with FranklinWH

This project is an independent, community-developed piece of software.
The author(s) of `franklinwh_local_api` have **no affiliation,
partnership, sponsorship, or endorsement relationship of any kind**
with FranklinWH Technologies Co., Ltd, its subsidiaries, or any of its
official products, apps, or cloud services. This project was not
created, reviewed, or approved by FranklinWH.

"FranklinWH" and any related product names are trademarks of their
respective owner(s). They are used here solely to describe
interoperability/compatibility with that hardware, not to claim any
official relationship.

## Reverse-engineered / unofficial register map

The Modbus register addresses, scale factors, sign conventions, and
behaviors documented and used by this project were derived through
independent testing against live hardware, cross-referencing publicly
available open-source projects, and analysis of undocumented registers
that are not part of any officially published FranklinWH interface
specification.

FranklinWH may change, restrict, or remove any of these registers, or
alter their behavior, in any firmware update, without notice and
without any obligation to this project. There is **no guarantee** that
the information here is accurate, complete, or will continue to work
on any given firmware version, past, present, or future.

## Use at your own risk

This software interacts directly with your FranklinWH aGate hardware
over Modbus TCP, including issuing commands that can change your
battery's operating mode and directly command battery charge/discharge
power. **You use this software entirely at your own risk.**

The author(s) make **no warranty of any kind** and accept **no
liability** for any consequences of using this software, including but
not limited to:

- Damage to your battery, aGate, inverter, or any connected equipment
- Data loss or incorrect data
- Voiding of any manufacturer warranty
- Unexpected energy bills, grid import/export behavior, or loss of
  backup power during an outage
- Any other direct, indirect, incidental, or consequential damages

This project is licensed under the GNU General Public License v3.0 or
later, which itself explicitly disclaims all warranties (see sections
15 and 16 of [LICENSE](LICENSE)). This disclaimer supplements, and does
not replace, those license terms.

**If you are not comfortable with these risks, do not use this
software.**
