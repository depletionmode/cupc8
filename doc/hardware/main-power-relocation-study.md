# Main input placement and routing study — red experiment

The isolated `codex/main-power-relocate-study` branch changes only the source placement wishes:
F1 to (25, 175) mm, U2 to (22, 168.5) mm at 180°, and R1 to
(19, 177) mm. J1, the six slot sockets and every mounting hole stay fixed.
`main.placement()` legalized those coordinates exactly, including
courtyard and designator clearances. U2's input now faces F1 and its
output faces the slot bus.

The pad-center distance from J1's nearest VBUS pad to F1:1 falls from
about 13.03 to 4.61 mm; F1:2 to U2:5 falls from about 13.89 to 5.17 mm.
The combined straight-line minimum is about 9.78 mm, versus 26.92 mm
at the saved placement. A hypothetical 2 mm outer trace, contracted to
80% width, over 9.78 mm at 115 °C and 24.9 µm copper would be about
5.73 mΩ. That arithmetic excludes the eFuse's fine-pitch escape,
connector return, via/barrel, solder and component contact resistance,
and any detour needed to clear other nets. It is not a routed result.

The first bounded build stopped at the old `_standby_preroute` placement
guard. This branch now uses relocation-specific locked geometry for the
C3-to-C5 5V_SYS trunk and U15 standby input. It retains the fixed slot
bus and U3 feeds, and skips the old salt-1 post-route repairs because
their coordinates no longer apply. The new F1-to-U2 and U2-to-C3
connections remain for the autorouter. The source-replayed board step
completes, with 272 GND pad vias. KiCad's DRC on the unrouted board has
no copper clearance violations; its 199 dangling vias and three
dangling tracks are expected until routing and plane fill.

Two bounded autoroute experiments did not produce an SES file. With one
ordering and a 90 s cap, each of three rounds timed out after the first
fanout pass, which left 415–417 SMD pins unrouted. A stronger run used
two orderings, 30 passes and a 300 s cap per ordering, with a 390 s
outer cap. Both first-round orderings stayed in fanout: after six to
seven passes they each reported 441 unrouted items, and neither
produced an SES file. The pipeline began a second round before the outer
cap stopped it. Reproduce the stronger trial from this branch with:

```sh
timeout 390s env CUPC8_OFFLINE=1 /usr/bin/python3 - <<'PY'
import sys
sys.path[:0] = ['hw/boards', 'hw/tools']
import main
main.ROUTE_PARALLEL = 2
main.ROUTE_TRIES = 1
main.ROUTE_TIMEOUT = 300
sys.argv = ['main.py', 'build/hw/main-relocate-route-long']
main.main()
PY
```

There is no routed board to measure, no zero-open result, and no
post-route DRC result. The eFuse fine-pitch escapes, connector contact
resistance, minimum finished via plating, and the fault temperature rise
also remain outside a demonstrated ≤20 mΩ input loop bound. This route
study stops here rather than treating pad proximity as a solved path.

This study demonstrates component placement space, not MB-005 closure.
The verified VBUS bypass is merged on `milestone-1` and is not replaced by
this unrouted relocation study.

## Local corridor replay audit

The `441 unrouted` figure above was a *fanout-stage* plateau, not a completed
autoroute result. The successful baseline route also remained at 426–427
unrouted in its seventh fanout pass, entered the autoroute stage with
468–471 items, and subsequently reduced that count. The 390-second trial
expired before the relocation entered autorouting; it cannot establish a
placement-specific detailed-routing deadlock. Each ordering began with 667
of 991 SMD pins needing fanout, within two of the baseline count.

On a copy of `build/hw/main-relocate-route-long/main.kicad_pcb`, a direct
locked F.Cu seed can connect J1 A4B9 to F1:1 without displacing J1 GND
vias or the SBU2 pad. Its waypoints (mm) are
`(27.6,180.95)→(27.6,179.6)` at 0.3 mm,
`→(27.6,178.5)` at 0.7 mm, then `→(25,177.1375)` at 1.0 mm.
Starting the 0.7 mm section at y=180.2 fails the 0.2 mm J1 SBU2
clearance by 0.0401 mm; waiting until y=179.6 clears it. The J1 GND
fanout via at (26.634,179.661) rules out a straight wide diagonal.

The same copied board can connect F1:2 to U2:5 with the current 0.3 mm,
2.0 mm eFuse stub and a direct 1.0 mm segment from (25,172.8625) to
(22.23,170.5). A second experiment replaces the stub with a 0.3 mm
segment ending (22.23,170.1), then uses 0.6 mm to (23.4,171.0) and
1.2 mm onward to F1:2. A uniform 1.2 mm path into U2 shorts PWR_EN;
0.7 mm on that last diagonal misses its clearance by 0.0012 mm. Both
the 1.0 mm and 0.6/1.2 mm segmented candidates have no KiCad copper,
mask, or shorting violations before zone fill. The baseline preroute
reported 499 unconnected items, 199 dangling vias and three dangling
tracks; the segmented seed reported 499, 199 and two respectively.
Those open/dangling counts are expected on an unrouted board and are not
a signoff result.

At 115 °C, 24.9 µm outer copper, 80% drawn width, 15 µm via wall and
1.76 mm board, `hw/power/copper.py` estimates the segmented seed at
**10.556 mΩ J1→F1 plus 11.532 mΩ F1→U2 = 22.089 mΩ positive copper**.
It idealizes pad copper yet charges track segments across those pads, so
this is a screening model, not a finished-copper upper or lower bound.
The existing 0.3 mm eFuse escape lies beside a second bar only 0.19 mm
away; a 0.20 mm gap/class and PWR_EN force a narrow local entry. The
1.0 mm paired placement shift discussed below cannot remove these necks.
Even using the earlier 3.46 mΩ scaled In1-only GND *scenario* would put
the segmented seed above 25.5 mΩ before connector contacts and solder.

The project placement legalizer accepts the smaller common shift
F1 `(25,176)` and U2 `(22,169.5)` at their existing rotations while R1
remains `(19,177)` and all sockets/holes stay fixed. That shortens the
nearest J1 VBUS-to-F1:1 pad-center line from 4.61 to about 3.83 mm;
the F1:2-to-U2:5 line remains 5.17 mm. The expected savings are under
1.0 mΩ even if the full 0.78 mm removed length were 1.0 mm-wide outer
copper at this corner. The shift alone therefore cannot bring the tested
22.089 mΩ positive path into the 7 mΩ positive allocation or the full
≤15 mΩ loop target. The large F1/U2 relocation remains the useful
geometry baseline, but its power route needs broad parallel copper and
shorter qualified pad entries, not just another millimetre of placement.

**Exact next bounded experiment:** set F1 `(25,176,90)` and U2
`(22,169.5,180)` in source, then replay a source-owned F.Cu seed on a
preroute-only build. Keep the J1 waypoints through `(27.6,178.5)` and
end at F1:1 `(25,178.1375)`. Shift the VBUS_F seed's F1/U2 waypoints
above by +1 mm in y, retaining the 0.3/0.6/1.2 mm widths. Preserve the
fixed J1 GND fanout and all current 5V_SYS and signal preroutes.
Update only the placement-dependent `_standby_preroute_relocated` guard,
the eFuse escape, and these two placement wishes. Add a second independent
path from J1 B4A9 through
DRC-clean B.Cu/In3 copper to F1:1 if a pad-adjacent via and USB signal
channel permit it; reject the candidate if the via or broad return
clearance fails. Run preroute KiCad DRC, then a normal complete autoroute
with at least enough wall time to finish fanout and one detailed pass.
Only after a zero-open, zero-violation filled route should the corner
network and assembled loop budgets be recomputed. A 390-second timeout
cannot answer this experiment. The present local seed and placement
shift are screening evidence; MB-005 stays red.
