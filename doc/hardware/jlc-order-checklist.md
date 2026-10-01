# JLCPCB order checklist (Milestone 1)

How to order the eight M1 boards from JLCPCB, one field at a time. **David
places the order.** The assistant prepares and reviews the files under the
user's delegation; no upload, reservation, purchase or order approval is implied.

JLC renames and moves fields on its order form now and then. The field names
below are the ones the form used when this was written (2026-09-28). If a
field has changed, pick the value that matches the **Why** column, and
record the change here.

Sources: each board's `build/hw/<board>/fab/order.json` (written by
`kicadgen.order_spec`, `hw/tools/kicadgen.py`), `milestone-1.md` (Board
thickness), `parts.md` (quantities, stock risks), `fab-readiness.md` /
`fab-waivers.md` (the gate and the hand checks), the card-notch decision
(`card-notch-decision-applied-20260928.md`) and `m1-live-status.md`.

Current final candidate audit (2026-09-30): all eight genuine normal
LIVE-STOCK packages have valid original receipts, two assembled boards of
each design. The exact selected source and outputs are
`build/firstarticle-final-candidate-20260930/source-tree/build/hw`; the
reviewed handoff is `build/firstarticle-manufacturing-handoff-20260930/candidate`.
These packages and stock snapshots do not constitute order approval.
Wi-Fi and e-ink require Top + Bottom assembly; the other six designs are
Top only. Codex completed the user-delegated engineering placement review
of all 127 focus rows, bound to the final native PCB, BOM, CPL and renders;
all eight complete fabrication checks passed. See
`build/firstarticle-final-candidate-20260930/engineering-review/index.html`.
Factory placement and production-file previews have not yet been seen.
The final mounted ROM is C632854 (SST39VF040-70-4I-NHE-T); the -T suffix is
carrier packaging only, with genuine exact supplier CAD separately checked.
Any subsequent source or artifact change requires fresh evidence/review binding.

## Before you order: David's notes (2026-09-28)

- **Board outline tolerance:** on all seven cards pick **±0.1 mm (high
  precision)**, not the regular ±0.2 mm. At ±0.2 mm the 0.20 mm gap between
  the key-notch walls and the nearest gold fingers can shrink to zero, and
  MECH-101's >= 0.10 mm first-article gap assumes ±0.1 mm. Check the price
  delta on the form when you order (not verified here). The main board can
  stay at ±0.2 mm.
- **Gold fingers: ENIG accepted** (David, 2026-09-28). JLC lists gold
  fingers only on ENIG, no hard-gold option. Immersion gold is thin, so
  the design life is tens of insertions; revisit hard gold in a later
  revision. `order_spec` now writes `"finger_finish": "ENIG"`.
- **2026-10-01 size revision:** select **Single PCB**, with one finished card per assembly unit. CPU/GPU/IO/storage/WiFi/eInk now measure **62 x 51 mm**; System remains **56 x 56.4 mm**. JLC may add temporary rails/carriers for assembly; require their removal before delivery and preserve fingers, notch and connector access. The earlier mandatory Panel by JLC selection is superseded. Review the actual production preview.
- **Impedance control:** Yes on every 4- and 6-layer board, with the stackup
  named in each board's `fab/order.json` (JLC04161H-7628 / JLC06161H-3313),
  once the SI rows confirm our trace geometry hits the targets on it.
- **Confirm Production File:** Yes, then run `tools/jlc_production_diff.py`
  on JLC's files (section 4).
- **First run: 2 assembled boards of each type** (David, 2026-09-28).
- **Check scarce parts before payment**: the final aggregate live snapshot
  (2026-09-30 20:04 UTC) covers all 118 mounted SKUs at twice the shared
  fitted demand; C632854 ROM stock was 9 against a required stock floor of
  4. The original C645939 was short and is not in the final BOM. This is
  not a reservation or a new spare-purchase authorization. Use the exact
  final BOM, recheck on ordering day, and obtain approval before reserving
  or paying for parts.

## 0. Mismatches and gaps found while writing this (resolve before ordering)

| # | What | Where | Proposed resolution |
|---|---|---|---|
| M1 | **Implemented in source and genuine development rebuilds (2026-09-30):** `order.json` gets `confirm_production_file`, `order_note` (cards), `pcba_type`, `solder_mask_colour`, `stencil_remark`. Was: no **Confirm Production File** field and no **order note**. Both were agreed with David (live status A.3). | `kicadgen.order_spec` and each actual `fab/order.json` | These fields are present in the current package. Check the final selected package again before ordering; implementation does not constitute supplier confirmation. |
| M2 | **Implemented in source and genuine development rebuilds (2026-09-30):** `impedance_control: true` on 4- and 6-layer boards. Was: `order.json` names a stackup (JLC04161H-7628 / JLC06161H-3313) but has no **impedance control** field. `verification.md` (the TMDS row) says the GPU is a "4-layer board with controlled impedance", and the SI models (`si-models.md`) use this stackup's dielectric. | order.json, 4- and 6-layer boards | Order **Impedance control: Yes** with the named stackup on every 4- and 6-layer board (section 2). The field is present; verify the supplier order uses that final package's named stackup. |
| M3 | **Implemented in source and genuine development rebuilds (2026-09-30):** `outline_tolerance_mm: 0.1` on cards. Was: `order.json` has no **outline tolerance**. MECH-101's acceptance, a gap of at least 0.10 mm from notch wall to finger, is "JLC's 0.20 less their **±0.10 high-precision** edge tolerance" (card-notch decision, step 1). At the regular ±0.2 mm, the nominal 0.20 mm gap can go to zero. | order.json, all seven cards | Order **Board outline tolerance: ±0.1 mm (high precision)** on every card. The field is present; retain it on the final selected package. |
| M4 | **Resolved by David, 2026-09-28: ENIG fingers accepted; source and docs changed to match.** Was: `order.json` and `milestone-1.md` said **hard gold** fingers. JLC's form offers "Gold fingers: Yes" plus a bevel. It is not clear from the form whether the fingers are electroplated hard gold or the board's ENIG. | all seven cards | ENIG fingers are already accepted. Confirm the actual supplier finish and thickness for the final order; a different finish/process needs a recorded decision. |
| M5 | `order.json` says `"assembly": "PCBA top side, parts from bom.csv/cpl.csv, all LCSC"`, but the main board has **8 through-hole connectors** (J2 CPU socket C404111, J11-J16 slot sockets C404113, J4 2x5 header C42431818; J3 C19188869 is SMD with posts). J1 USB-C also has four plated through-hole shell tabs alongside SMT contacts. So it needs JLC's through-hole assembly and USB-C shell-tab soldering as well. | main | Order **Standard PCBA** (section 2). The THT lines appear, with their fee, on the BOM step. Check that all 8 are listed as placed and J1's plated shell tabs are soldered. |
| M6 | No material or TG in `order.json`. | all | FR-4, **TG155** on the 4- and 6-layer boards. JLC's multilayer stackups are defined in TG155 FR-4. For Wi-Fi (2-layer), use JLC's default FR-4 TG135, or TG155 if the form prices it the same. Not significant for these boards: record the choice. |
| M7 | **Historical Wi-Fi via-in-pad defects repaired; genuine normal development builders pass the mandatory no-open-via-in-pad check.** David required design fixes. | Wi-Fi native PCB and Gerbers | No plugging or module-pad waiver was adopted. Preserve that check on the final selected build. The separate accepted RP2040 U1.57 exposed-pad via applies only to GPU, IO, storage, e-ink and system (`fab-waivers.md`). |
| M8 | **Final current engineering reviews completed:** all eight final `fab/cpl-review.json` files name reviewer Codex under explicit user delegation, bind current artifact hashes, and pass full fabrication checks. | gate | This closes the engineering placement review; preserve broader release/verification gates and the final supplier previews. No order approval is implied. |

What matches: layers (main 6, cpu 6, gpu/io/storage/eink/system 4, wifi 2)
agree between `order.json`, the Gerber job files and the drill files.
Thickness is 1.6 mm everywhere. The finish is ENIG. Outer copper is 1 oz and
inner copper 0.5 oz, both JLC's defaults. The smallest hole on every board
is 0.300 mm (the drill files' first tool), which matches `min_hole_mm`. The
fingers and the 30° chamfer are on all seven cards and not on the main board.
Wi-Fi and e-ink have both `Top` and `Bottom` CPL rows; the other six
boards have `Top` rows only. Every BOM line has an LCSC number.

## 1. The pre-order gate (complete the evidence tasks, then the final gate)

1. **Coordinated rebuild done** (live status A.6): all eight boards rebuilt
   into the selected release build, with fresh receipts generated by real
   pipelines. Never rehash or re-pin an old receipt. `make verify` may
   collect results at this stage, but its final green run must follow
   the reviews, live stock and dated hand checks below:
   ```sh
   make verify JOBS=2          # runs test/run.py --gate, then tools/fabready.py
   ```
   It must end green: `doc/hardware/fab-readiness.md` says **All rows green:
   yes**. Run it in the background; it takes hours.
2. **CPL reviews approved**, one per board, after the rebuild (a rebuild
   voids them, because they hash the BOM, CPL, PCB and render):
   ```sh
   python3 tools/fab_review_bundle.py                         # overlays + unsigned templates
   python3 tools/board_review_packet.py --output build/review-packet/cupc8-boards.pdf
   python3 tools/cpl_focus.py build/review-packet/cupc8-boards-checklist.csv   # the risky rows
   ```
   The delegated engineering reviewer checks every focus row (ICs,
   diodes/LEDs, transistors, connectors, crystals, switches and resistor
   networks), and records their own name and evidence. The final snapshot
   has authentic Codex approvals for all eight boards; no David/JLC
   signature or factory preview is claimed. A changed build requires new
   current review binding; never copy or rehash an old review.
3. **Fresh stock check** on the day of ordering. The final normal packages
   used genuine live stock checks, and the independent aggregate snapshot
   passed all 118 mounted SKUs. Recheck the selected ROM C632854 and shared
   FPGA C1521989 with the whole fitted demand; availability can change:
   ```sh
   python3 tools/aggregate_stock.py --board-root build/hw \
       --output build/release/aggregate-stock.json
   python3 hw/tools/jlcparts.py check C709347 C1509156 --min-stock 2   # the loose antenna lead and antenna
   ```
   This mandatory gate validates current receipts for all eight board types,
   exactly **2 assembled of each**, and requires stock ≥2× the **sum** of
   shared-part demand across all16 assembled boards. Separate per-board
   stock checks cannot establish that total. Offline/skipped or replayed
   supplier answers fail this release gate. The result is a dated live
   snapshot, not a reservation; repeat on ordering day. A quantity change
   requires matching newly generated receipts and a reviewed gate change.
   Anything short: reserve it in the JLC parts inventory first (`parts.md`,
   Risks 1-2), or use the listed fallback. A fallback part is a board change
   and needs a rebuild.
4. **Hand checks** in `fab-waivers.md` all dated. Run the final
   `make verify` against the selected source/build after steps 1–3; it
   must produce the green report required by `verification.md`. David
   then signs `fab-readiness.md`. Physical `kind = "hw"` measurements
   belong to first-article bring-up; their limits and minimum sample
   counts remain unchanged.
5. **Gerber zips made** (section 2.1) from the same build that passed 1-4.
   Every file in the zip must have the SHA-256 recorded for it under
   `artifacts` in `build/hw/<board>/evidence.json` (the zip step copies
   them unchanged, so rebuilding between the gate and the zip is the only
   way this fails).

## 2. Per-board order

### 2.1 Files to upload

Nothing in the repository makes the Gerber zip, so make it here. Put it
**outside** `build/hw/<board>/fab/`: every file in `fab/` is hashed into the
board's evidence receipt, so a new file there makes the board stale.

```sh
python3 - <<'EOF'
import pathlib, re, shutil, zipfile
for b in ('main', 'cpu', 'gpu', 'io', 'storage', 'wifi', 'eink', 'system'):
    fab, out = pathlib.Path(f'build/hw/{b}/fab'), pathlib.Path(f'build/jlc-order/{b}')
    out.mkdir(parents=True, exist_ok=True)
    keep = re.compile(rf'^{b}(-.*\.(gtl|gbl|g\d|gts|gbs|gto|gbo|gtp|gbp|gm1|gbrjob)|\.drl)$')
    with zipfile.ZipFile(out / f'{b}-gerbers.zip', 'w', zipfile.ZIP_DEFLATED) as z:
        for f in sorted(fab.iterdir()):
            if keep.match(f.name):
                z.write(f, f.name)
    for name in ('bom.csv', 'cpl.csv'):
        shutil.copyfile(fab / name, out / name)
    print(b, len(zipfile.ZipFile(out / f'{b}-gerbers.zip').namelist()), 'files')
EOF
```

| Upload step | File | Produced by |
|---|---|---|
| "Add gerber file" | `build/jlc-order/<board>/<board>-gerbers.zip` | the zip above, from `build/hw/<board>/fab/*` (KiCad plots from the board pipeline, `hw/boards/<board>.py` → `kicadgen.pipeline`) |
| PCBA "Add BOM file" | `build/hw/<board>/fab/bom.csv` (columns Comment, Designator, Footprint, LCSC Part #) | `kicadgen.pipeline`, checked by `hw/tools/bomcheck.py` |
| PCBA "Add CPL file" | `build/hw/<board>/fab/cpl.csv` (Designator, Mid X, Mid Y, Layer, Rotation) | `kicadgen.pipeline`; rotations checked by BRD-001 and the CPL review |

Order each board as its own line item (Different Design: 1). Do not combine
boards into a panel.

### 2.2 Board facts (from the job files, drill files and `order.json`)

| Board | Layers | Size (mm, job file) | Stackup | Fingers | BOM lines / placements | THT | Rev |
|---|---|---|---|---|---|---|---|
| main | 6 | 131.1 x 188.1 | JLC06161H-3313 | no | 71 / 274 | 8 THT (sockets, header); J1 SMT + PTH shell; J3 SMD + NPTH posts | A |
| cpu | 6 | 62.1 x 51.1 | JLC06161H-3313 | x8, ENIG gold, 30° | 11 / 47 | none | A |
| gpu | 4 | 62.1 x 51.1 | JLC04161H-7628 | x1, ENIG gold, 30° | 29 / 58 | none | A |
| io | 4 | 62.1 x 51.1 | JLC04161H-7628 | x1, ENIG gold, 30° | 30 / 58 | none | A |
| storage | 4 | 62.1 x 51.1 | JLC04161H-7628 | x1, ENIG gold, 30° | 21 / 48 | none | A |
| wifi | 2 | 62.1 x 51.1 | (2-layer, none) | x1, ENIG gold, 30° | 22 / 47 | none | A |
| eink | 4 | 62.1 x 51.1 | JLC04161H-7628 | x1, ENIG gold, 30° | 22 / 51 | none | A |
| system | 4 | 56.1 x 56.5 | JLC04161H-7628 | x4, ENIG gold, 30° | 19 / 48 | none | A |

(The "sockets" row in `fab-readiness.md` is not built and is not part of
this order.) Update this table from `build/hw/<board>/fab/<board>-job.gbrjob`
after the rebuild if an outline changed.

### 2.3 PCB options, click by click

Start at jlcpcb.com → **Order now** → **Add gerber file** → the zip. Wait
for the viewer. It must show the layer count and size from 2.2. If it does
not, stop: the zip is wrong.

| Field | main | cards (cpu, gpu, io, storage, eink, system) | wifi | Why / `order.json` field |
|---|---|---|---|---|
| Base material | FR-4 | FR-4 | FR-4 | |
| Layers | 6 | cpu 6; others 4 | 2 | `layers` |
| Dimensions | auto (131.1 x 188.1) | auto (2.2) | auto | from the Gerbers: check it |
| PCB qty | section 5 | section 5 | section 5 | historical planning minimum 5; confirm current supplier quotation |
| Product type | Industrial/Consumer electronics | same | same | |
| Different design | 1 | 1 | 1 | one board per zip |
| Delivery format | Single PCB (main) | **Single PCB**, supplier assembly rails/carrier removed before delivery | same | Supplier production preview remains pending; verify rails/tabs preserve fingers. The finished 62 x 51 mm cards meet the bevel size requirement; any assembly carrier is temporary and must preserve the supplied finished outline |
| PCB thickness | 1.6 mm | 1.6 mm | 1.6 mm | `thickness_mm`; CEM card 1.57 ± 0.13 (`milestone-1.md`) |
| PCB colour | Green | Green | Green | not specified anywhere; green is the cheapest and quickest |
| Silkscreen | White | White | White | |
| Material type | FR4-TG155 | FR4-TG155 | FR4-TG135 (or TG155 at the same price) | M6 |
| Surface finish | ENIG | ENIG | ENIG | `surface_finish`; needed with gold fingers and flat for the fine-pitch parts |
| Outer copper weight | 1 oz | 1 oz | 1 oz | `finished_outer_copper_oz` |
| Inner copper weight | 0.5 oz | 0.5 oz | n/a | `finished_inner_copper_oz` |
| Specify layer sequence | Yes if asked: L1 F_Cu (.gtl), L2 In1 (.g1), L3 In2 (.g2), L4 In3 (.g3), L5 In4 (.g4), L6 B_Cu (.gbl) | same for cpu; 4-layer: .gtl, .g1, .g2, .gbl | n/a | the SI and power models assume In1 is the ground plane under the top layer |
| Impedance control | **Yes**, JLC06161H-3313 | **Yes**, cpu JLC06161H-3313; others JLC04161H-7628 | No | `stackup`; M2 |
| Via covering | Epoxy Filled & Capped (current six-layer quote default) | Use current quote option; inspect CAM mask and RP2040 exposed-pad vias | Tented (see M7) | the genuine normal builds enforce no unapproved open via in pad (M7); the RP2040 exposed-pad via U1.57 on gpu, io, storage, eink and system stays open in its pad (audit I3, accepted) |
| Min via hole size / diameter | 0.3 mm / (0.4/0.45 mm), the free default | same | same | our smallest via is 0.3 mm drill with a 0.6 mm or larger pad |
| Board outline tolerance | ±0.2 mm (regular) | **±0.1 mm (high precision)** | **±0.1 mm** | M3; the MECH-101 0.10 mm gap assumes it |
| Confirm production file | **Yes** | **Yes** | **Yes** | David, 2026-09-28 (live status A.3): JLC's CAM may trim fingers or move the notch; we check their files first (section 4) |
| Mark on PCB | **Remove mark** | **Remove mark** | **Remove mark** | the boards have no `JLCJLCJLCJLC` placeholder, so "specify location" has nowhere to go. Otherwise JLC prints its number wherever it likes, possibly on the fingers' silk-free area or the logo |
| Electrical test | Flying probe, fully tested | same | same | the default; there is no prototype |
| Gold fingers | No | **Yes** | **Yes** | `gold_fingers`, `finger_finish` (M4) |
| 30° finger chamfer | n/a | **Yes, 30°** | **Yes, 30°** | `finger_chamfer_deg`; CEM asks 20° ± 5°: the 30° waiver in `fab-waivers.md` |
| Castellated holes | No | No | No | |
| Edge plating | No | No | No | |
| Press-fit holes, blind/buried vias, via-in-pad (POFV) | No | No | No (unless M7 says plug) | |
| Other paid extras (4-wire Kelvin test, paper between boards, UL mark, etc.) | No | No | No | |

### 2.4 PCB assembly (toggle **PCB Assembly** on)

| Field | Value | Why |
|---|---|---|
| PCBA type | **Standard** | the main board has THT parts and 6 layers, the cards have gold fingers and ENIG, and several parts are extended. Economic PCBA does not cover all of that, and one type for every board keeps them alike |
| Assembly side | **Top + Bottom for Wi-Fi and e-ink; Top for the other six boards** | match the exact `assembly_sides` and actual CPL rows in each final `order.json`; quote and review both faces |
| PCBA qty | **2 of every board** (David, 2026-09-28; JLC's minimum is 2) | `parts.md`, Build quantity; the build-time stock check assumed these |
| Tooling holes / edge rails | **Added by JLCPCB**, on rails only | our cards have no room for tooling holes. If the form or an EQ proposes holes or rails **on the board** or on the **finger edge**, refuse and ask for another way |
| Confirm parts placement | **Yes** | JLC's engineers send placement images to approve. This is a second check after our CPL review, not a replacement for it |
| Everything else (bake, cleaning, photo confirmation, packaging) | defaults | |

Then **Next** → upload `bom.csv` and `cpl.csv` → the parts page:

- Every BOM line must be matched to exactly the LCSC number in the file,
  with none "not selected" and no shortfall. Count them against 2.2.
- On the main board, check that the THT connectors (J2, J4, J11-J16) and J3
  are selected as placed, with the THT fee shown. Also confirm soldering
  of J1 USB-C's four plated shell tabs, not only its SMT contacts. J3
  support posts are NPTH mechanical features. Main U7 is physically SMD
  LQFP144 despite its erroneous native footprint THT attribute; quote
  assembly from the actual package and pads, not that metadata flag.
- JLC's placement preview: if a part looks rotated, **do not fix it in JLC's
  tool.** Fix the CPL at the source and rebuild, because a hand edit there
  bypasses BRD-001 and the CPL review. If time forces a JLC-side fix, record
  it here with the designator and angle.
- The Wi-Fi antenna lead (C709347) and SMA antenna (C1509156) are not in any
  BOM. Add them as loose parts to the same order (JLC parts, "order
  components"), quantity 2 each. Check that the lead is **SMA female (jack)**
  and the antenna **SMA male**, not RP-SMA (`fab-waivers.md`, hand checks).
  Ordinary live loose-part query passed on 2026-09-30: C709347 stock 157
  and C1509156 stock 334, against minimum 2 each (dated log
  `build/firstarticle-manufacturing-handoff-20260930/loose-antenna-live-stock.log`).
  They are not included in the 118 mounted-SKU aggregate and are not
  reserved. Plug the RF lead into the module by hand and attach the SMA
  antenna; JLC does not assemble these loose cable parts.

## 3. Order note (the "Remark" or "Order notes" field)

On **every card** (cpu, gpu, io, storage, wifi, eink, system), paste this
exactly. It was agreed with David, 2026-09-28:

> Gold fingers follow PCIe CEM r3.0 geometry. Do not trim, narrow, shorten or shift any gold finger, and do not change the key notch. If your process requires any change, contact us before production.

Main board: no note. It has no fingers.

These are proposed additions for David to approve, not yet agreed. Without
approval, paste only the sentence above:

- "No tooling holes or edge rails on the gold-finger edge." (2.4)
- The historical Wi-Fi via-plug proposal was not adopted: actual via-in-pad
  defects were repaired, and the final required no-open-via-in-pad check
  passed. Do not request plugging as a substitute for the approved geometry.

## 4. Checking JLC's production files (Confirm Production File)

After payment, JLC's CAM prepares the production files and the order waits
at "Confirm production file" in the order's detail page. Download them.
**Confirm only when every board passes both checks below.** If you
disagree, reply to the EQ or contact JLC. Do not confirm and then complain.

### 4.1 Automatic: `tools/jlc_production_diff.py`

```sh
python3 tools/jlc_production_diff.py build/hw/cpu/fab ~/Downloads/<jlc-cpu-production>.zip
```

It renders both sets, ours and theirs: every copper layer, both solder
masks, and the filled board profile. It aligns them on the profiles'
lower-left corners (JLC often moves the origin; the offset is printed) and
reports every area of difference **wider than 0.1 mm** (`--tolerance`).
Narrower differences are etch compensation or rendering noise. Each area is
reported as `removed` (ours has copper, mask or board, theirs does not) or
`added`, with its box in our coordinates. It is marked **EDGE** when it
lies within 3 mm of the board edge, which is where the fingers and the
notch are. It also matches every drill hit within 0.05 mm: a missing or
extra hit, or a diameter change over 0.16 mm, is a difference.
Enlargements within 0.16 mm (JLC's plating allowance on plated holes) are
counted, not failed. Exit 0: no differences. Exit 1: differences, listed.
Exit 2: a layer could not be paired or parsed.

Their files are paired to ours by X2 attributes or Protel extension. If JLC
names them differently, pair them by hand, for example
`--map "Gerber_TopLayer.GTL=copper-top" --map "Drill_PTH.DRL=drill"`. The
keys are copper-top, copper-bot, copper-inN, mask-top, mask-bot, profile
and drill. Silkscreen and paste are not compared; look at those in the
viewer.

Reading the result:

- **Any EDGE `removed` on copper-top, copper-bot or a mask**, or **any
  difference on `profile`**: the fingers were trimmed, narrowed, shortened
  or shifted, or the notch or outline changed. **Do not confirm.** Quote
  the order note and ask for our geometry.
- A difference away from the edge: open it in the viewer at the printed
  box. Copper added as thieving on an inner layer, or a small mask change,
  may be acceptable. Record the decision here with the order number.
- Missing or extra drills: do not confirm.
- Not handled by the tool (it exits 2 or would give a wrong answer): a
  panelised file (step and repeat), Gerber 2020 aperture transforms, and
  Excellon rout mode. If JLC sends a panel, compare by eye (4.2) and ask
  for the single-board file.

Status: implemented and tested (`test/host/test_jlc_production_diff.py`,
about 5 s, needs `build/hw/cpu/fab`). The test compares our CPU-card files
against themselves. It also compares them as JLC might return them: X2
stripped, renamed, zipped and moved 5 mm. Then it checks mutated copies:
fingers trimmed 0.5 mm (reported as EDGE removed, both faces), the notch
moved 0.3 mm (a profile difference), a via dropped (missing), and a
0.1 mm plating enlargement (not a difference). It is catalogued as **HOST-004**, kind `static`, vrow 4.9, command
`python3 test/host/test_jlc_production_diff.py`. It has not been run on
a real JLC production file, so the first order's files are its real test:
also do 4.2 on that order.

### 4.2 By eye (every board, even when 4.1 is clean)

In JLC's viewer, or gerbv/KiCad's Gerber viewer, with our zip loaded
alongside theirs:

- **Fingers:** count them (x1: 36 positions, x4: 64, x8: 98, both faces
  together). Look at the width, the length, and the setback from the edge
  (ours start 1.3 mm above the edge on the CPU card). Check the finger
  mask opening. Check that none is shortened or has a plating bar or
  bussing trace added that ours lacks.
- **Notch:** its position between A11/A12 (B11/B12) and its 1.90 mm width.
  The round end. No copper moved away from the walls.
- **Outline:** the size in 2.2, the tab shoulders, the corners.
- **Drills:** the tool list. Plated holes enlarged by about 0.1 mm is
  normal. NPTH mounting holes (3.2 mm) must be unchanged.
- **Silkscreen:** the logo, the `<name> rev A` text and the power LED
  marking are present. No JLC mark (you ordered Remove mark).

## 5. Order sequencing

The authorized assembled batch is two of each board type (`parts.md`,
David, 2026-09-28); the historical five-bare-PCB planning quantity requires
a current supplier quote. The unchanged three-unit first-power and GPU
qualification gates cannot be closed by this two-unit batch: an extra
assembled sample or explicitly approved qualification scope is required. The first order is therefore the
first article. What matters is what gates the *next* order. Recommended:

1. **Check the actual final scarce parts**, C632854 ROM and C1521989 FPGA,
   against aggregate demand and a current supplier quote. Any paid private
   inventory reservation or spare purchase requires David's approval;
   historical C645939/fallback/spare figures are not the final BOM.

2. **Optional, cheap, early: a bare-PCB fit order.** 5 bare PCBs (no
   assembly) each of **io** (x1 notch), **cpu** (x8) and **system** (x4),
   with every option in 2.3 including Confirm production file and the
   note. Plus loose sockets C404113, C404111 and C19188869 from LCSC. Then
   run MECH-101 steps 1-5 (measure the notch-to-finger gaps: at least
   0.10 mm; insert; reverse; continuity) before paying for assembly. This
   answers the notch question for about the cost of bare boards. It also
   gives `jlc_production_diff.py` its first real production files.
3. **First-article assembled order, all eight boards:** 5 PCBs / 2
   assembled of **each of all eight designs, including main**. Every board
   goes through section 4. The earlier suggestion of three assembled main
   boards is an unadopted spare-board proposal; current authorized demand
   and receipts remain two per design.
4. **Bring-up and measurement before any further order:** MECH-101 on two
   of each card, the `kind = "hw"` rows, and the first-article measurements
   in live status B (C45783 ESR and capacitance, mated-slot return
   resistance, ESP32 TX current and board temperature, the RP2040 DVDD
   step). Whether these gate a later order is David's call (live status C).
5. **Any further run or respin**: bump `REVISION` on each changed board
   (`milestone-1.md`, Board revision), rebuild, rerun section 1, and repeat
   sections 2-4. Never reorder an old zip after a board source has changed.

## Sign-off per board (fill in when ordering)

| Board | Gate (1) | Zip hash matches receipt | Options (2.3/2.4) | Note (3) | Production diff (4.1) | By eye (4.2) | JLC order no. |
|---|---|---|---|---|---|---|---|
| main | | | | n/a | | | |
| cpu | | | | | | | |
| gpu | | | | | | | |
| io | | | | | | | |
| storage | | | | | | | |
| wifi | | | | | | | |
| eink | | | | | | | |
| system | | | | | | | |

## Card-size revision receiving requirements

The six enlarged cards require **3.55 mm more top headroom**, and their common M3 mounting hole is now at **(52, -43.55) mm** in the finger coordinate frame. Raise the existing support rail by 3.55 mm; Main mounting holes and sockets remain fixed. System remains unchanged. Any enclosure must provide the extra clearance.

Require finished thickness at every card connector region within **1.44–1.70 mm** and measure on receipt. Preserve the named stackup; its nominal category alone does not guarantee this range. Select Standard PCBA, two assembled boards, correct sides, production-file and placement confirmation, and depanel before delivery.
