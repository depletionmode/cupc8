# Plotted profile containment audit — 2026-09-28

Verification row 4.9 requires an independent check of the plotted fabrication
package. The existing `gerberdrc.check_edge` measures copper-to-edge distance,
but a distance alone cannot distinguish copper inside the board from copper
outside it. `tools/fab_profile_containment.py` reconstructs the closed
Edge.Cuts profile from the plotted Gerber, then requires every plotted copper
feature and Excellon round/slot cut to be covered by that profile. It uses
the existing strict Gerber readers and validated board receipts. Arc edges
are chorded at 0.01 mm or finer; the existing copper-to-edge rule has at
least 0.20 mm observed clearance, much larger than that approximation.

All eight current receipt-bound boards pass this **additional** check:

| Board | Copper features inside | Excellon cuts inside |
| --- | ---: | ---: |
| main | 18,421 | 2,051 |
| cpu | 3,011 | 266 |
| gpu | 1,683 | 187 |
| io | 1,490 | 183 |
| storage | 1,731 | 221 |
| wifi | 940 | 196 |
| eink | 1,602 | 209 |
| system | 2,309 | 265 |

Run `python3 tools/fab_profile_containment.py` and
`python3 test/hw/test_fab_profile_containment.py`. The focused regression
accepts an inside flash and drill, and rejects an outside copper flash,
round hole, slot, and open profile.

This check does not close the fabrication gate. The seven card notches still
have 0.200 mm plotted copper-to-edge clearance against the 0.300 mm rule.
Complete minimum-neck coverage in filled copper and silkscreen and an
independent plotted text-height check remain absent. All 547 CPL rows still
need per-designator human placement, pin-one, polarity and rotation review;
the unsigned overlays and PDF are review aids, not approval.
