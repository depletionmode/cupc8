# Card key-notch qualification (Milestone 1)

**Status: open.** This is a dimensional acceptance plan, not a socket substitution,
fabrication approval, or waiver. Do not order cards from the proposed footprint
until the evidence below is recorded and the board checks pass. No supplier has
been contacted.

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
