# Card key-notch qualification (Milestone 1)

**Status: open.** This is a dimensional acceptance plan, not a socket substitution,
fabrication approval, or waiver. Do not order cards from the proposed footprint
until the evidence below is recorded and the board checks pass. No supplier has
been contacted.

The [socket source review](card-notch-socket-source-review.md) checks published
UMAX, Amphenol, Molex, TE, and Samtec drawings against the worst-case rib and
shifted-contact requirements. It identifies no qualified substitute.

## Proposed copper geometry

The current card footprint has a 1.90 mm notch centered at x=11.50 mm and
0.70 mm wide fingers centered at x=10.00 and 13.00 mm. Its nearest copper is
`1.50 - 1.90/2 - 0.70/2 = 0.200 mm` from either notch wall, below the
project's 0.30 mm copper-to-edge rule. The same key-adjacent geometry is used
on the x1, x4, and x8 cards, on both copper faces.

A **candidate**, retaining the 1.90 mm nominal notch, makes A11/B11/A12/B12
0.65 mm wide and shifts A11/B11 to x=9.92 mm and A12/B12 to x=13.08 mm.
Its nominal wall clearance is `1.50 + 0.08 - 1.90/2 - 0.65/2 = 0.305 mm`.
The ordinary pitches next to these four pads become 0.92 mm; the gap across
the key becomes 3.16 mm. The 0.65 mm width and 0.08 mm position change fall
within the PCIe CEM revision 3.0 Figure 6-3 finger-width and default
dimensional tolerances, respectively. This is a **nominal drawing comparison**,
not evidence that the selected socket's springs still wipe and land entirely
on each shifted pad. The current `hw/mech/fit.py` pitch check (±0.01 mm) and
`hw/boards/sockets.py` contact-center check (±0.05 mm) would also reject the
candidate; revise those checks only after mating is qualified.

The 0.005 mm nominal margin above the 0.30 mm rule is too small to absorb
unspecified etch or routing error. Qualify the finished copper-to-routed-edge
distance directly, or increase the nominal margin in a later, contact-qualified
design. Narrowing the notch to 1.84 mm or leaving the finger centers fixed
cannot supply a production solution: 1.84 mm is the CEM *finished* minimum,
and the fixed-center clearance is at most 0.255 mm even with 0.65 mm fingers.

## Constrained geometry result for the current checks

No edit confined to the key notch, the four adjacent fingers, or the tab
outline can meet **both** 0.30 mm copper-to-edge on each side of the key and
the current `MECH-001` checks. The KiCad x1, x4, and x8 footprints all use
the same local x coordinates: A11/B11 at 10.00 mm, A12/B12 at 13.00 mm, a
1.90 mm notch from x=10.55 to 12.45 mm, and 0.70 mm finger widths. Each
finger runs from y=-2.15 to 2.15 mm while its adjacent straight notch wall
runs from y=-4.00 to 2.95 mm. Thus the copper and wall overlap throughout
the contact's full y span; reshaping the rounded notch end below the pads or
the tab outline elsewhere cannot increase their nearest distance.

Let `G` be the adjacent finger-center gap, `N` the finished notch width at
the contact, and `wL,wR` the two finished finger widths. The **sum** of the
two horizontal copper-to-wall clearances is exactly
`G - N - (wL+wR)/2`, regardless of notch center shift. The current
`hw/mech/fit.py` key-pitch check requires `G <= 3.01 mm`; CEM's allowed
finger widths give `wL,wR >= 0.65 mm`; its minimum notch width is 1.84 mm.
Consequently the clearance sum is at most
`3.01 - 1.84 - 0.65 = 0.52 mm`, so at least one side is **<=0.260 mm**.
Two 0.30 mm gaps instead need `G >= N + 1.25 mm`: at the 1.84 mm minimum
notch this means `G >= 3.09 mm`, 0.08 mm beyond the current pitch maximum.
At the existing 1.90 mm notch it means `G >= 3.15 mm`. Moving the notch
center trades clearance between sides and cannot change this sum. Angling
or necking its wall at the contact reduces the local notch width below the
same required minimum. With a 4.30 mm pad length, avoiding the wall by a
pad y shift would require its center below -6.15 mm or above 5.10 mm,
versus the specified 0.00 mm; the tab edge itself is at y=3.45 mm.

The UMAX x1/x8 mating condition tightens this result. `MECH-001` compares
the nominal notch `Nnom - 0.06 mm` against the UMAX key maximum
`1.78 + 0.05 = 1.83 mm`, so even a perfectly centered positive fit needs
`Nnom > 1.89 mm`. At the maximum allowed nominal notch, 1.96 mm, the
largest centered per-side fit gap is only
`(1.96 - 0.06 - 1.83)/2 = 0.035 mm`. It cannot satisfy the existing
`MECH-001` requirement that this gap exceed JLC's listed 0.10 mm routed-edge
tolerance: that would need `Nnom > 2.09 mm`, above the 1.96 mm CEM maximum.
At the smallest nominal notch that permits positive UMAX fit, the
finger-pitch bound also limits one copper-to-wall gap to **<0.235 mm**.
These are independent contradictions, so no source-only outline edit is a
reviewable production correction under the current checks.

A candidate needs a qualified change to the contact geometry or part and
fabrication process: at 1.90 mm notch and 0.65 mm fingers, the key-adjacent
gap must grow to at least 3.15 mm (for example, a 0.075 mm outward shift on
each side), and the selected socket must guarantee the shifted pad's entire
wipe area over its tolerance stack. The present socket-center check allows
only 0.05 mm error. The fabricator must also guarantee the **finished**
notch-to-copper distance and rib-to-notch registration, including route and
etch errors, on both faces. A smaller or better located socket rib could
improve mating margin, but does not cure the finger-pitch inequality.

## Evidence and acceptance limits

| Owner | Required evidence | Acceptance limit |
|---|---|---|
| PCB fabricator | Written capability for the **finished internal key route**, including tool radius, width, profile, burr control, and copper-to-route registration on both faces. The quoted outline tolerance alone is insufficient. | Every finished notch is 1.84–1.96 mm wide and retains the CEM full-radius end; tab and key datums stay inside Figure 6-3 limits. Every key-adjacent finger has **≥0.30 mm actual copper-to-edge** at its nearest point, including the routed wall and entry chamfer. Report the process tolerances and a measurement/inspection plan that guarantees these limits for shipped boards. |
| PCB fabricator | Production drawing and measured first articles for x1, x4, and x8 tabs, on both faces. Include measured finger widths and centers, actual notch width and center relative to the fingers, and the minimum copper-to-notch distances. | Finished finger width is 0.65–0.75 mm and CEM finger/key location tolerances are met. The proposed 0.65 mm width has no negative width margin, so the production target or process limits must be adjusted to guarantee ≥0.65 mm. |
| Socket maker | Controlled drawing or written guarantee for the **molded rib width and its center position relative to A11/B11/A12/B12 contacts** for the exact x1 and x8 orderable parts; corresponding evidence for the x4 socket. State worst-case dimensions, not model or nominal values. | For each mating card, `side gap = (finished notch width - maximum rib width)/2 - worst-case lateral center offset` remains positive at full insertion. State the minimum required side gap or lateral freedom and show the complete worst-case stack. |
| Socket maker | Contact-tip width, lateral location tolerance, wipe path and length at full insertion, and accepted mating-card pattern for **0.65 mm wide, 0.08 mm shifted** adjacent pads. Include contact resistance/current and durability evidence for the actual pattern. | Every spring's whole required wipe area remains on its intended plated finger throughout insertion and the specified tolerance stack; no bridge to the neighbor or notch, and electrical/mechanical ratings remain met. If contact-tip width is `c` and its lateral uncertainty from the nominal socket center is `e`, complete lateral containment needs `0.08 + e + c/2 ≤ 0.325 mm`. The present drawings do not provide `c` and `e` as a guaranteed wipe envelope. |
| Design review | Revised footprint, generated Gerbers, independent plotted clearance, socket alignment, CEM fit, and measured mating samples after the guarantees are available. | All eight boards pass the normal 0.30 mm plotted copper-edge check; `MECH-001` and socket checks pass with the qualified tolerances; trial cards mate without force or intermittent contact. Record part revisions and inspected lot identifiers. |

The existing UMAX 318307001 drawing specifies a 1.78 ±0.05 mm molded key.
Against the CEM minimum 1.84 mm finished notch, its 1.83 mm maximum key leaves
only `(1.84 - 1.83)/2 = 0.005 mm` per side when perfectly centered. JLCPCB's
published regular/high-precision routed-edge tolerances (±0.20/±0.10 mm) do
not establish that fit or the CEM ±0.06 mm notch-width requirement. A different
fabricator's advertised ±0.05 mm outline capability likewise does not by
itself establish the needed **notch-to-copper** or **rib-to-contact**
registration. A smaller guaranteed rib would relax the fit stack, but no
qualified substitute is identified here.

## Sources

- [PCI-SIG, PCI Express Card Electromechanical Specification revision 3.0](https://pcisig.com/PCIExpress/Specs/CEM/CardElectromechanical_3.0), Figure 6-3 (finger/key dimensions and default tolerance); project transcription in `hw/mech/fit.py`.
- UMAX drawing 318307001, page 1: `hw/datasheets/C404113_UMAX-3183-10200P1T.pdf` (key width and x1/x8 dimensions).
- [JLCPCB board capabilities](https://jlcpcb.com/capabilities/Capab) (routed-edge process tolerances); existing plotted violation and selected parts in `hw/boards/fab-review.md`.
- [Microchip USA PCB capabilities](https://pcb.microchipusa.com/pcb-capabilities) (example of a published ±0.05 mm outline capability and hard gold fingers; not a qualification for this notch).
