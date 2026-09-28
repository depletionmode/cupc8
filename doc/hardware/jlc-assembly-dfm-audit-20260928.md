# JLCPCB assembly (PCBA) DFM audit, 2026-09-28

This audit covers all eight boards as built in `build/hw/<board>/`: the main, CPU,
GPU, I/O, storage, system, Wi-Fi and e-ink boards. The inputs were
`<board>.kicad_pcb`, `fab/bom.csv`, `fab/cpl.csv` and `fab/order.json`, all read-only.
The boards were checked against JLCPCB's published PCB and PCBA rules. The facts
come from `tools/jlc_dfm.py`, which has a test in `test/hw/test_jlc_dfm.py`.
Run it like this:

    python3 tools/jlc_dfm.py build/hw/main build/hw/cpu ...   # or --json

The tool reports facts and flags. The pass / issue / must-fix calls below are
judgements made on top of those facts. Coordinates are board millimetres, as
KiCad prints them (y increases downwards).

## JLC rules used

| Rule | Figure | Source |
|---|---|---|
| Standard PCBA board size | single board 70x70 to 460x500 mm (Economic: from 10x10). Edge rails are "necessary" for Standard | [PCBA capabilities](https://jlcpcb.com/capabilities/pcb-assembly-capabilities) |
| Gold fingers and assembly | gold fingers and castellated holes: Standard PCBA only, not Economic | same page |
| Gold-finger board size | "The length and width of a single board or panel with gold fingers shall not be less than 50mm." No chamfer below 5x5 cm. Bevel 30° or 45°. The bevel "can not have copper". The finger mask must be fully open. | [JLCPCB Gold fingers](https://jlcpcb.com/help/article/jlcpcb-gold-fingers) |
| Gold-finger finish | "Only when ENIG is chosen, the fingers ... will be with gold." The published spec lists no hard-gold (electroplated) option. | same page |
| Rails, fiducials, tooling holes | Rails at least 5 mm wide. Fiducials 1 mm, with a mask opening twice their size, at least 3.35 mm from the edge. 2 mm tooling holes. JLC adds rails and fiducials if they are missing ("We'll add fiducial marks"). Assembled boards ship with the rails on; removing them costs extra. | [Edge rails & fiducials](https://jlcpcb.com/help/article/how-to-add-edge-rails-fiducials-for-pcb-assembly-order), [process edges](https://jlcpcb.com/help/article/specifications-for-adding-process-edges-and-positioning-holes), [PCBA FAQ](https://jlcpcb.com/help/article/pcb-assembly-faqs) |
| Part to edge | Economic: at least 0.3 mm. A 2.5 mm body-to-edge rule appears only in a search snippet I could not confirm on a page, so it is not used as a gate here. | [PCBA FAQ part 2](https://jlcpcb.com/help/article/pcb-assembly-faqs-part-2) |
| Solder mask bridge | at least 0.10 mm on 1 oz copper for green, red, yellow, blue and purple mask; at least 0.13 mm for black and white | [PCB capabilities](https://jlcpcb.com/capabilities/pcb-capabilities) |
| Via-in-pad | Free POFV (filled and capped) on 6 to 20 layers only; paid on 4 layers. JLC's warning on open vias in pads: solder "flows into the vias and may cause weak soldering" | [POFV](https://jlcpcb.com/blog/Free-Via-in-Pad-on-6-20-Layer-PCBs-with-POFV), FAQ part 2 |
| Through-hole | Hand soldered: "$3.5" labour plus "$0.0173 per joint", and one extra day | PCBA FAQ |
| Stencil | JLC engineers adjust apertures to their own standard unless the order carries a remark asking for the apertures as drawn | [Stencil opening standard](https://jlcpcb.com/help/article/opening-process-standard-of-stencil) |
| Polarity | JLC reads polarity from the silkscreen: "add a triangle to point to cathode" or a band | FAQ part 2 |
| Confirm Production File | JLC emails its CAM-edited Gerbers and waits for approval before production | [Confirm production file](https://jlcpcb.com/help/article/how-to-confirm-the-production-file) |

## Findings common to every board

| Check | Result | Status |
|---|---|---|
| Bottom-side parts | None. Every CPL row is `Top`, which matches `order.json` "PCBA top side". | pass |
| Part-to-part copper gap | No pad-to-pad gap between different parts is under 0.30 mm on any board. | pass |
| Solder mask webs | The narrowest web is 0.13 mm: main U2, VQFN-10 at 0.45 mm pitch, with the pad mask expansion at 0.01 mm. Every other part is at 0.18 mm or more. That passes JLC's 0.10 mm for green. Black or white mask would put main U2 exactly on the 0.13 mm limit, so **order green** (or any colour except black and white). | pass |
| Fiducials / tooling holes | None on any board. The only NPTH holes are M3 mounting holes and connector pegs. JLC says it adds fiducials and tooling holes on rails. Every board needs rails anyway (see below), so they belong on the rails. | issue (low): put them on the panel rails (M1) |
| Zone pad connection | Every pour is `ZONE_CONNECTION_FULL` (kicadgen.py:954). Small 0402/0603 parts with one pad solid in a pour and the other pad on a track: main 77, cpu 20, gpu 20, io 24, storage 20, system 21, wifi 8, eink 19 (listed by `jlc_dfm.py`). This is a tombstoning risk, worst on the 0402 cards. JLC publishes no rule for it. | issue: see I1 |
| Order options | `order.json` has no PCBA type, panel, rails, Confirm Production File or stencil remark. Only Standard PCBA takes gold fingers. | must-fix M1 / M2 |

## Per board

Card outline for cpu, gpu, io, storage, wifi and eink: a body of 62.0 x 39.05 mm
(x -6..56, y -44..-4.95), plus a finger tab 8.4 mm deep, giving 62.0 x 47.45 mm
overall. The system card body is 56.0 x 48.0 mm plus its tab, giving
56.0 x 56.4 mm.

### main (131.1 x 188.1 mm, 6 layers, 254 parts, no gold fingers)

- **Size: pass.** The board is at least 70 x 70 mm. Standard PCBA needs rails, and
  JLC adds them by default.
- **Edge: issue (I2).** J1 (USB-C, at 30.0, 183.42) overhangs the bottom edge
  (y 188) by 0.50 mm. SW2 and SW1 (42.0 and 56.0, 184.6) have their courtyards
  0.85 mm from that edge, and U16 (49.0, 184.6) is 1.96 mm from it. Along the
  top edge, the LEDs D2-D6 and D11-D18 at y 3.0 are 2.27 mm from the edge.
  Rails must go on the **left and right (188 mm) edges**, not on the bottom
  edge: a rail there would foul J1. Say so in the order note.
- **Through-hole: issue (cost and time).** J11-J16 (UMAX 3183-10200P1T, 36
  joints each), J2 (UMAX 3183-10112P1T, 98), J4 (2x5 header, 10) and the J1
  shell (4) come to 328 joints. That costs about $5.7 per board plus $3.5
  labour, and adds a day. The PCIe sockets have staggered 1.0 mm pitch, so ask
  for AOI or visual inspection of the hand-soldered joints for bridges. J1
  (C165948) has THT shell legs: check in the JLC BOM step whether JLC treats it
  as SMD (paste-in-hole) or hand solder.
- **Connectors.** J3, the system slot (SOFNG PCIE-64P11L, SMD, pegs 1.2 mm
  NPTH), is reflowed. It is a long SMD part, and the pegs locate it, so it
  passes. The card-edge sockets are handled as THT (above).
- **Via-in-pad: pass.** No via touches an SMD pad.
- **Pin-1 marks: pass.** Every polarised part has asymmetric silkscreen. U10
  (PLCC-32) is marked by the chamfered corner at (86.67, 17.08).
- **Paste: pass.** No exposed-pad QFN. U2 (VQFN-10) has no centre pad.

### cpu (62.0 x 47.45 mm, 6 layers, 47 parts, x8 fingers)

- **Size: must-fix M1.** The board is under 70 x 70 mm (Standard PCBA) and 47.45 mm is under
  the 50 mm gold-finger minimum.
- **Fingers: pass.** No silkscreen and no via within 1 mm of the finger area
  (x -0.35..50.35, y -2.15..2.15). The nearest parts are RN6 and RN7, 11.7 mm
  away. Every finger has an open mask window. The fingers end 1.30 mm from the
  tab edge, with no copper in that band (tracks stop at y 0.10, pour at -1.50).
- **Edge: issue.** U1 (TQFP-144 at 24.5, -31.3) has its pads 0.85 mm from the
  top edge (y -44). C16 (54.8, -21.5) is 0.89 mm from the right edge, and C10
  (36.7, -42.3) is 0.94 mm from the top edge. That is fine inside a panel frame
  (M1), but the break-away tabs must stay off x 13.5..35.5 of the top edge.
- **Via-in-pad: pass.** One via touches U2.4 (SOIC GND), but its drill is
  outside the pad's mask opening.
- **Pin-1 marks: pass.** RN1-RN8 have symmetric silkscreen, but they are
  4 x 33 ohm isolated arrays, so a 180-degree turn is electrically identical.
- **Note:** the U1 footprint (easyeda TQFP-144) carries KiCad's THT attribute.
  JLC classifies parts by their LCSC part number, so this does not affect the
  order. It does make KiCad count U1 as through-hole.

### gpu (62.0 x 47.45 mm, 4 layers, 48 parts, x1 fingers)

- **Size: must-fix M1.**
- **Fingers: pass.** Keep-out clear. The nearest part is C13 (20.8, -6.2), 3.64
  mm from the finger tops. The copper-free band is 1.30 mm.
- **Edge: issue.** J2 (HDMI at 27.5, -37.1) overhangs the top edge by 1.22 mm.
  The panel frame needs a slot there (M1). C13 is 0.79 mm from the body edge
  beside the tab.
- **Through-hole: issue (cost).** J2's four shell legs are hand soldered.
- **Via-in-pad: issue (low), I3.** U1.57, the RP2040 exposed pad at (26.0, -16.0), has one
  0.3 mm via at (26.0, -15.0) inside the pad's mask opening, so its hole is
  open. It sits in the paste-free gutter between the four paste windows. The
  paste on the pad is about 0.77 mm³ against a hole volume of 0.11 mm³, so a
  good joint is expected. The vias at Y1.2, Y1.4 and U3.4 only touch the pad
  copper: their holes stay under mask.
- **Paste: pass.** The U1 exposed pad is window-paned (4 x 1.29 mm, 63 %
  coverage). Put the stencil remark on the order (M2) so JLC keeps it.
- **Pin-1 marks: pass.** RN1 and RN2 have no silkscreen, but they are
  isolated arrays of equal resistors. The BOM still lists 270 ohm, but the
  360 ohm change is pending (status A.2).

### io (62.0 x 47.45 mm, 4 layers, 48 parts, x1 fingers)

- **Size: must-fix M1.** Fingers: pass. The nearest part is Y1, 4.46 mm away.
- **Edge: issue.** J2 (USB-A at 39.5, -31.96) overhangs the top edge by 0.85
  mm, which needs a frame slot. C21 (1206 at 53.6, -17.5) is 1.26 mm from the
  right edge.
- **Via-in-pad: issue (low).** J2.5 and J2.6 are the USB-A shell pads (12.7 mm²,
  100 % paste). Each has an open 0.3 mm via, at (31.21, -33.21) and
  (47.79, -33.21). There is plenty of paste, but solder can reach the bottom
  side. U1.57 is the same as on the gpu, via at (26.5, -16.5).
- **Pin-1 mark: issue (I4).** U7 (TPS61023, SOT-563 at 43.0, -11.5, 180°)
  has **no silkscreen at all** on the built board. The library footprint has a
  pin-1 dot at (0.84, 0.93) and two bars; the build's silkscreen pass removed
  them. The package has six pads in a 2x3 grid, so a 180-degree error swaps FB
  and VOUT, and SW and VIN. JLC checks polarity against silkscreen. The CPL
  review (status item C) must cover U7 explicitly, or the mark must be put back.
- **Paste: pass.**

### storage (62.0 x 47.45 mm, 4 layers, 38 parts, x1 fingers)

- **Size: must-fix M1.** Fingers: pass. The nearest part is C13, 3.64 mm away.
- **Edge: issue.** J2 (microSD at 40.0, -34.5) sits flush with the top edge
  (courtyard 0.06 mm over it). U3 (SOIC at 34.2, -10.4) has its courtyard 0.80
  mm from the body edge beside the tab.
- **Connectors: pass.** J2 is SMD and located by its 1.0 mm NPTH pegs. The vias
  at J2.10-J2.13 (GND tabs) keep their holes under mask.
- **Via-in-pad: issue (low).** U1.57 is the same as on the gpu.
- **Pin-1 marks: pass.** RN1 is an isolated 10 k array.

### system (56.0 x 56.4 mm, 4 layers, 48 parts, x4 fingers)

- **Size: must-fix M1.** The board is under 70 x 70 mm, so Standard PCBA needs a
  panel. At 56 mm or more it passes the 50 mm gold-finger minimum.
- **Fingers: pass.** The area is x 11.15..44.85, y 50.8..55.1. The nearest part
  is R22, 12.0 mm away, and the copper-free band is 1.30 mm.
- **Edge: issue.** J1 (USB-C at 42.0, 4.58, 180°) overhangs the top edge by
  0.51 mm, which needs a frame slot.
- **Through-hole: issue (cost).** J1's four shell legs.
- **Via-in-pad: issue (I5).** Y1.2 and Y1.4 are the crystal pads (1.4 x 1.2 mm).
  The vias at (20.89, 26.46) and (17.11, 23.54) have their centres 0.09 mm
  outside the pads, so their 0.3 mm drills break into the pads' mask openings.
  Solder can wick away from a small pad and tilt the crystal. U1.57 is as on
  the gpu, via at (28.0, 18.0).
- **Pin-1 marks: pass.**

### wifi (62.0 x 47.45 mm, 2 layers, 23 parts, x1 fingers)

- **Size: must-fix M1.** Fingers: pass. The nearest part is C1, 5.29 mm away.
- **Edge: pass.** The nearest parts are D1 and R5, with courtyards 1.53 mm
  from the edge.
- **Via-in-pad: issue (I6), the worst on any board.** 15 GND pads of the
  ESP32-C3-MINI-1U (U1 at about 41, -29) have an open 0.3 mm via hole inside
  their mask opening:
  - edge pads U1.1, 11, 36, 38, 39, 42, 43, 45, 46, 47 and 52: 0.5 mm² each.
    Via centres are inside the pads, for example (40.0, -34.0) in U1.43;
  - centre pads U1.54, 56, 58 and 59: partial.

  On a 0.5 mm² pad the paste is about 0.06 mm³ at a 0.12 mm stencil, but the
  1.6 mm hole holds about 0.11 mm³. The hole can drain the whole joint. On 2
  layers there is no free POFV. These are all GND pads, so one lost joint
  costs nothing electrically, but it is the likeliest assembly defect on the
  board.
- **Paste: pass.** The module's nine 1.45 mm centre pads each have 100 %
  paste, already split into separate pads.
- **Pin-1 marks: pass.**

### eink (62.0 x 47.45 mm, 4 layers, 41 parts, x1 fingers)

- **Size: must-fix M1.** Fingers: pass. The nearest part is C13, 3.64 mm away.
- **Edge: issue.** J2 (right-angle 9-pin header at 36.5, -39.6, 180°) sticks
  out **6.12 mm** past the top edge. The panel frame needs a slot at least
  7 mm deep there. U3 and C13 have courtyards 0.80 mm from the body edge beside
  the tab.
- **Through-hole: issue (cost).** J2 is 9 hand-soldered joints.
- **Via-in-pad: issue (low).** U1.57 is as on the gpu.
- **Pin-1 marks: pass.**

## Must-fix

**M1. Panel every card, and say Standard PCBA.** Every card is under JLC's
70 x 70 mm Standard PCBA minimum. Every card except the system card is also
under the 50 mm gold-finger minimum ("single board or panel"). Gold fingers
rule out Economic PCBA, so the order as written cannot be placed. The fingers
must stay on an outer edge of the panel, because a bevel is impossible in the
middle of a panel. Proposed panel, one design per panel:

- Two cards side by side, same orientation, with the finger tabs along the
  panel's bottom edge. There is a 2 mm routed gap between the cards, and the
  cards are held by mouse-bite tabs, not V-cut: there are MLCCs within 0.8 mm
  of the edges.
- 5 mm rails on the left and right. Each rail carries 1 mm fiducials at least
  3.85 mm from the edge (2 mm mask opening), plus 2 mm NPTH tooling holes. The
  rails end level with the card body's bottom edge (y -4.95), so only the
  tabs reach the bevel.
- A top frame that brings the panel to 70 mm high. For the 62.0 x 47.45 cards
  that is 23 mm, giving a 136 x 70.45 mm panel. For the system card it is
  14 mm, giving a 124 x 70.4 mm panel. The frame is separated from the card
  tops by a routed slot at least 1 mm deeper than the largest overhang:
  - eink J2: 7.2 mm;
  - gpu J2: 2.3 mm;
  - io J2: 1.9 mm;
  - system J1: 1.6 mm;
  - every other card: 1.0 mm.

  No frame tab may sit on the cpu's top edge between x 13.5 and 35.5 (U1 pads
  0.85 mm from the edge).

This belongs in the board pipeline (a panel step in kicadgen, or KiKit), plus
`order_spec` fields: `"pcba_type": "Standard"`, `"panel": {...}`,
`"edge_rails": "customer"`. It needs David's decision, and it is hw/tools work
that this audit did not do. The cheaper alternative is to ask JLC to panelise
and add rails; it has to be confirmed through Confirm Production File.

**M2. Resolve the finger finish, and complete the order options.** `order.json`
asks for `"finger_finish": "hard gold"` and `check_order` enforces it, as do
milestone-1.md and fab-waivers.md. JLC's published gold-finger spec only
describes gold via ENIG, and its order options include no hard-gold
(electroplated) choice. Before ordering, do one of these:

- get a JLC quote or EQ for electroplated hard gold on the fingers;
- accept ENIG fingers, which suits a few insertions but not IPC's 30 µin
  guidance for about 1000 cycles, and change the requirement,
  `order_spec` and `check_order` to match.

Also add to `order_spec`:

- the Confirm Production File option and the agreed do-not-trim note, both
  already queued (status A.3);
- a stencil remark: "stencil apertures as supplied in the paste layers (RP2040
  exposed-pad windowpane)";
- solder mask colour green;
- for the main board: "edge rails on the left and right (188 mm) edges only".

## Issues (fix recommended, not blocking)

- **I1 Tombstoning.** Give SMD pads thermal-relief connections to the pours:
  `ZONE_CONNECTION_THERMAL`, 0.25 mm spokes. Keep `FULL` on exposed pads, the
  module's GND pads and power pads through footprint or pad overrides. This
  needs a rebuild. The 0402 cards (cpu, gpu, io, storage, eink) benefit most.
- **I2 Main rails.** The main board needs its rails on the left and right
  (M2 note). J1 overhangs the bottom edge by 0.50 mm and SW1 and SW2 are
  0.85 mm from it.
- **I3 RP2040 exposed-pad via** (gpu, io, storage, system, eink). One open
  0.3 mm via sits in the paste gutter. You can accept it, or tent or plug it
  (paid on 4 layers). There is also only one thermal via under the exposed
  pad; that is a thermal matter outside this audit (see the -006 rows).
- **I4 io U7 has no pin-1 mark.** Restore the SOT-563 dot and bars (the silk
  clearance pass removed them; the dot at 0.84, 0.93 was 0.13 mm from pad 1),
  or add a mark that clears 0.15 mm. In any case, list U7 in the CPL review.
- **I5 system Y1.** Move the vias at (20.89, 26.46) and (17.11, 23.54) so that
  their drill edge is at least 0.1 mm outside the pad: centre at least 0.26 mm
  from the pad edge, which means about 0.2 mm further out.
- **I6 wifi module GND vias.** Pull the 11 edge-pad vias out of the pads, onto
  a short neck with the via tented at least 0.25 mm beyond the pad edge, and
  move the partial ones in the centre field to the gaps between the 1.45 mm
  pads. The alternative is to order via plugging on this board.
- **Through-hole cost.** The main board has 328 hand-soldered joints. gpu J2,
  system J1 and eink J2 have 4, 4 and 9. Budget about $3.5 plus $0.0173 per
  joint, and a day.
- **Edge overhang and frames.** Covered by M1. The overhanging connectors
  (HDMI, USB-A, USB-C, and the e-ink header at 6.1 mm) are intended, but a
  panel must leave room for them.

## Fine as built

- Every board is single-sided.
- No part is closer than 0.3 mm (pad copper) to another part.
- Every mask web is at least 0.13 mm.
- Card fingers:
  - mask open on all of them;
  - no silkscreen or vias within 1 mm;
  - the nearest parts are 3.6 mm or more away;
  - a 1.30 mm copper-free band before the bevelled edge;
  - 1.6 mm thick, 30° bevel, ENIG, as in `order.json`.
- The RP2040 exposed-pad paste is window-paned at 63 %.
- Pin-1 or polarity marks are present on every polarised part except io U7.
  The RN arrays are symmetric by design.
- The SMD connectors (USB-C, microSD, the system slot J3) are located by NPTH
  pegs.

## Limits of this audit

- The 2.5 mm body-to-edge figure, the stencil thickness JLC uses and the
  hard-gold availability were not confirmed on a JLC page.
- The pin-1 check is a symmetry test on the silkscreen. It shows that a mark
  exists, not that the mark is correct; the CPL overlay review does that.
- The tombstoning list counts pads whose centre is in a filled pour of the same
  net. It does not weigh copper mass.
