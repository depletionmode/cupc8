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
tracks. The source-owned
salt-9 DSN for a single no-optimizer route has SHA-256
`c72cbe94baf2465d80f825bb9deb8949e7a77c568cab86e8e27be6c58cf54a53`.
Freerouting completed 20 passes in 1 h 07 min with its optimizer disabled.
Its final router report had 12 incomplete connections and 14 fixed-rule
violations. The saved `route-9.ses` SHA-256 is
`0afda1eed4962fc27357b921878584712105a126445608e02e266b7d95ea92d2`;
the route log SHA-256 is
`6c8c9a0e1b42e218b638548adfc001a98aa4a809137a7ab02d13d64ada4b4a31`.
Reproduce the diagnostic KiCad checks and corner scenarios with:

```sh
python3 hw/power/main_mb005_route_review.py \
  --preroute build/hw/main-mb005-preroute-d \
  --route build/hw/main-mb005-route-one \
  --out build/hw/main-mb005-route-review
```

The review refuses a mismatched source PCB or DSN and creates no receipt.
After SES import, source-side finishing and zone fill, KiCad reports **four
opens, ten DRC violations and zero schematic parity findings**. The four
opens are:

| Net | Disconnected items |
| --- | --- |
| `/GND` | F.Cu and In1.Cu ground zones remain separate. |
| `/+5V` | In3.Cu track at `(14.0,13.25)` to via at `(66.3182,8.8565)`. |
| `/5V_SYS` | U2 F.Cu output stub at `(21.74,170.0)` to the C3 trunk at `(11.0,162.0)`. |
| `/SLOT5_PROG_n` | J15.A18 at `(31.0,110.35)` to R605.2 at `(15.944,126.12)`. |

The ten DRC findings are two `/CPU_A2` F.Cu tracks at `(90.05,51.75)`
and `(91.0892,51.75)` that are 0.075 mm wide against a 0.100 mm minimum;
three `/+5V` 7.5 mm wide south-edge taps at `(4.5,40.52)` on B.Cu,
In2.Cu and In3.Cu with zero clearance against the 0.30 mm edge rule;
two connection-width findings on those same `/CPU_A2` tracks near U7 pad 24;
two dangling F.Cu stubs on `/5V_SYS` at `(21.74,170.0)` and `/PWR_EN`
at `(22.91,170.9)`; and one dangling `/+5V` via at
`(66.3182,8.8565)`. This is a red layout trial. No route repair is
attempted after these findings because the fitted contact guarantee already
prevents whole-loop certification.

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
solder under the 20 mΩ loop requirement. For this relocated board, an
In1.Cu-only return mesh from the U2 GND via at `(19.89,169.77)` to the fixed
J1 GND pads gives **2.671, 2.395, 2.284, 2.250 mΩ** at 0.5, 0.25, 0.125
and 0.0625 mm mesh spacing, respectively, with 115 °C and 11.4 µm inner
copper. The two finest meshes differ by 1.5%. This calculation excludes
the GND zone open, via and pad resistance, thermal spokes, F.Cu/B.Cu pours
and temperature coupling. It is a single-plane scenario, not a bound on the
assembled return. The A-side positive sum plus this single-plane scenario
is 18.850 mΩ, leaving only 1.150 mΩ for every omitted term under the
20 mΩ limit. Even an ideal zero-ohm return and
contacts would leave this trial above the proposed 15 mΩ design target; the
20 mΩ limit has little unallocated budget. The local
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

### Quantified contact qualification blocker

The source netlist maps J1's two merged VBUS solder pads, `A4B9` and
`B4A9`, to `/VBUS`, and its two merged signal-ground pads, `A1B12` and
`B1A12`, to `/GND`. Each merged pad names two USB-C fingers. This gives a
*generous* four independent mated fingers on each rail, assuming the mating
plug connects and shares current across all of them. The shell hold-downs
are not counted as a guaranteed power return. The [HRO TYPE-C-31-M-12
product page](https://en.krhro.com/Product-Details/726.html) publishes
`≤50 mΩ` contact resistance but gives no bound for the complete mated
VBUS-plus-GND groups with the selected plug, temperature and life. The
following four-finger calculation is a conditional sensitivity, not a
claim that HRO guarantees individual or equal-sharing paths.

For four equal contacts per rail at `r` mΩ each, their ideal loop
contribution is `r/4 + r/4 = r/2`. The public 50 mΩ value permits the
illustrative `r = 50 mΩ` corner: **25 mΩ from mated contacts alone**, with
zero board copper, zero solder and zero plug wiring. It already exceeds
the 20 mΩ loop ceiling by 5 mΩ. With the trial's A-side positive copper
and finest In1-only return scenario, the arithmetic becomes
`16.600 + 2.250 + 25.000 = 43.850 mΩ`, before all omitted terms. Two
conducting fingers per rail would give 50 mΩ of contacts and a
`68.850 mΩ` illustrative total. These are possible high-resistance
corners under the published rating, not measured resistance of a unit.

Conversely, with four equally loaded fingers per rail, the relocated
trial's `16.600 + 2.250 = 18.850 mΩ` copper scenario leaves at most
**1.150 mΩ combined contact resistance**, even granting ideal solder,
pad/via interfaces and all omitted copper. It would require
`r ≤ 2.300 mΩ` for *each* of the eight mated fingers. This is about
21.7 times tighter than the public 50 mΩ figure. Even the optimistic
15.863 mΩ tied-VBUS-pad solve leaves only 1.887 mΩ for the combined
contact groups after the 2.250 mΩ return scenario, or
`r ≤ 3.774 mΩ` per equally loaded finger. The In1-only return is not a
bound; including other GND layers could reduce its copper contribution,
while real barrels, spokes, solder and contact imbalance consume more
budget. No change to F1/U2 placement or PCB copper can establish the
specified *assembled* 20 mΩ maximum from the fitted connector's public
data. Obtain a qualified mated-group maximum or substitute and qualify
a suitable connector pair before treating further routing as closure.

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
qualification before MB-005 can change status. This completed diagnostic
replay does not meet those gates. The trial remains isolated and red.
