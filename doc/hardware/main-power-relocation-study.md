# Main input placement and routing study — red experiment

This branch deliberately changes only the source placement wishes:
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
The verified VBUS bypass stays on `codex/main-power-next-sol` and is not
replaced by this unrouted branch.
