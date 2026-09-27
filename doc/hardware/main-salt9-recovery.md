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
