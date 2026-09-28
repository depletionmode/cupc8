# Seven-card key-notch release decision (2026-09-28)

> **Superseded the same day:** David accepted the CEM geometry with JLC's 0.20 mm routed-edge minimum for the notch fingers only, and first-article fitting for the key position. See [the decision applied](card-notch-decision-applied-20260928.md).

**Disposition: hold all seven card fabrication packages at the existing 0.30 mm copper-to-edge gate.** No published socket drawing reviewed here qualifies a replacement or a shifted finger pattern. Do not change the shared card footprint, board outlines, `MECH-001`, or the plotted Gerber rule on the present evidence.

## Independent check of current routed cards

Loaded `build/hw/{cpu,gpu,io,storage,wifi,eink,system}/*-routed.kicad_pcb` with KiCad `pcbnew`. Every card has A11/B11 and A12/B12 finger centers 3.00 mm apart, each 0.70 mm wide. The shared footprint has a 1.90 mm notch, leaving `(3.00-1.90-0.70)/2 = 0.200 mm` nominal copper clearance on either side. The independent `build/rebuild-final/*fab-diagnostics.jsonl` receipts fail `copper_edge` at 0.200 mm against 0.300 mm for all seven cards; the main board passes this gate.

The existing key-pitch check accepts at most 3.01 mm between those centers. Even choosing the *smallest* CEM notch (1.84 mm) and fingers (0.65 mm), two 0.30 mm clearances require `G >= 1.84+0.65+0.60 = 3.09 mm`. A socket-only change or notch recentering cannot close the 0.08 mm gap in that check. For a guaranteed finished result over the full CEM notch and finger ranges, before route/etch registration, `Gmin >= Nmax + Wmax + 0.60 = 1.96+0.75+0.60 = 3.31 mm`. The earlier 0.65 mm fingers shifted 0.08 mm outward each give 0.305 mm only at nominal dimensions; they give 0.225 mm at the wide notch/wide finger corner. These bounds apply to both faces.

The selected UMAX x1/x8 key is 1.78±0.05 mm in drawing 318307001. Against the smallest 1.84 mm finished notch, its 1.83 mm maximum leaves only 0.005 mm per side when perfectly centered. A manufacturer must supply the rib-to-contact and assembly registration stack; nominal rib width alone does not prove insertion. The selected x4 SOFNG drawing likewise lacks the complete maximum-rib/contact-location stack.

## Decision needed

Authorize a controlled mating-card review with the makers of the **exact orderable x1, x4, and x8 sockets**, plus a process guarantee from the card fabricator, or select an alternate interconnect architecture. A new socket footprint is not qualified merely by a catalogue listing. The [manufacturer source review](card-notch-socket-source-review.md) examined UMAX, Amphenol, Molex, TE, and Samtec; TE states its 36-position variant is not tooled, and the other public drawings do not guarantee a shifted-pad wipe envelope. [Samtec's current PCIE product family](https://www.samtec.com/products/pcie) lists 36/64/98-position variants, so it is a sourcing lead, not a qualified substitution.

Minimum written evidence for **each** mating pair and exact part revision:

1. Socket maker: maximum molded-rib width and center offset relative to the adjacent contact springs; worst-case contact-tip width, lateral position, and full insertion wipe envelope; accepted finished card notch/pad pattern; insertion, electrical, and durability ratings with that pattern. At notch minimum, require `(1.84-Rmax)/2-e_mate` to exceed the maker's required insertion side clearance. For a 0.65 mm finger shifted 0.08 mm, full lateral tip containment requires `0.08+e_contact+tip_width/2 <= 0.325 mm`, plus longitudinal wipe containment.
2. Card fabricator: guaranteed finished notch width 1.84–1.96 mm, finger width 0.65–0.75 mm, pad centers, both notch-wall locations relative to copper on **both faces**, route radius/burr/registration and plating effects. The production drawing and inspection plan must guarantee **at least 0.30 mm actual and plotted copper-to-edge** on every shipped card, including worst cases.
3. Assembly owner: orderable manufacturer part numbers/revisions and JLC assembly or approved alternate placement process for x1/x4/x8, with validated motherboard socket footprints, hole/pad geometry, stock, and first-article mating samples.

Once these bounds exist, choose a shifted pattern with real tolerance margin, regenerate and independently check all seven card Gerbers, re-run CEM/mechanical and assembly checks, then inspect and mate first articles. Until then the published data do not support a passing, manufacturable board edit. Full geometry and the earlier nominal proposal are in [the qualification analysis](card-notch-qualification.md).
