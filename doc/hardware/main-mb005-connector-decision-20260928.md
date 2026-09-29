# MB-005 connector decision, 2026-09-28

> **Superseded (David, 2026-09-28):** the requirement is now the board-side
> loop ≤ 60 mΩ at the hottest corner with the mated contacts in the cable's
> USB Type-C §4.4.1 budget, plus ≤ 20 °C copper rise at 3.213 A
> (`mb005-loop-requirement-derivation.md`, option 2). No connector
> qualification beyond a compliant USB-C receptacle is needed; the input
> corner was re-laid (`hw/boards/main_power_corner.py`). This note is kept
> as the record of the earlier 20 mΩ analysis.

**Verdict: the current main board cannot meet the assembled ≤20 mΩ
VBUS/GND input-loop gate. No source-backed, JLC-assembled drop-in USB-C
replacement has been identified that would close it.** Keep the requirement
and MB-005 red pending the exact mated connector-pair qualification below.

The current receipt `build/hw/main/evidence.json` validates against current
source. Running `python3 hw/power/main_input_heat.py build/hw/main` gives
37.129 mΩ J1 VBUS→F1:1 plus 35.931 mΩ F1:2→U2:5 = **73.060 mΩ** positive
copper at its 115 °C sensitivity corner, before GND, contacts, solder and
other transitions. At the 3.213 A eFuse limit this scenario drops 234.7 mV
and dissipates 754 mW in modeled positive copper. The script fails I1–I4;
its copper dimensions are sensitivity assumptions, not certified fab minima.

The isolated F1/U2 relocation trial preserves J1, the card sockets and
mounting holes. It reports **four opens and ten DRC findings**, so it is not
a candidate board. Its optimistic A-side positive result is 16.600 mΩ and
its In1-only return scenario is 2.250 mΩ, for **18.850 mΩ before contacts**.
Only 1.150 mΩ remains under the absolute 20 mΩ ceiling for the complete
mated VBUS/GND contacts, solder, barrels and any omitted return geometry.
Even this is too little for a defensible manufacturing tolerance.

The fitted HRO TYPE-C-31-M-12 (JLC part C165948) advertises **≤50 mΩ
contact resistance** and 5 A rating, but supplies no maximum for the exact
receptacle plus selected plug's combined VBUS/GND groups under current,
temperature, life and orientation. If its 50 mΩ applied to each of four
independent, equally loaded fingers on each rail, the possible contact-loop
corner would be 50/4 + 50/4 = **25 mΩ** before any board copper. That is a
conditional sensitivity, not a claim about measured HRO units or guaranteed
four-way sharing. The HRO figure alone cannot certify this gate. The trial's
18.850 mΩ copper scenario plus that contact case would be 43.850 mΩ,
141 mV and 453 mW at 3.213 A before omitted terms. [HRO manufacturer
page](https://en.krhro.com/Product-Details/726.html).

The most favorable complete design budget currently proposed is **15 mΩ
at the hottest qualified condition**: ≤7 mΩ positive copper, ≤3 mΩ GND
copper, ≤1 mΩ solder/transitions and ≤4 mΩ *combined mated VBUS plus GND
contact groups*. It leaves 5 mΩ design margin. At 3.213 A that is 48.2 mV
and 155 mW for the whole loop. The existing relocation trial exceeds the
7 mΩ positive allocation by 9.600 mΩ and needs a further reroute, even if
the connector is qualified. Typical 5 A USB-C alternatives found in primary
manufacturer data advertise 30–40 mΩ initial contact maxima, not a 4 mΩ
combined-group guarantee; a current rating is not a low-resistance bound.
[Molex product specification](https://www.molex.com/content/dam/molex/molex-dot-com/products/automated/en-us/productspecificationpdf/203/203615/2036150002-000.pdf),
[Amphenol product page](https://www.amphenol-cs.com/product/gsb3c3133dshr.html).

## Minimum external decision and evidence

Ask HRO or a proposed alternate supplier for a **contractual or measured
four-terminal maximum ≤4.000 mΩ for the complete mated VBUS-plus-GND groups**
of a specified receptacle and plug/cable pair. The limit must cover both
plug orientations, 3.213 A, production variation, the specified mating life
and the connector's permitted temperature range. Also obtain JLC assembly
availability at twice the build quantity and footprint/height data proving
fit at fixed J1, sockets, holes and board outline. If that guarantee cannot
be obtained, the product owner must choose a different qualified power
interface; simply substituting another 5 A USB-C part or rerouting copper
cannot certify the present assembled-loop requirement.

After a pair qualifies, reroute the F1/U2 input corridor to the 7/3/1 mΩ
copper/transition budgets, obtain finished local copper and barrel minima,
then require source replay, zero KiCad opens/DRC, corner-aware filled-copper
extraction, four-terminal assembled-loop measurement and coupled fault
thermal verification. No current route or unqualified part is approved for
fabrication by this note.

## Options screened for the next design iteration

| Option | Quantitative result | Disposition |
| --- | --- | --- |
| Retain J1 and improve the existing Salt-9 route | Its 73.060 mΩ positive-copper scenario exceeds the entire 20 mΩ loop ceiling by 53.060 mΩ before return/contact losses. | Routing needs a substantial F1/U2 relocation, not local width cleanup. |
| Keep J1, relocate F1/U2, and add parallel outer-layer copper | The isolated trial reaches 16.600 mΩ positive plus a 2.250 mΩ *single-plane return scenario*. It has four opens and ten DRC findings. The proposed 15 mΩ margin budget requires a further 9.600 mΩ reduction in positive copper and ≤3 mΩ fully connected GND. | Feasible geometry experiment only if a mated connector pair first meets the ≤4 mΩ combined contact allocation. Complete a source-owned, zero-open route and extract all return layers. |
| Change the full six-layer board to 2 oz outer copper | [JLC's 2026 copper-weight guide](https://jlcpcb.com/help/article/jlcpcb-copper-weight) lists 2 oz outer copper but a 0.16 mm minimum trace width/space. The current board uses 0.100 mm traces at dense FPGA pins. | This is not a drop-in stackup change; it would force high-density rerouting and fabrication requalification. It cannot by itself bound the mated contacts. |
| Substitute a catalogue USB-C receptacle based on 5 A rating | [USB-IF's published Type-C specification](https://www.usb.org/sites/default/files/USB%20Type-C%20Spec%20R2.0%20-%20August%202019.pdf), §3.7.8.1, permits up to 40 mΩ initially and 50 mΩ after stress **per mated contact**. Even four perfectly shared 50 mΩ VBUS contacts and four GND contacts can total 25 mΩ before copper. | A standard-compliant 5 A rating does not prove this project's 20 mΩ assembled-loop limit. Require a tighter maker guarantee for the exact plug/receptacle pair, or change the power interface by explicit product decision. |

The first purchase decision is therefore **which mated power interface will be qualified**, with a four-terminal maximum for its complete VBUS/GND groups. Rerouting before that decision can improve the board but cannot turn MB-005 green. The relocation geometry remains the starting point once the contact and assembly bounds are supplied.
