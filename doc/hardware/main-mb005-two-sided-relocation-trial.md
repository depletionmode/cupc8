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
| Both J1 VBUS pads held at one ideal source potential → F1:1 | 5.466 mΩ |
| F1:2 → U2:5, with B.Cu branch | 10.397 mΩ |
| **A-side positive sum** | **16.600 mΩ** |
| **Ideal tied-pad positive sum** | **15.863 mΩ** |

The ordinary model fixes one J1 pad at a time. A separate optimistic solve
contracts both connector VBUS pad nodes to one ideal voltage source; this
assumes zero source-side contact imbalance and omits contact resistance.
Neither solve bounds actual sharing. The A-side sum leaves **3.400 mΩ**,
and even the ideal tied-pad sum leaves just **4.137 mΩ**
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
reach 50 mΩ before PCB copper. Even counting all four USB-C VBUS contacts
and all four GND contacts as separate, equally loaded 50 mΩ paths yields a
25 mΩ loop ceiling. Actual contact sharing, the mating plug and whether the
published number applies to each finger or tied contact group are not
bounded. At the eFuse's 3.21 A maximum current-limit value, these 25/50 mΩ
contact cases alone dissipate 258/515 mW. The connector's 80 °C maximum
operating temperature has no qualified fault-heating margin.

**Requirement decision:** retain the whole-loop ≤20 mΩ limit and keep MB-005
red. The fitted HRO public guarantee cannot establish it, regardless of
PCB route quality. For a 5 mΩ design margin, allocate no more than 4 mΩ
to the combined mated VBUS and GND contact groups, 7 mΩ to positive copper,
3 mΩ to GND copper and 1 mΩ to transitions/solder. That needs either a
connector and specified mating plug guaranteed at the assembled 4 mΩ
contact limit over temperature and life, or a controlled four-terminal
qualification of this exact connector pair. A connector replacement must
still fit the fixed J1 envelope and undergo a fresh full-board route.
Finished local copper/via minima and fault-temperature coupling also remain
unqualified.

A complete routed candidate must pass source replay, KiCad DRC, zero opens,
schematic parity, corner-aware filled-copper extraction and assembled loop
qualification before MB-005 can change status. This pre-route experiment
does not meet those gates.
