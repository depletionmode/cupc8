# Card key notch: the decision, applied (2026-09-28)

This supersedes the hold in [the release decision](card-notch-release-decision-20260928.md).
The background geometry is in [the qualification analysis](card-notch-qualification.md).

## The decision (David, 2026-09-28)

1. **Geometry:** keep the standard PCIe CEM r3.0 finger and key-notch
   geometry, the one real PCIe cards use: 0.70 mm fingers, 1.90 mm notch,
   A11/B11 and A12/B12 centres 3.00 mm apart. Nominal copper to each notch
   wall is `(3.00 - 1.90 - 0.70) / 2 = 0.20 mm`.
2. **Copper-to-edge:** the gold fingers next to the key notch (A11, A12, B11,
   B12), measured against the notch walls **only**, are held to JLCPCB's
   published minimum. All other copper on every board, and those four fingers
   against any other cut, keep the project's 0.30 mm.
3. **Key/notch position:** the positional fit (socket key rib against the
   routed notch, within JLC's edge tolerance) is qualified by first-article
   test fitting in the real sockets before the full run. It no longer fails
   the static MECH-001 check, which cannot pass on published tolerances.

## The JLCPCB figure

[JLCPCB PCB capabilities](https://jlcpcb.com/capabilities/pcb-capabilities)
(read 2026-09-28):

- "Copper clearance from routed board edges: ≧0.2 mm". **This is the figure
  used: 0.20 mm.**
- "Copper clearance from V-cut board edges: ≧0.4 mm" (not used: the cards are
  routed).
- "Dimension tolerance for routed board edges: ±0.2 mm (regular precision);
  ±0.1 mm (high precision)".

The capabilities page has no separate copper-to-edge rule for gold fingers or
the bevel. JLC's other pages say this about fingers:

- [JLCPCB Gold fingers (help)](https://jlcpcb.com/help/article/jlcpcb-gold-fingers):
  "sufficient clearance should be maintained between the edge of the gold
  fingers and the board edge", with no number; designs below the "safety
  distance" are "optimized" by JLC's engineers. The bevelled area must have
  no copper. Bevel 30° or 45°.
- [All you need to know about PCB Gold Fingers (blog)](https://jlcpcb.com/blog/pcb-gold-fingers):
  "A distance of 0.5mm should exist between the gold fingers and the outline",
  and elsewhere "at least 1.0mm away from the PCB outline".

**Open risk:** the blog numbers are guidance, not the capabilities table, and
they would also fail the 0.30 mm at the tab's outer ends that every real
PCIe card has. But JLC's engineering review may still "optimize" (trim) the
fingers beside the notch. Say in the order notes that the fingers are
standard PCIe CEM, and ask JLC to confirm they won't be trimmed. Check the
first articles for it (below).

## What the checks do now

- `hw/tools/gerberdrc.py` `check_edge` (run by `boardcheck <card> fab`,
  `fabcheck`, and `tools/fab_diagnostics.py`): a copper flash gets the
  0.20 mm (`KEY_NOTCH_EDGE_MINIMUM`) rule only if all of these hold:
  - its aperture function is `ConnectorPad`;
  - its X2 pad attribute is A11, A12, B11 or B12 of a footprint that also
    flashes the matching pin-11 or pin-12 partner, on the same axis;
  - the Edge.Cuts segment lies wholly between those two pad centres, so it is
    a notch wall, the notch chamfer, or the notch's end radius.

  Everything else is checked at the board's `min_copper_edge_clearance`
  (0.30). A distance that equals the rule passes. Before, a GEOS float
  rounding made the 0.300 mm at the tab's outer ends read as
  `0.300000 < 0.300000`, which the notch failure had been hiding.
- Test: `test/test_fabcheck.py`
  `test_key_notch_fingers_alone_get_jlc_edge_minimum`. A finger at 0.20 from
  the notch passes. A finger at 0.19 fails. A finger at 0.25 from the card
  edge fails. Non-finger copper at 0.25 from the notch fails, including SMD
  pads named A11/A12 either side of it. A lone A11 with no A12 gets no
  exemption. Counterexamples: three `Fabrication:` entries in
  `test/counterexamples.toml`.
- On the current Gerbers, all seven cards (cpu, gpu, io, storage, wifi, eink,
  system) now pass `check_edge`. The main board is unchanged.
- **KiCad board DRC:** no rule area or custom rule is added.
  `min_copper_edge_clearance` stays 0.3. KiCad already reports no
  copper-to-edge violation for the fingers against the notch: the notch
  Edge.Cuts belongs to the finger footprint, and KiCad's edge-clearance test
  does not check a footprint's pads against its own edge cuts. The plotted
  Gerber check above is the narrow, authoritative gate.
- `hw/mech/fit.py` MECH-001: every static CEM check stays: tab, chamfers,
  notch width and position, DIM B, finger width, pitch, pad tops and leads,
  short pads, shoulder, the key rib in the notch at worst case (> 0), and the
  card in the slot. The positional check (`key_position_check`, gap vs JLC's
  ±0.10 mm) is now `key_position_note`: an info line in the report that gives
  the margin and points at **MECH-101**. For the SOFNG x4 (C19188869) it
  still says "no published maximum key-rib width … the margin is nominal
  only".

## First-article procedure (MECH-101)

Proposed catalogue entry (not yet in `test/catalogue.toml`):

```toml
[[test]]
id = "MECH-101"
title = "First article: card key and fingers in the real sockets"
checks = "before the full run, on first-article cards of every type: each card inserts fully in its socket type (x1 UMAX C404113, x8 UMAX C404111, x4 SOFNG C19188869) by hand, without force, key rib in the notch; reversed insertion is blocked by the key; continuity from A11/A12/B11/B12 to the socket's matching contacts; no finger trimmed or lifted, and no copper or gold exposed at the notch walls under magnification; measured notch width and notch-wall-to-finger gap on both faces"
method = "manual, recorded in bringup.md: calipers or optical measurement, 10x+ loupe or microscope, meter on the socket's solder tails"
kind = "hw"
vrow = "5"
```

Steps, for **each** card type and at least two boards of each:

1. **Measure before insertion.** Notch width (CEM 1.90 ±0.06). Both notch
   walls to the edge of A11/B11 and A12/B12, on both faces. Record the
   smallest gap. Proposed acceptance (David to confirm): ≥ 0.10 mm, which is
   JLC's 0.20 less their ±0.10 high-precision edge tolerance, and no pad
   trimmed by JLC engineering.
2. **Look under magnification** (10x or more) at each notch wall. The route
   must not cut into a finger, and there must be no exposed copper, lifted
   gold or burr at the wall. The notch radius and chamfer must be clean.
3. **Insert** in every socket type the card goes in: I/O cards in the UMAX x1
   C404113, the CPU card in the UMAX x8 C404111, the system card in the SOFNG
   x4 C19188869. Each must seat fully by hand with the shoulder above the
   housing. The key must not bind or shave. Do each socket type on the real
   main board or on a socket soldered to a scrap board.
4. **Reversed:** turn the card round and try again. The key rib must stop
   it before any finger touches a contact, in every socket type.
5. **Continuity:** with the card seated, meter A11, A12, B11 and B12 to their
   socket contacts' solder tails: < 1 Ω, and no short to the next finger.
   Repeat after 10 insertion cycles.
6. **SOFNG x4 especially:** its drawing publishes no key-rib tolerance. If
   the rib binds, measure it and stop the run.

Pass = every card type passes 1 to 6 in its socket. On a failure, hold the
full run and go back to the socket makers (see the release decision's
evidence list).
