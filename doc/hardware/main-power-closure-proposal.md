# MB-005 input loop: corrective design target

Status: **proposal, not a routed or qualified board**. The current clean
input bypass on `codex/main-power-next-sol` is 18.610 mΩ from J1 VBUS to
F1:1 and 48.247 mΩ from F1:2 to U2:5 at the 115 °C sensitivity corner.
The 66.858 mΩ positive sum alone exceeds the specified ≤20 mΩ VBUS/GND
loop. Its 0-violation, 0-open source replay does not qualify its copper
thickness, contacts, or conductor temperatures. The isolated F1/U2
relocation study places F1 at (25,175) mm and U2 at (22,168.5) mm with
clear courtyards, but its bounded autoroute did not finish; it supplies
placement space, not a new electrical result.

## Proposed sign-off budget

For a useful 5 mΩ margin, target **≤15 mΩ total** at the hottest
qualified condition, including the mated connector and both rails. The
PTC and eFuse *internal* resistances belong to the separate supply-drop
model and are excluded from this PCB/connector loop limit.

| Series element | Target maximum | Required evidence |
| --- | ---: | --- |
| J1 VBUS pads → F1:1 plus F1:2 → U2:5, routed copper | 7 mΩ | Filled-board, corner-aware extraction with all pad and via necks |
| U2 GND via/pad network → both J1 GND pads, routed copper | 3 mΩ | Multi-layer return extraction including spoke geometry |
| Solder, pad interfaces and other unmodeled transitions | 1 mΩ | Four-terminal assembled-board bound or calibrated extraction |
| Both mated VBUS and GND contact groups combined | 4 mΩ | Guaranteed or qualified four-terminal maximum at temperature and life |
| **Total** | **15 mΩ** | **5 mΩ below MB-005's 20 mΩ ceiling** |

The contact row means ≤4 mΩ for the *combined* VBUS plus GND contact
groups, including current sharing and the specified mating plug. If each
rail uses two independent contacts, a sufficient individual maximum is
4 mΩ per contact: each pair is then ≤2 mΩ. The fitted HRO
TYPE-C-31-M-12 public maximum is 50 mΩ **per contact**. Even two ideal
50 mΩ contacts per rail give a 50 mΩ loop ceiling before copper. The
public rating therefore cannot substantiate this budget. If MB-005 is
interpreted to exclude contacts, record that interpretation explicitly;
the current positive copper still fails, and the proposed copper plus
transition target would be ≤11 mΩ.

## Copper geometry to prototype

Keep J1, socket rows and mounting holes fixed. Use the legal F1/U2/R1
neighbourhood from the relocation study, then reroute the whole board.
The pad-centre path through F1 has a 9.78 mm straight-line minimum,
versus 26.92 mm in the saved placement. Reserve an uninterrupted input
corridor on F.Cu and B.Cu from both J1 VBUS pads to F1:1, then from F1:2
to U2:5. Use 2 mm or broader drawn outer-layer copper where clear, with
at least four well-spaced, DRC-clean 0.3 mm drill vias per transition
between layers. Preserve the J1 GND fanout and plated hold-downs; widen
or move local signal/standby routes rather than deleting return vias.
Bring broad copper as close to U2's high-current IN bar as QFN clearance
allows, and keep its 0.3 mm escape at 0.5 mm or shorter if legal. The
existing 1.8 mm by 0.3 mm input neck alone is 7.03 mΩ in the harsh
scenario, exhausting the proposed positive budget.

These dimensions are *screening constraints*, not a claim that the route
will fit. At 115 °C, 80% drawn width and 24.9 µm finished outer copper,
the 9.78 mm straight line in a single 2 mm trace is about 5.73 mΩ. Two
identical full-length outer traces in parallel would halve that idealized
value to 2.87 mΩ. A 15 µm plated 0.3 mm drill via over 1.76 mm is about
2.77 mΩ; four in parallel at each of two transitions add about 1.39 mΩ.
Shortening the 0.3 mm U2 neck from 1.8 to 0.5 mm would lower its own
estimate from 7.03 to 1.95 mΩ. Those optimistic pieces already sum to
roughly 6.21 mΩ before detours, pad spreading and nonuniform sharing.
The 7 mΩ positive allocation is consequently demanding; route and
extract before selecting copper dimensions or claiming margin.

For GND, use at least two connected planes/outer pours and multiple
J1/U2 stitches, with controlled solid or characterized thermal spokes.
The saved *In1-only* mesh is 2.410 mΩ at 100 °C and 90% of nominal inner
copper; scaling to 115 °C and 11.4 µm is about 3.46 mΩ **before** a
barrel or pad contact. One 15 µm barrel adds about 2.77 mΩ. The 3 mΩ
return allocation therefore requires measured parallel paths; an
In1-only estimate cannot pass it.

## Fabrication and thermal evidence

The 115 °C extraction corner currently assumes ≥24.9 µm finished outer
copper, ≥11.4 µm inner copper, ≥15 µm minimum plated via wall,
≤1.76 mm board thickness and ≥80% of drawn trace width. Obtain these as
accepted *local minima* for the actual stackup, or replace them with
the fabricator's guaranteed limits. Nominal copper weight and average
via plating are insufficient. A cross-section coupon or lot microsection
must check the barrel and finished copper at acceptance.

Qualify the exact receptacle and mating plug with a four-terminal bound
for both VBUS and GND contact groups at maximum connector temperature,
after the specified mating cycles, and under the relevant current. The
public HRO page gives a 5 A rating and 80 °C maximum operating
temperature, but not the ≤4 mΩ aggregate contact bound. Four-terminal
board measurements should separately resolve J1→F1, F1→U2 and U2→J1
return at controlled temperature. This distinguishes copper, contacts,
and the PTC/eFuse internal drops.

At the eFuse's 3.21 A maximum current-limit value, a 15 mΩ loop would
dissipate 155 mW and drop 48 mV; the 4 mΩ contact allocation alone would
dissipate 41 mW. The proposed 0.5 mm QFN neck's 1.95 mΩ estimate would
dissipate 20 mW. These are electrical loads, not temperature limits.
Use a coupled board-and-connector thermal model or powered fault test at
worst ambient and the eFuse/PTC time history. Re-extract resistance at
the resulting conductor temperatures, keep J1 within 80 °C, and check
the PTC and eFuse independently. A static 115 °C copper assumption does
not establish that thermal fixed point.

Only a complete source-replayed board with zero KiCad DRC violations and
zero opens, the accepted fabrication minima, qualified contacts, and
bounded thermal field can close MB-005. Neither existing experimental
branch meets these conditions.
