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
and GND plane are not in that one-dimensional model. The 100 °C copper row
leaves 1.122 mΩ before the 20 mΩ budget at the farthest slot.

`main_ground_mesh.py` samples the saved In1 GND fill and solves a two-pitch
sheet-conductance mesh at 100 °C and 90% thickness. The U3 GND via to J1
connector pads is 2.076/1.985 mΩ at 0.5/0.25 mm pitch; the nearest J11
GND stitch via to J1 is 8.386/8.000 mΩ. The 4.4% and 4.6% mesh changes
are small compared with unknown pad/via contact effects. A one-barrel
20 µm-plated, 1.76 mm-long through via adds about 1.96 mΩ at 100 °C.
At the expanded load, U3 draws 1.155 A input and the largest single +5V
card load is about 0.81 A, so an In1-only return path plus one such barrel
would dissipate roughly 5.3 mW at U3 or 6.5 mW at J11. These currents do
not all flow through the same path. The F/B GND fills and other stitches
would add parallel routes, but this mesh cannot certify their contacts.
The deliberately narrow 2 mm-corridor raster path from U3 to J1 is
19.62 mΩ in In1 alone before vias, showing the sensitivity to a local
neck or poorly represented thermal relief.

The move separates U2 from U3 by about 7 mm, and puts U2 4 mm from R4
instead of about 10.6 mm. C15 is 4.9 mm from U2; it has no significant
self-heating, but the closer R4 0 Ω link could warm U2. At the expanded
1.276 A +5V load and the budgeted 50 mΩ R4 maximum, R4 could dissipate
81 mW. Neither R4-to-U2 thermal transfer nor the GND plane temperature
field is calibrated. Thus the existing 63.1 °C eFuse and 73.9 °C buck
junction estimates cannot simply be reused as a proven copper boundary.

This trial can replace the baseline only after the supplier gives a minimum
finished outer/inner copper thickness and via-barrel plating for the ordered
stackup, and a thermal measurement or calibrated board-level model bounds
R4-to-U2 coupling, the far +5V trunk, GND return/pad contacts, and conductor
temperature under the expanded load. The 100 °C scenario is a useful design
margin check, not evidence that the conductors stay below 100 °C.

## Isolated slot-bus trial (source change, not released)

`hw/boards/main_power_trial5.py` is called after SES import and the U2/C15
relocation. It widens the U2:6-to-R4:1 F.Cu diagonal from 1.0 to 1.5 mm,
adds a 7.5 mm In4.Cu +5V trunk from the first slot at y=40.52 mm to
y=149 mm, and adds a 4.5 mm F.Cu trunk at x=2.75 mm with 1 mm taps at both
ends. Exact route and via guards reject an unexpected placement. Applying
it after import leaves the saved DSN/SES input unchanged. The old baseline
and its fabrication receipt remain separate.

For a direct replay from the source-driven `build/hw/main/main.kicad_pcb`,
load that board with `pcbnew.LoadBoard`, call
`main_power_trial5.reinforce_slot_5v(board)`, refill with
`pcbnew.ZONE_FILLER(board).Fill(board.Zones())`, and save it beside copies of
the main project's `main.kicad_pro` and `fp-lib-table`. Running
`kicad-cli pcb drc --format json --severity-all` on that replay gave **zero
violations and zero unconnected items**. Without the copied project library
table, KiCad reported 136 footprint-library warnings but no copper errors.
The trial is not yet a full source-driven fabrication receipt.

The modeled U2:6 → R4:1 5V_SYS path plus R4:2 → F200:1 +5V path is:

| Copper temperature | Via plating | U2 to R4 | R4 to F200 | Sum |
| --- | ---: | ---: | ---: | ---: |
| 70 °C | 20 µm | 4.745 mΩ | 12.668 mΩ | 17.412 mΩ |
| 100 °C | 20 µm | 5.212 mΩ | 13.916 mΩ | 19.128 mΩ |
| 100 °C | 15 µm | 5.287 mΩ | 14.288 mΩ | 19.574 mΩ |
| 115 °C | 20 µm | 5.446 mΩ | 14.540 mΩ | 19.986 mΩ |
| 115 °C | 15 µm | 5.524 mΩ | 14.928 mΩ | **20.452 mΩ** |

These scenarios apply 80% of drawn trace width, 24.9 µm outer copper,
11.4 µm inner copper, and a 1.76 mm board. The thicknesses are illustrative
processed-copper sensitivities, **not a qualified JLCPCB minimum**. JLC's
[copper-weight guide](https://jlcpcb.com/help/article/jlcpcb-copper-weight)
states nominal weights and the [stackup tool](https://jlcpcb.com/impedance)
lists design thicknesses of 35 µm outer and 15.2 µm inner for this stackup;
neither establishes a binding minimum for this order. JLC's
[plating article](https://jlcpcb.com/blog/pcb-plating-thickness) discusses
approximately 20 µm average Class 2 hole-wall copper, but does not certify
this lot. Widening the existing 7.5 mm trunks to 8 mm failed KiCad DRC on
edge clearance and slot IRQ contacts, so the clean geometry stops at 7.5 mm.

This remains **MB-005 open**. The resistance graph idealizes pads and omits
their solder joints and zone copper, so 19.128 mΩ is not a guaranteed upper
bound. The narrow U2 output escape, R4 body, GND return, and far trunk lack
a calibrated thermal bound. A deliberately poor-cooling 1D calculation for
the U2 neck and diagonal alone can place the R4-side copper above 100 °C at
the 2.62 A eFuse limit; branching at the neck's via and board conduction
could reduce that rise, but their effect has not been measured. Before merge,
obtain order-specific minimum finished outer/inner copper and via plating
(or lot microsection acceptance), then bound copper temperature and pad/GND
contact resistance under the expanded load and current-limit condition.
