# JLCPCB order checklist (Milestone 1)

How to order the eight M1 boards from JLCPCB, one field at a time. **David
places the order.** Claude prepares the files and this checklist and never
uploads or pays for anything.

JLC renames and moves fields on its order form now and then. The field names
below are the ones the form used when this was written (2026-09-28). If a
field has changed, pick the value that matches the **Why** column, and
record the change here.

Sources: each board's `build/hw/<board>/fab/order.json` (written by
`kicadgen.order_spec`, `hw/tools/kicadgen.py`), `milestone-1.md` (Board
thickness), `parts.md` (quantities, stock risks), `fab-readiness.md` /
`fab-waivers.md` (the gate and the hand checks), the card-notch decision
(`card-notch-decision-applied-20260928.md`) and `m1-live-status.md`.

## 0. Mismatches and gaps found while writing this (resolve before ordering)

| # | What | Where | Proposed resolution |
|---|---|---|---|
| M1 | `order.json` has no **Confirm Production File** field and no **order note**. Both were agreed with David (live status A.3). | `kicadgen.order_spec` (hw/tools/kicadgen.py:2722), queued until the main-board agent finishes | Add `"confirm_production_file": true` and, for cards, `"order_note": "<the text in section 3>"` to `order_spec`, then rebuild. Until then this checklist is the only record. |
| M2 | `order.json` names a stackup (JLC04161H-7628 / JLC06161H-3313) but has no **impedance control** field. `verification.md` (the TMDS row) says the GPU is a "4-layer board with controlled impedance", and the SI models (`si-models.md`) use this stackup's dielectric. | order.json, 4- and 6-layer boards | Order **Impedance control: Yes** with the named stackup on every 4- and 6-layer board (section 2). Add `"impedance_control": true` to `order_spec`. |
| M3 | `order.json` has no **outline tolerance**. MECH-101's acceptance, a gap of at least 0.10 mm from notch wall to finger, is "JLC's 0.20 less their **±0.10 high-precision** edge tolerance" (card-notch decision, step 1). At the regular ±0.2 mm, the nominal 0.20 mm gap can go to zero. | order.json, all seven cards | Order **Board outline tolerance: ±0.1 mm (high precision)** on every card. Add it to `order_spec`. |
| M4 | `order.json` and `milestone-1.md` say **hard gold** fingers. JLC's form offers "Gold fingers: Yes" plus a bevel. It is not clear from the form whether the fingers are electroplated hard gold or the board's ENIG. | all seven cards | Before ordering, ask JLC (chat or order note) whether "Gold fingers: Yes" is hard gold, and how thick. If it is only ENIG, David decides: accept it (with a waiver in `fab-waivers.md`) or change fabs. It is not a silent substitution. |
| M5 | `order.json` says `"assembly": "PCBA top side, parts from bom.csv/cpl.csv, all LCSC"`, but the main board has **9 through-hole connectors** (J2 CPU socket C404111, J11-J16 slot sockets C404113, J4 2x5 header C42431818; J3 C19188869 is SMD with posts). So it needs JLC's through-hole assembly as well. | main | Order **Standard PCBA** (section 2). The THT lines appear, with their fee, on the BOM step. Check that all 8 are listed as placed. |
| M6 | No material or TG in `order.json`. | all | FR-4, **TG155** on the 4- and 6-layer boards. JLC's multilayer stackups are defined in TG155 FR-4. For Wi-Fi (2-layer), use JLC's default FR-4 TG135, or TG155 if the form prices it the same. Not significant for these boards: record the choice. |
| M7 | On the **Wi-Fi** card, 13 of the 190 via hits (0.3 mm) fall inside solder-mask openings, around U1 (ESP32-C3 module, X 34.8-46.0, Y 24.0-34.2 mm in Gerber coordinates). They are vias in pads, not tented. A via under a module pad can wick solder away in reflow, and JLC may raise an EQ about it. | wifi Gerbers | Confirm they are intentional (the module's GND pad stitching). If so, either ask for them to be plugged (Via covering: "Epoxy filled & capped", if the 2-layer form offers it) or accept the EQ. No other board has vias in mask openings (checked on cpu, main and wifi; the others were built by the same pipeline). |
| M8 | The CPL reviews do not exist yet (`build/hw/*/fab/cpl-review.json`: none). `fab-readiness.md` is red. The boards read "stale" until the coordinated rebuild. | gate | Section 1 is the gate: do not order before it passes. |

What matches: layers (main 6, cpu 6, gpu/io/storage/eink/system 4, wifi 2)
agree between `order.json`, the Gerber job files and the drill files.
Thickness is 1.6 mm everywhere. The finish is ENIG. Outer copper is 1 oz and
inner copper 0.5 oz, both JLC's defaults. The smallest hole on every board
is 0.300 mm (the drill files' first tool), which matches `min_hole_mm`. The
fingers and the 30° chamfer are on all seven cards and not on the main board.
Every CPL row is `Top`, and every BOM line has an LCSC number.

## 1. The pre-order gate (all must pass, in this order)

1. **Coordinated rebuild done** (live status A.6): all eight boards rebuilt
   into `build/hw` one at a time, receipts re-pinned, then:
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
   David checks every row `cpl_focus.py` lists (ICs, diodes/LEDs,
   transistors, connectors, crystals, switches, resistor networks), fills
   in each board's template and saves it as `build/hw/<board>/fab/cpl-review.json`
   with `"result"` approved. MB-009 and each card's -009 then pass.
3. **Fresh stock check** on the day of ordering. The 2x-stock check that ran
   at build time is stale by now. The ROM (C645939, 11 in stock at the last
   check) and the FPGAs (C1521989) are the risks (`parts.md`, Risks):
   ```sh
   python3 - <<'EOF'
   import collections, csv, sys
   sys.path.insert(0, 'hw/tools')
   import kicadgen
   ASSEMBLED = {'main': 3, 'cpu': 2, 'gpu': 2, 'io': 2, 'storage': 2, 'wifi': 2, 'eink': 2, 'system': 2}
   for board, n in ASSEMBLED.items():
       counts = collections.Counter()
       for row in csv.DictReader(open(f'build/hw/{board}/fab/bom.csv')):
           counts[row['LCSC Part #']] += len(row['Designator'].split(','))
       try:
           print(board, kicadgen.check_stock(counts, n))
       except SystemExit as short:
           print(board, 'SHORT:', short)
   EOF
   python3 hw/tools/jlcparts.py check C709347 C1509156 --min-stock 2   # the loose antenna lead and antenna
   ```
   Change `ASSEMBLED` to the quantities actually being ordered (section 5).
   Anything short: reserve it in the JLC parts inventory first (`parts.md`,
   Risks 1-2), or use the listed fallback. A fallback part is a board change
   and needs a rebuild.
4. **Hand checks** in `fab-waivers.md` all dated, and David signs
   `fab-readiness.md`.
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
| main | 6 | 131.1 x 188.1 | JLC06161H-3313 | no | 58 / 254 | 8 THT (sockets, header) + J3 SMD with posts | A |
| cpu | 6 | 62.1 x 47.55 | JLC06161H-3313 | x8, hard gold, 30° | 12 / 47 | none | A |
| gpu | 4 | 62.1 x 47.55 | JLC04161H-7628 | x1, hard gold, 30° | 26 / 48 | none | A |
| io | 4 | 62.1 x 47.55 | JLC04161H-7628 | x1, hard gold, 30° | 28 / 48 | none | A |
| storage | 4 | 62.1 x 47.55 | JLC04161H-7628 | x1, hard gold, 30° | 18 / 38 | none | A |
| wifi | 2 | 62.1 x 47.55 | (2-layer, none) | x1, hard gold, 30° | 14 / 23 | none | A |
| eink | 4 | 62.1 x 47.55 | JLC04161H-7628 | x1, hard gold, 30° | 19 / 41 | none | A |
| system | 4 | 56.1 x 56.5 | JLC04161H-7628 | x4, hard gold, 30° | 19 / 48 | none | A |

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
| PCB qty | section 5 | section 5 | section 5 | JLC's minimum is 5 |
| Product type | Industrial/Consumer electronics | same | same | |
| Different design | 1 | 1 | 1 | one board per zip |
| Delivery format | Single PCB | Single PCB | Single PCB | not panelised: a panel would put rails or V-cuts at the finger edge |
| PCB thickness | 1.6 mm | 1.6 mm | 1.6 mm | `thickness_mm`; CEM card 1.57 ± 0.13 (`milestone-1.md`) |
| PCB colour | Green | Green | Green | not specified anywhere; green is the cheapest and quickest |
| Silkscreen | White | White | White | |
| Material type | FR4-TG155 | FR4-TG155 | FR4-TG135 (or TG155 at the same price) | M6 |
| Surface finish | ENIG | ENIG | ENIG | `surface_finish`; needed with gold fingers and flat for the fine-pitch parts |
| Outer copper weight | 1 oz | 1 oz | 1 oz | `finished_outer_copper_oz` |
| Inner copper weight | 0.5 oz | 0.5 oz | n/a | `finished_inner_copper_oz` |
| Specify layer sequence | Yes if asked: L1 F_Cu (.gtl), L2 In1 (.g1), L3 In2 (.g2), L4 In3 (.g3), L5 In4 (.g4), L6 B_Cu (.gbl) | same for cpu; 4-layer: .gtl, .g1, .g2, .gbl | n/a | the SI and power models assume In1 is the ground plane under the top layer |
| Impedance control | **Yes**, JLC06161H-3313 | **Yes**, cpu JLC06161H-3313; others JLC04161H-7628 | No | `stackup`; M2 |
| Via covering | Tented | Tented | Tented (see M7) | our mask files cover every via on these boards except the 13 Wi-Fi via-in-pad hits |
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
| Assembly side | **Top side** | every CPL row is `Top` (`order.json` `assembly`) |
| PCBA qty | section 5 (main 3, cards 2 in the M1 build; JLC's minimum is 2) | `parts.md`, Build quantity; the build-time stock check assumed these |
| Tooling holes / edge rails | **Added by JLCPCB**, on rails only | our cards have no room for tooling holes. If the form or an EQ proposes holes or rails **on the board** or on the **finger edge**, refuse and ask for another way |
| Confirm parts placement | **Yes** | JLC's engineers send placement images to approve. This is a second check after our CPL review, not a replacement for it |
| Everything else (bake, cleaning, photo confirmation, packaging) | defaults | |

Then **Next** → upload `bom.csv` and `cpl.csv` → the parts page:

- Every BOM line must be matched to exactly the LCSC number in the file,
  with none "not selected" and no shortfall. Count them against 2.2.
- On the main board, check that the THT connectors (J2, J4, J11-J16) and J3
  are selected as placed, with the THT fee shown.
- JLC's placement preview: if a part looks rotated, **do not fix it in JLC's
  tool.** Fix the CPL at the source and rebuild, because a hand edit there
  bypasses BRD-001 and the CPL review. If time forces a JLC-side fix, record
  it here with the designator and angle.
- The Wi-Fi antenna lead (C709347) and SMA antenna (C1509156) are not in any
  BOM. Add them as loose parts to the same order (JLC parts, "order
  components"), quantity 2 each. Check that the lead is **SMA female (jack)**
  and the antenna **SMA male**, not RP-SMA (`fab-waivers.md`, hand checks).

## 3. Order note (the "Remark" or "Order notes" field)

On **every card** (cpu, gpu, io, storage, wifi, eink, system), paste this
exactly. It was agreed with David, 2026-09-28:

> Gold fingers follow PCIe CEM r3.0 geometry. Do not trim, narrow, shorten or shift any gold finger, and do not change the key notch. If your process requires any change, contact us before production.

Main board: no note. It has no fingers.

These are proposed additions for David to approve, not yet agreed. Without
approval, paste only the sentence above:

- "No tooling holes or edge rails on the gold-finger edge." (2.4)
- Wi-Fi only, if M7 is resolved as "plug": "Please plug the vias inside the
  module's ground pad."

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
0.1 mm plating enlargement (not a difference). It is **not yet in
`test/catalogue.toml`**. Proposed row: `HOST-00x`, kind `sim`, vrow 2.8,
cmd `python3 test/host/test_jlc_production_diff.py`. It has not been run on
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

M1 builds only two machines (`parts.md`: 5 bare PCBs of each design, 3 main
boards and 2 of each card assembled). The first order is therefore the
first article. What matters is what gates the *next* order. Recommended:

1. **Reserve the risky parts** in the JLC parts inventory: 3-4 x ROM C645939
   (or fallback C632851), and the FPGAs, 5 x C1521989 (`parts.md`, Risks).
   Paid by David, and possible before the gate passes.
2. **Optional, cheap, early: a bare-PCB fit order.** 5 bare PCBs (no
   assembly) each of **io** (x1 notch), **cpu** (x8) and **system** (x4),
   with every option in 2.3 including Confirm production file and the
   note. Plus loose sockets C404113, C404111 and C19188869 from LCSC. Then
   run MECH-101 steps 1-5 (measure the notch-to-finger gaps: at least
   0.10 mm; insert; reverse; continuity) before paying for assembly. This
   answers the notch question for about the cost of bare boards. It also
   gives `jlc_production_diff.py` its first real production files.
3. **First-article assembled order, all eight boards:** 5 PCBs / 2
   assembled per card, 5 PCBs / 3 assembled main boards (the spare main
   board is `parts.md`'s "no prototype" margin). Every board goes through
   section 4.
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
