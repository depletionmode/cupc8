# MB-005 two-sided input relocation trial — red

This isolated source trial moves F1 to `(25,175,90)` mm, U2 to
`(22,170,180)` mm and R1 to `(19,177,0)` mm. The placer accepts these
positions exactly. J1, all card sockets and all mounting holes retain their
source positions. Locked F.Cu paths connect each J1 VBUS pad toward F1:1 and
F1:2 to the eFuse input escape; two B.Cu branches and five new through vias
give the short input path a parallel conductor. This is a trial of routing
space, not an approved board change.

The generated pre-route PCB
`build/hw/main-mb005-preroute-d/main.kicad_pcb` has SHA-256
`d29d7b76c63eaa45260e5ba0abe5ca7bf551d0feb310e6f2fbcece69e9565362`.
KiCad's pre-route check reports **zero copper-clearance violations** and
499 expected unconnected items, 199 dangling fanout vias and two dangling
tracks. It has neither a completed route nor post-fill DRC. The source-owned
salt-9 DSN for a single no-optimizer route has SHA-256
`c72cbe94baf2465d80f825bb9deb8949e7a77c568cab86e8e27be6c58cf54a53`.

At 115 °C, 24.9/11.4 µm outer/inner copper, 80% effective drawn width,
15 µm via wall and 1.76 mm board, the track/via sensitivity model gives:

| Positive leg | Resistance |
| --- | ---: |
| J1 A4B9 → F1:1, with B.Cu branch | 6.203 mΩ |
| J1 B4A9 → F1:1 | 20.165 mΩ |
| F1:2 → U2:5, with B.Cu branch | 10.397 mΩ |
| **A-side positive sum** | **16.600 mΩ** |

The model fixes one J1 pad at a time and does not bound current sharing
between mated contacts. Even the lower A-side sum leaves only **3.400 mΩ**
for all GND copper, via/pad transitions, both mated contact groups and
solder under the 20 mΩ loop requirement. The prior In1-only return *scenario*
was about 3.46 mΩ at this corner before its via and pad contact, so this
candidate lacks defensible margin even if full routing passes. The local
0.3 mm eFuse escape and the adjacent PWR_EN pad are binding: shortening the
escape by 0.3 mm and widening the adjacent feed produced a measured
0.0581 mm clearance against the 0.150 mm rule and was discarded.

The [fitted connector's manufacturer page](https://en.krhro.com/Product-Details/726.html)
states a maximum contact resistance of 50 mΩ. If two contacts per rail each
reach that ceiling and share perfectly, their VBUS plus GND contribution can
reach 50 mΩ before PCB copper. Actual contact sharing and the mating plug
are not bounded. The assembled loop therefore cannot be certified to 20 mΩ
from the public part limit; it needs a qualified lower contact bound or a
different connector/loop requirement. Finished local copper/via minima and
fault-temperature coupling also remain unqualified.

A complete routed candidate must pass source replay, KiCad DRC, zero opens,
schematic parity, corner-aware filled-copper extraction and assembled loop
qualification before MB-005 can change status. This pre-route experiment
does not meet those gates.
