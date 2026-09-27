# PCIe key-notch socket source review (2026-09-28)

**Decision: no socket or shifted contact pattern is qualified.** Keep the
0.30 mm plotted copper-to-notch failure and `MECH-001` open. This review is
limited to published manufacturer information; no supplier was contacted and
no part was ordered. It does not authorize a footprint, card outline, or
assembly substitution. The current geometry and required evidence are in
[card-notch-qualification.md](card-notch-qualification.md).

## Geometry that a candidate must close

All dimensions below are in mm. Let `G` be the *finished* center distance
between the two key-adjacent fingers, `N` the *finished* notch width at the
finger's y span, and `wL,wR` their *finished* widths. The two copper-to-wall
clearances sum to `G - N - (wL+wR)/2`. Therefore **both** clearances can be
at least 0.30 only if

`Gmin >= Nmax + (wLmax+wRmax)/2 + 0.60`.

With the published PCIe card dimensions `N=1.90±0.06` and
`wL=wR=0.70±0.05`, an independent worst-case production guarantee needs
`Gmin >= 1.96+0.75+0.60 = 3.31`. Even if a process can guarantee both
fingers at *at most* 0.65 wide, it still needs `Gmin >= 3.21`. The earlier
proposed `G=3.16`, `N=1.90`, `w=0.65` gives 0.305 **nominal** per side; at
`N=1.96,w=0.75` it gives only 0.225 per side. At `N=1.96,w=0.65` it gives
0.275. Thus a nominally allowed 0.08 shift is not a finished 0.30 guarantee.
These bounds assume perfect centering of notch between fingers and zero
extra etch/registration error; either error can only worsen one side.

For rib fit, let `Rmax` be the socket's guaranteed maximum rib width and
`e` the absolute worst-case rib-to-notch lateral offset, including rib to
spring location, card contact/route registration, and assembly freedom.
The minimum gap at either side is at most `(Nmin-Rmax)/2-e`. At the PCIe
`Nmin=1.84`, a **positive** gap requires `Rmax+2e<1.84`. To exceed the
project's 0.10 mm routed-edge allowance on *each* side requires
`Rmax+2e<1.64`. The selected UMAX rib is `1.78±0.05`, or `Rmax=1.83`:
its best centered minimum-notch gap is only 0.005, before `e`. A nominal
notch of 1.96 with a ±0.06 route process would have a 2.02 maximum and
would fail the published 1.96 finished maximum; increasing the nominal
notch alone cannot close this stack.

For a shifted 0.65-wide finger, full lateral containment of a contact tip
requires `|shift| + e_contact + tip_width/2 <= 0.325`. At the proposed
`|shift|=0.08`, the *sum* of spring lateral uncertainty and half tip width
must be no more than 0.245. A longitudinal wipe path and plated contact
area also need a guaranteed overlap throughout insertion. Nominal pitch,
current rating, a CAD model, or a drawing of a standard card pattern does
not supply these bounds.

## Primary manufacturer drawings reviewed

| Socket family | Published relevant evidence | Qualification result |
|---|---|---|
| [UMAX 3183-10200P1T x1 / 3183-10112P1T x8](../../hw/datasheets/C404113_UMAX-3183-10200P1T.pdf), drawing 318307001, p. 1 | Selected project's x1/x8 rib `1.78±0.05`; x4 is a different SOFNG part. | `Rmax=1.83` leaves 0.005 centered at `Nmin=1.84`. No guaranteed shifted-finger tip envelope or full rib-to-contact registration is supplied. |
| [Amphenol ICC CEM01641001450X Gen5 proposal drawing](https://cdn.amphenol-cs.com/media/wysiwyg/files/drawing/c_cem01641001450xc_x3.pdf), pp. 1–2 | Lists x1/x4/x8 (36/64/98 positions), `1.78±0.05` rib, and `1.90±0.06` card notch. Its drawing status is **PROPOSAL**. | Same 0.005 centered minimum-notch gap as UMAX. It shows the ordinary card pattern, without a guaranteed shifted-pad contact-tip/wipe envelope. A proposal drawing cannot qualify an orderable substitute. |
| [Molex 87715 sales drawing SD-87715-207 rev. J4](https://www.molex.com/content/dam/molex/molex-dot-com/products/automated/en-us/salesdrawingpdf/877/87715/877159106_sd.pdf), pp. 1–3 | Covers x1/x4/x8 36/64/98 positions. Its add-in-card figure retains `1.90±0.06` notch and `0.70±0.05` fingers. The drawing has key-region dimensions, but does not present a complete guaranteed rib-center-to-contact-tip/wipe stack for shifted pads. | No documented acceptance of the 0.65-wide, 0.08-shifted A11/B11/A12/B12 pattern or complete tolerance stack. Mechanical PCB termination is also different from selected sockets. |
| [TE Connectivity 2337939 Gen4 drawing rev. F1](https://www.te.com/commerce/DocumentDelivery/DDEController?Action=srchrtrv&DocFormat=pdf&DocLang=English&DocNm=2337939&DocType=Customer+Drawing&PartCntxt=5-2337939-7), pp. 1–3 | Part table spans 36/64/98 positions and explicitly says **36-position parts are not tooled**. Its card figure uses `1.90±0.06` notch and `0.70±0.05` fingers. These are SMT motherboard sockets, whereas the selected x1/x8 sockets are THT. | Cannot presently serve x1; no shifted-pad wipe envelope or guaranteed rib-to-contact offset is given for x4/x8. A board assembly substitution would need its own footprint/stock review. |
| [Samtec PCIE series and PCIE-XXX-02-X-D-TH drawing](https://suddendocs.samtec.com/prints/pcie-xxx-02-x-d-th-mkt.pdf) | Manufacturer offers 36/64/98-position PCIe sockets for 1.57 mm cards. | Published product overview/drawing do not certify the shifted key-adjacent card pattern or full rib-to-contact offset. |

The Amphenol and Molex drawings offer no smaller **verified** rib plus a
qualified shifted contact pattern. TE's explicit x1 tooling gap prevents
one-family replacement today. Samtec is a possible sourcing lead, not a
qualified part. This is a gap in the reviewed published evidence, not proof
that no manufacturer could make a suitable connector.

## Evidence needed for a reviewable replacement

For each exact orderable x1/x4/x8 part and revision, obtain a controlled
socket drawing or manufacturer acceptance of the intended production card:
maximum rib width and rib center relative to the adjacent spring contacts;
contact-tip lateral width/location extremes; full insertion wipe path and
length; mechanical engagement and electrical ratings on the shifted pads.
The PCB fabricator must give finished internal-route and copper registration
bounds or measured acceptance of every shipped card at ≥0.30 mm plotted
and finished clearance on both faces, with the PCIe notch/finger limits.
Only then can socket center, card edge, board footprints, and first articles
be reviewed together.

Sources for the card dimensions and current fabrication limits:
[PCI-SIG CEM 3.0](https://pcisig.com/PCIExpress/Specs/CEM/CardElectromechanical_3.0),
[JLCPCB capabilities](https://jlcpcb.com/capabilities/Capab), and the
[existing notch qualification](card-notch-qualification.md).
