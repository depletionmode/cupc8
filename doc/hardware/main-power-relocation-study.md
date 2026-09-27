# Main input placement study — unrouted experiment

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

The bounded build command
`timeout 120s env CUPC8_OFFLINE=1 /usr/bin/python3 hw/boards/main.py build/hw/main-relocate`
completed schematic, ERC and netlist generation, then stopped in the
board step with `_standby_preroute: the eFuse's neighbours have moved; lay
its power copper again`. The saved salt-1 route also has coordinate
guards in `_five_volt_bus`, `_finish_route`, `main_power_reinforce.py` and
both trial reinforcement modules. A valid placement move therefore needs
new eFuse/standby preroutes, a new slot and buck feed, a complete
autoroute, then schematic parity, DRC/open checks and an input/return
resistance and thermal audit. No such routed board exists on this branch.

This study demonstrates component placement space, not MB-005 closure.
The verified VBUS bypass stays on `codex/main-power-next-sol` and is not
replaced by this unrouted branch.
