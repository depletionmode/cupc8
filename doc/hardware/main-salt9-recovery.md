# Main board salt-9 SES recovery

The completed salt-9 Freerouting session is a content-bound alternative route
for the main board. Its source DSN SHA-256 is
`10cbd97dc043be4d4b86715b286c6924763b697cb44ab191190d82dd30072316`;
its SES SHA-256 is
`c7853762fe222520e2bfeb048cd8964fa8c75305e05383ddfc95092b897158ab`.
The source preroute PCB SHA-256 is
`71e33e9f197487dc417f5a0e2bd47bb10e12ab347ce5d8bbf29493814e388e61`.

Rebuild it through the source-owned replay path with `sesreplay.py snapshot`
and `main.py --replay-manifest`, as described in `main-ses-replay.md`. The
salt-9 postroute branch is selected only by that manifest. It verifies one
7.5 mm `/+5V` tap per B.Cu, In2.Cu and In3.Cu at each end of the slot bus,
then narrows those six short taps to 1 mm. It also verifies U3 pad 2 and adds
the missing short F.Cu GND trace and via at (38.3, 160.0). The salt-1 edits
are absent from this SES and are not applied to it.

The SES import changed the free endpoint of a short bus tap across repeated
source replays, even with the same captured SES and canonical DSN hashes.
Observed x coordinates were 3.4, 4.2 and 5.0 mm. The guard therefore allows
only that measured x range while still requiring the exact start point, y,
net, 7.5 mm width, layer, and exactly one tap per layer. The final KiCad DRC
and connectivity checks are authoritative after import and zone fill.

The isolated source replay produced a complete board, Gerbers, BOM/CPL,
render, and `evidence.json`; strict KiCad DRC and schematic parity both had
zero findings. `boardcheck.py main drc` passed against its receipt. This is
layout closure only. The input positive copper sensitivity at 115 °C,
15 µm via plating and 80% nominal trace width is 37.129 mΩ for J1→F1 plus
35.931 mΩ for F1→U2, or **73.060 mΩ before ground, contacts, zones or fault
thermal limits**. MB-005's 20 mΩ loop target is therefore not met by this
route and remains red.

## Receipt-bound input heating check (2026-09-28)

The completed DRC-clean main-board receipt copied from `milestone-1` has
PCB SHA-256 `ada8c6fe16af74c4a75cca67dab2989fda286a35da70fa92e9d700a1b25fc30e`,
netlist SHA-256 `995ba33de0e5dfe3c83a928318f3b039767c58ad91d3d27219696379437f422f`,
and order SHA-256 `230fc5562b8c8697009adc22b33044df4c3e416f0ede71235340f9e8b5d42e66`.
`python3 hw/power/main_input_heat.py build/hw/main` validates the complete
content receipt and J1→F1→U2 pin nets before extracting resistance. At the
modeled 115 °C corner, the two positive segments are 37.129 and 35.931 mΩ.
At the 3.213 A eFuse maximum current-limit corner, they imply **234.7 mV**
positive-path drop and **754 mW instantaneous** copper heat. For an ambient
of 40 °C, holding an assumed uniform copper maximum of 115 °C would require
at most **99.4 °C/W effective rise per watt** for that aggregate heat alone.
This is a screening requirement, not a measured board thermal resistance or
a local neck temperature; other board heat and the fault time history are
excluded. The current limit is derived from the fitted RILM and the
[TPS25947 datasheet](https://www.ti.com/lit/ds/symlink/tps25947.pdf).

The 115 °C resistance calculation assumes 80% of drawn trace width, 24.9/11.4
µm outer/inner copper, 15 µm via wall and 1.76 mm board thickness. JLCPCB
publishes [±20% trace-width tolerance and nominal multilayer copper
options](https://jlcpcb.com/capabilities/Capab), but the selected local
finished-copper and via-wall minima have not been accepted as fabrication
limits. The graph also omits positive-net fills and idealizes pad copper, so
73.060 mΩ is a modeled scenario rather than a guaranteed lower bound on the
fabricated board. The check explicitly fails both its 20 mΩ positive-copper
screen and the absent fabrication, return/contact and coupled thermal
evidence. A lower extracted resistance cannot clear those three evidence
failures. MB-005 remains red.
