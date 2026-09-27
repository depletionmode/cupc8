# Main board 5 V copper reinforcement trial

This is a **candidate**, not a fabrication release. The source-driven board
pipeline adopts the recorded salt-1 route, moves U2 to (11, 156) mm and C15
to (15.2, 153.5) mm, redraws their local connections, and adds three-layer
5V_SYS copper toward U3. The signal route and baseline release stay separate.

The complete isolated build passed ERC, schematic parity, KiCad DRC with zero
violations and zero unconnected items, Gerbers/drill, BOM/CPL, pincheck and
content-addressed board receipt. It used `CUPC8_OFFLINE=1`, so live LCSC
availability was not checked. The recorded SES/DSN pair was checked for
structural identity before import.

`python3 hw/power/main_copper_corner.py build/hw/main/main.kicad_pcb` gives:

| Scenario | U2:6 to R4:1 | F200, farthest slot | U3 buck, worst VIN pad |
| --- | ---: | ---: | ---: |
| 70 °C | 4.842 mΩ | 17.185 mΩ | 16.092 mΩ |
| 100 °C | 5.320 mΩ | 18.878 mΩ | 17.678 mΩ |

Both rows apply 80% of drawn trace width, 90% of ordered copper thickness,
a 20 µm via barrel and a 1.76 mm board. JLC publishes a ±20% trace-width
tolerance and the [JLC06161H-3313 stackup](https://jlcpcb.com/impedance)
specifies 1 oz outer / 0.5 oz inner copper. The 90% finished-copper figure
is an engineering allowance; a supplier minimum has not been obtained.
`hw/power/copper.py` contracts pad copper to ideal nodes and omits pours.
Its effective-resistance result is therefore a sensitivity estimate, not a
certified physical upper bound.

## Heat sensitivity

The existing THM-001 model reports 63.1 °C eFuse junction at its 2.62 A
minimum limit and 73.9 °C buck junction at the expanded six-slot load.
The expanded load calculation draws 2.431 A from 5V_SYS, of which 1.155 A
goes to the buck and 1.276 A to +5V loads. The narrow U2-to-R4 copper
contains a 2.2 mm, 0.3 mm trace followed by a 2.491 mm, 1.0 mm trace. At
2.62 A, 100 °C resistivity, 80% width, 90% copper thickness and an assumed
350 W/(m·K) thermal conductivity, these two pieces dissipate 44.9 mW and
15.2 mW. A one-dimensional series model with only the U2 end held at its
63.1 °C junction temperature and no cooling through the board gives a
33.7 °C rise, or 96.8 °C at R4's copper. This checks the local escape under
deliberately poor cooling, but does not bound heat from R4 itself.

**Thermal and return-path gates remain open.** The long +5V trunk, R4 body,
and GND plane are not in that one-dimensional model. The source-driven board
has GND fills, yet no calibrated GND current/temperature mesh or physical
minimum finished-copper thickness. The 100 °C copper row leaves 1.122 mΩ
before the 20 mΩ budget at the farthest slot. An independently bounded
conductor temperature, GND return heating and fabricated copper thickness
are needed before this trial can replace the baseline.
