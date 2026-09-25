#!/usr/bin/env python3
"""Mechanical fit check (verification.md row 4.7): every board's STEP, the
slot sockets, and the cards in them.

    python3 hw/mech/fit.py                 run every check, print the report
    python3 hw/mech/fit.py --check MECH-003
                                           the same run (cached), exit status
                                           of that one check only

Boards are picked up by themselves: every hw/boards/<name>.py and every
build/hw/<name>/<name>.kicad_pcb. A board whose build is missing or older
than its script is built into build/mech/boards/<name> (so a parallel
`make verify` never writes the directory another test is building). A board
is classified by what it carries:
  - a BUS_PCIexpress_x1 finger tab: an I/O card; x8: the CPU card;
    x4: the system card
  - the slot sockets (C404113, C404111, C19188869): the main board
The row (slot.md, Mechanical, "One row of cards"): the CPU socket first,
then the six I/O slots, 20.32 mm apart, the same way round and at the same
height, so the CPU card and the I/O cards (one outline) stand in a line.
The system card's x4 socket is off the row and is checked on its own.
Until the main board exists, the row comes from the stand-in in
SOCKETS/STANDIN below (the sockets' datasheet heights and seating depths),
and the system card cannot be placed.

This half runs under the system python with KiCad's pcbnew: it reads the
boards, exports STEP with kicad-cli, and does the checks that are numbers
on the design files (fingers, bevel, LED and hole positions). The geometry
(collisions, clearances, cable route, the overview render) runs in FreeCAD,
hw/mech/fc_check.py, under freecadcmd.

Outputs in build/mech/: report.txt, results.json, overview.png, <board>.step.
"""

import argparse
import fcntl
import glob
import hashlib
import json
import math
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
OUT = os.path.join(ROOT, "build", "mech")
sys.path.insert(0, os.path.join(ROOT, "hw", "tools"))

# ------------------------------------------------------------------ references
# PCI Express CEM r3.0 (2013), Figure 6-3 "Add-in Card Edge-Finger Dimensions"
# (tolerance +/-0.13 unless noted, note 3), Figure 6-1 "Connector Form
# Factor", Figure 9-1 (component height). Frame: finger B1 at the origin,
# fingers towards +y (KiCad's BUS_PCIexpress_* footprints use it too).
CEM = {
    "tol": 0.13,
    "pitch": 1.00,                    # 1.00 TYP, 'N' spaces at 1.00
    "finger_w": (0.70, 0.05),         # 0.70 +/- 0.05 TYP
    "pad_top": 5.60,                  # card edge to the pads' top end
    "lead": (1.30, 0.25),             # card edge to a full pad's leading edge (side view)
    "short_lead": 2.40,               # ... of the short pads (A1 and pin "C")
    "tab_min": 8.40,                  # card edge to the body shoulder, MIN
    "key_w": (1.90, 0.06),            # key notch, full radius
    "key_from_left": 12.15,           # tab's B1-side edge to the key centre (DATUM X)
    "key_to_b12": 1.50,               # key centre to the first finger past it (basic)
    "b1_to_b11": 10.00,               # basic
    "chamfer": 0.50,                  # tab corners, 0.50 x 45 deg
    "bevel_deg": (20.0, 5.0),         # edge bevel 20.0 +/- 5.0 deg (side view)
    "bevel_waiver_deg": 30,           # milestone-1.md: JLC's nearest (30 or 45 only), a written waiver
    "thick": (1.57, 0.13),            # across pads
    "comp_side_max": 14.47,           # Figure 9-1: primary side component height, MAX
    "solder_side_max": 2.67,          # Figure 9-1: secondary side, MAX
}
# per link width: DIM 'B' (key centre to the tab's far edge) and the short pin "C"
CEM_WIDTH = {"x1": (8.15, "B17"), "x4": (22.15, "B31"), "x8": (39.15, "B48")}
EDGE_KIND = {"x1": "io", "x4": "system", "x8": "cpu"}

# The sockets, from their datasheets (hw/datasheets/). "seat" is where the
# card edge rests: housing height less the insertion depth, i.e. the card
# bottoms out on the slot floor (the lowest it can sit; the key rib is not
# dimensioned, and the EasyEDA model puts its top 0.10 mm above a card's
# 8.40 mm notch reach, which would lift the card by that much at most).
# "b1" is where finger B1's contact sits along the housing, from the key
# position (14.50 from the housing end to the key centre, 11.50 key to B1).
SOCKETS = {
    "C404113": {"width": "x1", "part": "UMAX 3183-10200P1T", "height": 11.25, "depth": 7.60,
                "slot_w": 1.78, "length": 25.00, "wide": 7.40, "rib_w": 1.75,
                "ds": "UMAX drawing 318307001 (hw/datasheets/C404113_UMAX-3183-10200P1T.pdf): 11.25 MAX, 7.60 deep, slot 1.78 +/- 0.05, D 25.00, 7.40 wide"},
    "C404111": {"width": "x8", "part": "UMAX 3183-10112P1T", "height": 11.25, "depth": 7.60,
                "slot_w": 1.78, "length": 56.00, "wide": 7.40, "rib_w": 1.75,
                "ds": "UMAX drawing 318307001, the one LCSC serves for C404111 and C404113 (hw/datasheets/C404113_UMAX-3183-10200P1T.pdf): 11.25 MAX, 7.60 deep, D 56.00 for 98 positions"},
    "C19188869": {"width": "x4", "part": "SOFNG PCIE-64P11L", "height": 11.10, "depth": 7.60,
                  "slot_w": 1.78, "length": 39.00, "wide": 8.76, "rib_w": 1.75,
                  "ds": "hw/datasheets/C19188869_PCIE-64P11L.pdf: 11.10, 7.60 deep, 1.78 slot, 39.00 long, 8.76 wide",
                  "pads": ("1", "33")},    # JLC's pad numbers for A1 and B1 (hw/boards/sockets.py)
}
HOUSING_BEFORE_B1 = 14.50 - 11.50      # housing end to finger B1's contact
SLOT_BEFORE_B1 = 1.00                  # slot end to B1 (EasyEDA model of C404113: slot x -10.50, B1 -9.50)
SLOT_AFTER_TAB = 0.40                  # tab's far edge to the slot end (model: 10.55 vs tab 10.15)

# Until the main board exists: the row of slot.md, Mechanical: the x8 CPU
# socket, then six x1 sockets, 20.32 mm apart, finger B1 in line, all the
# same way round, on a 1.6 mm board. Which way the cards face isn't in the
# spec: the stand-in turns the component sides away from the CPU socket,
# so the CPU card's FPGA faces I/O slot 1's back.
STANDIN = {"pitch": 20.32, "row": ["C404111"] + ["C404113"] * 6, "main_t": 1.6}
ROW_PITCH = STANDIN["pitch"]
ROW_SLOTS = {"x8": 1, "x1": 6}         # slot.md: the CPU socket and six I/O slots
ROW_KINDS = ("cpu", "io")

# slot.md, Mechanical (and kicadgen IO_CARD_*): the I/O card outline, frame as CEM
IO_BODY = (-6.0, -44.0, 56.0, -4.95)    # x0, y0 (top), x1, y1 (where the tab starts)
IO_HOLE = (52.0, -40.0)
IO_HOLE_DRILL = 3.2
IO_PWR_LED = (-3.0, -41.0)
TAB_ZONE = 5.0                         # nothing but GND ties within 5 mm above the tab
RAIL_KEEPOUT = 6.4                     # the hole's keep-out: the rail standoff

# card-to-card: IPC-6012 class 2 bow and twist, 0.75 % of the 62 mm card
# body = 0.47 mm per card; two neighbours bowing towards each other
MIN_GAP = 1.0

# top- and back-edge connectors: the plug that goes in, centred on the receptacle's
# opening. USB-C: Type-C spec r2.0 3.2.1 overmold 12.35 x 6.50 max. HDMI and
# USB-A have no overmold limit in their specs: typical moulded plugs, assumed.
PLUGS = {
    "C2858275": ("HDMI type A plug (assumed typical overmold)", 21.0, 11.5),
    "C112455": ("USB-A plug (assumed typical overmold)", 17.0, 9.0),
    "C165948": ("USB-C plug (Type-C r2.0 max overmold)", 12.35, 6.5),
    # the e-ink card's 1 x 9 header: nine 2.54 mm female jumper housings side
    # by side (Dupont, 2.54 x 2.54 each, assumed; a 1 x 9 housing is the same)
    "C492417": ("nine 2.54 mm female jumper housings (assumed)", 22.9, 2.6),
}
MIN_OVERHANG = -0.3                    # mating face at the edge: routing tolerance +/-0.2

# The Wi-Fi module and its antenna. ESP32-C3-MINI-1U datasheet v1.7 (hw/
# datasheets/C2911374_ESP32-C3-MINI-1U.pdf) Fig. 9: connector centre 1.70 in
# from the left edge and 1.55 down from the top (top view, 13.2 x 12.5);
# §10.2 Fig. 10: the receptacle is the 3rd-generation one (Hirose W.FL,
# I-PEX MHF III, Amphenol AMMC), 2.05 x 2.00, mated height 1.40.
MODULES = {
    "C2911374": {"name": "ESP32-C3-MINI-1U", "size": (13.2, 12.5), "conn": (1.70, 1.55),
                 "conn_kind": "MHF III", "mated_h": 1.40},
}
# antennas by LCSC: connector generation, cable OD, cable length (datasheets)
ANTENNAS = {
    "C4943394": {"part": "KH-FPC2.4G-1.13IPEX-240", "conn_kind": "MHF I", "od": 1.13, "length": 240,
                 "ds": "Kinghelm drawing: connector 'IPEX 一代' (1st generation = MHF I / U.FL), RF-1.13 cable L=240 mm"},
    "C910056": {"part": "KH-081-TX50-IPEX3", "conn_kind": "MHF III", "od": 0.81, "length": 50,
                "ds": "JLC library: IPEX3 antenna, 50 mm (check its band before ordering)"},
    "C709347": {"part": "KH-IPEX3-SMA-RG081-150mm", "conn_kind": "MHF III", "od": 0.81, "length": 150,
                "ds": "JLC library: Gen 3 IPEX to SMA cable, 150 mm (for a case-mounted SMA antenna)"},
}
CABLE_MIN_GAP = 0.5

CHECKS = {
    "MECH-001": "Card edge and socket fit vs PCIe CEM",
    "MECH-002": "Finger bevel and card thickness vs PCIe CEM",
    "MECH-003": "Card-to-card clearance along the row, CPU card included",
    "MECH-004": "Top- and back-edge connectors: overhang and plug access",
    "MECH-005": "One row: sockets in line at one height, M3 holes on the rail",
    "MECH-006": "One row: one outline, top edges and power LEDs aligned",
    "MECH-007": "Wi-Fi antenna: connector match and cable route",
    "MECH-008": "System card off the row: envelope and clearance",
}


# ------------------------------------------------------------------- helpers
def mm(v):
    return v / 1e6


def unit(v):
    n = math.hypot(*v)
    return tuple(c / n for c in v)


def step_xy(p):
    """KiCad board coordinates (y down) to the STEP export's (y up)."""
    return (p[0], -p[1])


class Result:
    def __init__(self):
        self.checks = {k: {"title": t, "ok": True, "lines": []} for k, t in CHECKS.items()}

    def add(self, cid, ok, text):
        c = self.checks[cid]
        c["lines"].append(("pass " if ok else "FAIL ") + text)
        c["ok"] = c["ok"] and bool(ok)

    def note(self, cid, text):
        self.checks[cid]["lines"].append("     " + text)


def within(v, nominal, tol):
    return abs(v - nominal) <= tol + 1e-6


# --------------------------------------------------------------- the boards
def discover():
    """{name: pcb path} for every board that exists or has a script."""
    import kicadgen  # noqa: F401  (only to find its mtime)
    gen_mtime = os.path.getmtime(os.path.join(ROOT, "hw", "tools", "kicadgen.py"))
    names = {os.path.basename(p)[:-3] for p in glob.glob(os.path.join(ROOT, "hw", "boards", "*.py"))
             if "\ndef schematic(" in open(p).read()}   # a board script draws a schematic; rp2040card.py is a module
    names |= {os.path.basename(os.path.dirname(p))
              for p in glob.glob(os.path.join(ROOT, "build", "hw", "*", "*.kicad_pcb"))
              if os.path.basename(p) == os.path.basename(os.path.dirname(p)) + ".kicad_pcb"}
    only = os.environ.get("CUPC8_MECH_BOARDS")      # e.g. "eink,wifi": a partial run, while another board's build is broken
    if only:
        names &= set(only.split(","))
    found = {}
    for name in sorted(names):
        script = os.path.join(ROOT, "hw", "boards", name + ".py")
        need = max(os.path.getmtime(script), gen_mtime) if os.path.exists(script) else 0
        pcb = os.path.join(ROOT, "build", "hw", name, name + ".kicad_pcb")
        own = os.path.join(OUT, "boards", name, name + ".kicad_pcb")
        if os.path.exists(pcb) and os.path.getmtime(pcb) >= need:
            found[name] = pcb
        elif os.path.exists(script):
            if not (os.path.exists(own) and os.path.getmtime(own) >= need):
                print("building %s (no current build/hw/%s) ..." % (name, name), flush=True)
                r = subprocess.run([sys.executable, script, os.path.dirname(own)], cwd=ROOT,
                                   capture_output=True, text=True)
                if r.returncode != 0 or not os.path.exists(own):
                    raise SystemExit("%s: board build failed\n%s%s" % (name, r.stdout[-2000:], r.stderr[-2000:]))
            found[name] = own
        elif os.path.exists(pcb):
            found[name] = pcb             # stale but no script to rebuild it: use what there is
    return found


def read_board(name, path):
    import pcbnew
    board = pcbnew.LoadBoard(path)
    ps = pcbnew.SHAPE_POLY_SET()
    board.GetBoardPolygonOutlines(ps, False)
    outline = []
    if ps.OutlineCount():
        o = ps.Outline(0)
        outline = [(mm(o.CPoint(i).x), mm(o.CPoint(i).y)) for i in range(o.PointCount())]
    fps = []
    for fp in board.GetFootprints():
        pos = fp.GetPosition()
        lcsc = ""
        for key in ("LCSC", "LCSC Part"):
            if fp.HasField(key):
                lcsc = fp.GetField(key).GetText()
                break
        item = {"ref": fp.GetReference(), "value": fp.GetValue(), "fpid": fp.GetFPIDAsString(),
                "lcsc": lcsc, "pos": (mm(pos.x), mm(pos.y)), "rot": fp.GetOrientationDegrees(),
                "side": "B" if fp.IsFlipped() else "F"}
        # where each 3D model lands in the STEP (x, y up): the footprint
        # position plus the model's offset, turned with the footprint (an
        # imported model can be offset, e.g. C165948's 2.27 mm)
        at = []
        th = math.radians(item["rot"])
        for m in fp.Models():
            ox, oy = m.m_Offset.x, m.m_Offset.y
            if fp.IsFlipped():
                ox = -ox
            at.append((item["pos"][0] + ox * math.cos(th) - oy * math.sin(th),
                       -item["pos"][1] + ox * math.sin(th) + oy * math.cos(th)))
        item["model_at"] = at
        pads = {}
        holes = []
        for p in fp.Pads():
            pp, sz = p.GetPosition(), p.GetSize()
            rel = p.GetFPRelativePosition()
            pads[p.GetNumber()] = {"pos": (mm(pp.x), mm(pp.y)), "rel": (mm(rel.x), mm(rel.y)),
                                   "size": (mm(sz.x), mm(sz.y))}
            if p.GetAttribute() == pcbnew.PAD_ATTRIB_NPTH:
                holes.append({"pos": (mm(pp.x), mm(pp.y)), "drill": mm(p.GetDrillSize().x)})
        if "PCBEdge:BUS_PCIexpress" in item["fpid"] or lcsc in SOCKETS:
            item["pads"] = pads
        item["holes"] = holes
        fps.append(item)
    with open(path) as f:
        text = f.read()
    labels = [(m.group(1), (float(m.group(2)), float(m.group(3))))
              for m in re.finditer(r'\(gr_text "([^"]*)"\s*\(at ([-\d.]+) ([-\d.]+)', text)]
    order = {}
    order_path = os.path.join(os.path.dirname(path), "fab", "order.json")
    if os.path.exists(order_path):
        with open(order_path) as f:
            order = json.load(f)
    b = {"name": name, "pcb": path, "thickness": mm(board.GetDesignSettings().GetBoardThickness()),
         "outline": outline, "fps": fps, "labels": labels, "order": order, "kind": None}
    edges = [fp for fp in fps if "PCBEdge:BUS_PCIexpress_" in fp["fpid"]]
    sockets = [fp for fp in fps if fp["lcsc"] in SOCKETS]
    if sockets:
        b["kind"] = "main"
    elif edges:
        width = edges[0]["fpid"].rsplit("_", 1)[1]
        if width in EDGE_KIND:
            b["kind"], b["width"], b["edge_ref"] = EDGE_KIND[width], width, edges[0]["ref"]
    return b


def export_step(b):
    step = os.path.join(OUT, b["name"] + ".step")
    if os.path.exists(step) and os.path.getmtime(step) >= os.path.getmtime(b["pcb"]):
        return step
    cmd = ["kicad-cli", "pcb", "export", "step", "--subst-models", "--force", "-o", step]
    if b["kind"] == "main":
        # the sockets are placed from their datasheets (SOCKETS), not from
        # whatever 3D model the footprint carries
        keep = [fp["ref"] for fp in b["fps"] if fp["lcsc"] not in SOCKETS]
        cmd += ["--component-filter", ",".join(keep) if keep else "NONE"]
    r = subprocess.run(cmd + [b["pcb"]], capture_output=True, text=True)
    if r.returncode != 0 or not os.path.exists(step):
        raise SystemExit("%s: STEP export failed\n%s%s" % (b["name"], r.stdout, r.stderr))
    return step


# ------------------------------------------------------- card frame (fingers)
def edge_frame(b):
    """The finger tab's frame in board coordinates: B1's position, the row
    direction a (B1 -> B11) and d (towards the card edge)."""
    fp = next(f for f in b["fps"] if f["ref"] == b["edge_ref"])
    if fp["side"] != "F":
        raise SystemExit("%s: the finger footprint is on the back" % b["name"])
    p1, p11 = fp["pads"]["B1"]["pos"], fp["pads"]["B11"]["pos"]
    a = unit((p11[0] - p1[0], p11[1] - p1[1]))
    d = (-a[1], a[0])                          # +90 deg in KiCad's y-down frame
    return fp, p1, a, d


def to_local(p, origin, a, d):
    v = (p[0] - origin[0], p[1] - origin[1])
    return (v[0] * a[0] + v[1] * a[1], v[0] * d[0] + v[1] * d[1])


def check_fingers(b, res):
    """MECH-001: the finger tab, from the pads and the board outline."""
    cid = "MECH-001"
    fp, b1, a, d = edge_frame(b)
    width = b["width"]
    dim_b, pin_c = CEM_WIDTH[width]
    tol = CEM["tol"]
    name = b["name"]
    pads = {n: dict(p, loc=to_local(p["pos"], b1, a, d)) for n, p in fp["pads"].items()}
    verts = [to_local(p, b1, a, d) for p in b["outline"]]
    edge_y = max(v[1] for v in verts)
    fingers_x = [p["loc"][0] for p in pads.values()]
    lo, hi = min(fingers_x), max(fingers_x)
    tab = [v for v in verts if v[1] > edge_y - 9.5 and lo - 3 < v[0] < hi + 3]
    left, right = min(v[0] for v in tab), max(v[0] for v in tab)
    shoulder = min(v[1] for v in tab if abs(v[0] - left) < 1e-3)
    tab_h = edge_y - shoulder
    ok = tab_h >= CEM["tab_min"] - 1e-6
    res.add(cid, ok, "%s: tab height (card edge to shoulder) %.2f mm, CEM >= %.2f" % (name, tab_h, CEM["tab_min"]))
    bottom = [v[0] for v in tab if abs(v[1] - edge_y) < 1e-3]
    ch_l, ch_r = min(bottom) - left, right - max(bottom)
    ok = within(ch_l, CEM["chamfer"], tol) and within(ch_r, CEM["chamfer"], tol)
    res.add(cid, ok, "%s: corner chamfers %.2f / %.2f mm, CEM %.2f +/- %.2f" % (name, ch_l, ch_r, CEM["chamfer"], tol))
    b["tab"] = {"edge_y": edge_y, "shoulder": shoulder, "left": left, "right": right}
    notch = [v[0] for v in tab if left + 0.8 < v[0] < right - 0.8 and v[1] < edge_y - 0.2]
    if not notch:
        res.add(cid, False, "%s: key notch not found in the outline" % name)
        return
    inner = (min(notch), max(notch))
    key_w, key_c = inner[1] - inner[0], (inner[0] + inner[1]) / 2
    res.add(cid, within(key_w, *CEM["key_w"]), "%s: key notch %.2f mm wide, CEM %.2f +/- %.2f"
            % (name, key_w, *CEM["key_w"]))
    res.add(cid, within(key_c - left, CEM["key_from_left"], tol),
            "%s: tab edge to key centre %.2f mm, CEM %.2f +/- %.2f" % (name, key_c - left, CEM["key_from_left"], tol))
    res.add(cid, within(right - key_c, dim_b, tol),
            "%s: key centre to the far tab edge %.2f mm, CEM DIM B (%s) %.2f +/- %.2f" % (name, right - key_c, width, dim_b, tol))
    # the fingers
    bad = []
    for side in "AB":
        row = sorted((p for n, p in pads.items() if n.startswith(side)), key=lambda p: p["loc"][0])
        for p, q in zip(row, row[1:]):
            gap = q["loc"][0] - p["loc"][0]
            if not (within(gap, CEM["pitch"], 0.01) or within(gap, CEM["key_to_b12"] * 2, 0.01)):
                bad.append("%s pitch %.2f" % (side, gap))
    widths = [p["size"][0] for p in pads.values()]
    res.add(cid, all(within(w, *CEM["finger_w"]) for w in widths),
            "%s: finger width %.2f..%.2f mm, CEM %.2f +/- %.2f" % (name, min(widths), max(widths), *CEM["finger_w"]))
    res.add(cid, not bad, "%s: finger pitch %.2f mm with the key gap %.2f (key centre to B12 %.2f, CEM %.2f)%s"
            % (name, CEM["pitch"], pads["B12"]["loc"][0] - pads["B11"]["loc"][0],
               pads["B12"]["loc"][0] - key_c, CEM["key_to_b12"], "; " + ", ".join(bad) if bad else ""))
    tops = [edge_y - (p["loc"][1] - p["size"][1] / 2) for p in pads.values()]
    res.add(cid, all(within(t, CEM["pad_top"], tol) for t in tops),
            "%s: card edge to pad tops %.2f..%.2f mm, CEM %.2f +/- %.2f" % (name, min(tops), max(tops), CEM["pad_top"], tol))
    leads = {n: edge_y - (p["loc"][1] + p["size"][1] / 2) for n, p in pads.items()}
    short = sorted(n for n, v in leads.items() if v > 2.0)
    full = [v for n, v in leads.items() if n not in short]
    res.add(cid, all(within(v, *CEM["lead"]) for v in full),
            "%s: card edge to leading edge of the pads %.2f..%.2f mm, CEM %.2f +/- %.2f"
            % (name, min(full), max(full), *CEM["lead"]))
    ok = short == sorted(["A1", pin_c]) and all(within(leads[n], CEM["short_lead"], tol) for n in short)
    res.add(cid, ok, "%s: short (last-mate) pads %s at %s mm, CEM A1 and %s at %.2f"
            % (name, "+".join(short), "/".join("%.2f" % leads[n] for n in short), pin_c, CEM["short_lead"]))
    # the socket's side: the tab against the slot (the geometry repeats this in FreeCAD)
    sock = next(s for s in SOCKETS.values() if s["width"] == width)
    res.add(cid, tab_h - sock["depth"] > 0,
            "%s in %s: card shoulder %.2f mm above the housing (tab %.2f, insertion depth %.2f)"
            % (name, sock["part"], tab_h - sock["depth"], tab_h, sock["depth"]))
    res.add(cid, sock["rib_w"] < key_w - CEM["key_w"][1],
            "%s in %s: key rib %.2f mm (EasyEDA model) in the %.2f notch, >= %.3f a side at the notch's min"
            % (name, sock["part"], sock["rib_w"], key_w, (key_w - CEM["key_w"][1] - sock["rib_w"]) / 2))
    res.add(cid, b["thickness"] < sock["slot_w"] - 0.05,
            "%s in %s: card %.2f mm in the %.2f +/- 0.05 slot" % (name, sock["part"], b["thickness"], sock["slot_w"]))


def check_order(b, res):
    """MECH-002: what the fab order says about the fingers."""
    cid = "MECH-002"
    order, name = b["order"], b["name"]
    if not order:
        res.add(cid, False, "%s: no fab/order.json next to the board" % name)
        return
    t = order.get("thickness_mm")
    res.add(cid, t is not None and within(t, *CEM["thick"]),
            "%s: board %s mm, CEM %.2f +/- %.2f" % (name, t, *CEM["thick"]))
    res.add(cid, order.get("finger_finish") == "hard gold",
            "%s: finger finish %s (hard gold required, milestone-1.md)" % (name, order.get("finger_finish")))
    bev = order.get("finger_chamfer_deg")
    ok = bev is not None and (within(bev, *CEM["bevel_deg"]) or bev == CEM["bevel_waiver_deg"])
    res.add(cid, ok, "%s: finger bevel %s deg ordered, CEM Fig. 6-3 %.1f +/- %.1f deg%s" % (
        name, bev, *CEM["bevel_deg"],
        " (waived: JLC's nearest, milestone-1.md)" if bev == CEM["bevel_waiver_deg"] else ""))
    if not ok:
        res.note(cid, "JLC offers 30 and 45 deg bevels only (jlcpcb.com/help/article/jlcpcb-gold-fingers).")
        res.note(cid, "30 deg is the nearest to CEM (5 deg over its 25 deg max) and JLC's own recommendation")
        res.note(cid, "for easier insertion; ordering it needs milestone-1.md and kicadgen's order spec changed.")


# ------------------------------------------------------------------- slots
def slot_frames(main):
    """The world frame of every socket: B1's contact point on the slot's
    centre plane at the seat height, the row direction u and the card's
    component-side normal n (both horizontal)."""
    frames = []
    if main is None:
        for k, lcsc in enumerate(STANDIN["row"]):
            s = SOCKETS[lcsc]
            frames.append({"ref": "cpu" if s["width"] == "x8" else "slot%d" % k, "lcsc": lcsc,
                           "width": s["width"],
                           "b1": (0.0, k * STANDIN["pitch"], STANDIN["main_t"] + s["height"] - s["depth"]),
                           "u": (-1.0, 0.0, 0.0), "n": (0.0, 1.0, 0.0), "standin": True})
        return frames
    for fp in main["fps"]:
        if fp["lcsc"] not in SOCKETS:
            continue
        s = SOCKETS[fp["lcsc"]]
        pads = fp["pads"]
        pa, pb = s.get("pads", ("A1", "B1"))
        if pa not in pads or pb not in pads:
            frames.append({"ref": fp["ref"], "lcsc": fp["lcsc"], "width": s["width"],
                           "error": "footprint has no pads %s and %s (contacts A1, B1) to orient the card by"
                           % (pa, pb)})
            continue
        a1, b1 = step_xy(pads[pa]["pos"]), step_xy(pads[pb]["pos"])
        n = unit((b1[0] - a1[0], b1[1] - a1[1]))
        u = (-n[1], n[0])                      # z x n
        m = ((a1[0] + b1[0]) / 2, (a1[1] + b1[1]) / 2)
        frames.append({"ref": fp["ref"], "lcsc": fp["lcsc"], "width": s["width"],
                       "b1": (m[0], m[1], main["thickness"] + s["height"] - s["depth"]),
                       "u": (u[0], u[1], 0.0), "n": (n[0], n[1], 0.0), "standin": False})
    return frames


def card_transform(b, frame):
    """4x4 (row-major) matrix: card STEP coordinates -> world, for a card in
    the socket `frame`. The card's mid-plane z is filled in by FreeCAD
    (it knows where the export put the board body): returned as the matrix
    for z_mid = 0 plus the column that multiplies z_mid."""
    _, b1, a, d = edge_frame(b)
    a_s, d_s = step_xy(a), step_xy(d)
    up_s = (-d_s[0], -d_s[1])
    b1_s = step_xy(b1)
    e = b["tab"]["edge_y"]
    p0 = (b1_s[0] + e * d_s[0], b1_s[1] + e * d_s[1])      # card edge below B1
    u, n = frame["u"], frame["n"]
    z = (0.0, 0.0, 1.0)
    # R maps a_s -> u, up_s -> z, ez -> n
    cols_src = [(a_s[0], a_s[1], 0.0), (up_s[0], up_s[1], 0.0), (0.0, 0.0, 1.0)]
    cols_dst = [u, z, n]
    R = [[sum(cols_dst[k][i] * cols_src[k][j] for k in range(3)) for j in range(3)] for i in range(3)]
    t = [frame["b1"][i] - (R[i][0] * p0[0] + R[i][1] * p0[1]) for i in range(3)]
    return {"R": R, "t": t, "tz": [R[i][2] for i in range(3)]}     # world = R p + t - tz * z_mid


def world(tr, p, z_mid):
    return tuple(sum(tr["R"][i][j] * p[j] for j in range(3)) + tr["t"][i] - tr["tz"][i] * z_mid for i in range(3))


def fp_local(b, fp):
    _, b1, a, d = edge_frame(b)
    return to_local(fp["pos"], b1, a, d)


def label_part(b, word):
    """The part a kicadgen label (the word printed by an LED) belongs to."""
    at = [p for w, p in b["labels"] if w == word]
    if not at:
        return None
    leds = [fp for fp in b["fps"] if fp["fpid"].startswith("LED_") or fp["ref"].startswith("D")]
    return min(leds, key=lambda fp: math.dist(fp["pos"], at[0]), default=None)


def check_outline(b, res):
    """MECH-006: the body is slot.md's I/O card outline (the CPU card's
    too, cpu-bus.md), in the finger footprint's frame whatever the tab."""
    _, b1, a, d = edge_frame(b)
    verts = [to_local(p, b1, a, d) for p in b["outline"]]
    x0, y0, x1, y1 = IO_BODY
    body = [v for v in verts if v[1] < y1 - 0.05]
    top = [v for v in verts if abs(v[1] - y1) < 0.05]
    if not body or not top:
        res.add("MECH-006", False, "%s: no body above the tab line y = %.2f" % (b["name"], y1))
        return
    on_edge = all(min(abs(v[0] - x0), abs(v[0] - x1), abs(v[1] - y0)) < 0.01 for v in body)
    corners = [v for v in top if min(abs(v[0] - x0), abs(v[0] - x1)) < 0.01] or top
    got = (min(v[0] for v in body + top), min(v[1] for v in body), max(v[0] for v in body + top),
           max(v[1] for v in corners))
    ok = on_edge and all(abs(g - w) < 0.01 for g, w in zip(got, IO_BODY)) and len(body) == 2
    res.add("MECH-006", ok, "%s: body x %.2f..%.2f, y %.2f..%.2f (%d corners above the tab line), slot.md "
            "x %.1f..%.1f, y %.1f..%.2f, a plain rectangle" % (b["name"], got[0], got[2], got[1], got[3],
                                                               len(body), x0, x1, y0, y1))


def card_hole(b):
    """The card's M3 hole (>= 3 mm), the one nearest slot.md's spot, in the
    finger frame, or None."""
    holes = [(fp_local(b, fp), h["drill"]) for fp in b["fps"] for h in fp["holes"] if h["drill"] >= 3.0]
    return holes, min(holes, key=lambda h: math.dist(h[0], IO_HOLE), default=None)


def check_io_card(b, res):
    """MECH-005 and MECH-006 in the card's own frame."""
    name = b["name"]
    check_outline(b, res)
    holes, hole = card_hole(b)
    hole = hole if hole and math.dist(hole[0], IO_HOLE) < 0.01 else None
    if hole:
        res.add("MECH-005", within(hole[1], IO_HOLE_DRILL, 0.01),
                "%s: M3 hole at (%.2f, %.2f), %.2f mm NPTH, slot.md (%.1f, %.1f) %.1f"
                % (name, hole[0][0], hole[0][1], hole[1], *IO_HOLE, IO_HOLE_DRILL))
    else:
        res.add("MECH-005", False, "%s: no M3 hole at slot.md's (%.1f, %.1f); holes: %s"
                % (name, *IO_HOLE, ", ".join("(%.2f, %.2f)" % h[0] for h in holes) or "none"))
    led = label_part(b, "PWR")
    if led is None:
        res.add("MECH-006", False, "%s: no power LED (no LED labelled PWR)" % name)
    else:
        loc = fp_local(b, led)
        res.add("MECH-006", math.dist(loc, IO_PWR_LED) < 0.01 and led["side"] == "F",
                "%s: power LED %s at (%.2f, %.2f) on the %s side, slot.md (%.1f, %.1f) component side"
                % (name, led["ref"], loc[0], loc[1], "component" if led["side"] == "F" else "solder", *IO_PWR_LED))
    return hole, led


def check_row(frames, res):
    """MECH-005: the CPU socket and the six I/O sockets in one row: 20.32 mm
    apart, finger B1 in line along the row, the same way round, the same
    seat height (the card edge's rest), the CPU socket at one end."""
    row = [f for f in frames if f["width"] in ROW_SLOTS]
    for width, want in ROW_SLOTS.items():
        got = sum(f["width"] == width for f in row)
        res.add("MECH-005", got == want, "%d %s socket%s in the row, slot.md: %d"
                % (got, width, "" if got == 1 else "s", want))
    if not row:
        return
    n0 = row[0]["n"]
    row.sort(key=lambda f: sum(f["b1"][i] * n0[i] for i in range(3)))
    for f, g in zip(row, row[1:]):
        step = sum((g["b1"][i] - f["b1"][i]) * n0[i] for i in range(3))
        skew = sum((g["b1"][i] - f["b1"][i]) * f["u"][i] for i in range(3))
        par = sum(f["n"][i] * g["n"][i] for i in range(3))
        res.add("MECH-005", abs(abs(step) - ROW_PITCH) <= 0.05 and abs(skew) <= 0.05 and par > 0.99999,
                "%s -> %s: pitch %.3f mm (slot.md %.2f), finger B1 offset along the row %.3f, same way round: %s"
                % (f["ref"], g["ref"], abs(step), ROW_PITCH, skew, "yes" if par > 0.99999 else "NO"))
    cpu = [k for k, f in enumerate(row) if f["width"] == "x8"]
    if cpu:
        k = cpu[0]
        end = k in (0, len(row) - 1)
        # row is sorted along n0; the cards' component sides point along n
        towards = (k == 0) == (sum(n0[i] * row[k]["n"][i] for i in range(3)) > 0)
        res.add("MECH-005", end, "the CPU socket %s is %s of the row; its card's component side faces %s the I/O cards"
                % (row[k]["ref"], "at one end" if end else "NOT at an end (position %d)" % (k + 1),
                   "towards" if towards else "away from"))
    for lcsc in sorted({f["lcsc"] for f in row}):
        s = SOCKETS[lcsc]
        res.note("MECH-005", "%s %s: %.2f tall, %.2f deep, so the card edge rests %.2f mm above the main board (%s)"
                 % (lcsc, s["part"], s["height"], s["depth"], s["height"] - s["depth"], s["ds"]))
    zs = [f["b1"][2] for f in row]
    res.add("MECH-005", max(zs) - min(zs) <= 0.01,
            "seat heights in the row: x8 vs x1 differ by %.2f mm (card edge %.2f..%.2f above the main board's underside)"
            % (max(zs) - min(zs), min(zs), max(zs)))


# ------------------------------------------------------------------- report
def inputs_key(boards):
    h = hashlib.sha256()
    files = [b["pcb"] for b in boards.values()]
    files += [os.path.join(os.path.dirname(b["pcb"]), "fab", "order.json") for b in boards.values()]
    files += glob.glob(os.path.join(HERE, "*.py")) + [os.path.join(ROOT, "doc", "hardware", "parts.md")]
    for f in sorted(files):
        if os.path.exists(f):
            h.update(f.encode())
            with open(f, "rb") as fh:
                h.update(hashlib.sha256(fh.read()).digest())
    return h.hexdigest()


def antenna_lcsc():
    """The antenna the order uses: parts.md's 'Wi-Fi antenna' row."""
    with open(os.path.join(ROOT, "doc", "hardware", "parts.md")) as f:
        for line in f:
            if line.startswith("| Wi-Fi antenna"):
                m = re.search(r"\|\s*(C\d+)\s*\|", line)
                return m.group(1) if m else None
    return None


def run():
    os.makedirs(OUT, exist_ok=True)
    found = discover()
    boards = {n: read_board(n, p) for n, p in found.items()}
    key = inputs_key(boards)
    cache = os.path.join(OUT, "results.json")
    if os.path.exists(cache):
        with open(cache) as f:
            old = json.load(f)
        if old.get("key") == key:
            return old
    res = Result()
    cards = [b for b in boards.values() if b["kind"] in ("io", "cpu", "system")]
    mains = [b for b in boards.values() if b["kind"] == "main"]
    main = mains[0] if mains else None
    ignored = sorted(n for n, b in boards.items() if b["kind"] is None)
    for b in cards:
        check_fingers(b, res)
        check_order(b, res)
    frames = slot_frames(main)
    io_cards = [b for b in cards if b["kind"] == "io"]
    for b in cards:
        if b["kind"] in ROW_KINDS:
            check_io_card(b, res)
    for f in frames:
        if "error" in f:
            res.add("MECH-005", False, "%s (%s): %s" % (f["ref"], f["lcsc"], f["error"]))
    check_row([f for f in frames if "error" not in f], res)

    placements = []
    for b in cards:
        want = b["width"]
        for f in frames:
            if f["width"] == want and "error" not in f:
                placements.append({"card": b["name"], "slot": f["ref"], "tr": card_transform(b, f)})
    job = {
        "root": ROOT, "out": OUT,
        "cards": {b["name"]: {"step": export_step(b), "kind": b["kind"], "width": b["width"],
                              "thickness": b["thickness"], "fps": b["fps"], "tab": b["tab"],
                              "edge": list(edge_frame(b)[1:]),
                              "hole": (lambda h: h and h[0])(card_hole(b)[1]),
                              "pwr_led": (lambda led: led and led["ref"])(label_part(b, "PWR"))}
                  for b in cards},
        "main": main and {"name": main["name"], "step": export_step(main), "thickness": main["thickness"],
                          "fps": main["fps"]},
        "frames": frames, "placements": placements, "sockets": SOCKETS,
        "housing_before_b1": HOUSING_BEFORE_B1, "slot_before_b1": SLOT_BEFORE_B1,
        "slot_after_tab": SLOT_AFTER_TAB, "cem": CEM, "min_gap": MIN_GAP, "plugs": PLUGS,
        "min_overhang": MIN_OVERHANG, "modules": MODULES, "antennas": ANTENNAS,
        "antenna": antenna_lcsc(), "cable_min_gap": CABLE_MIN_GAP, "io_hole": IO_HOLE,
        "io_pwr_led": IO_PWR_LED, "rail_keepout": RAIL_KEEPOUT, "tab_zone": TAB_ZONE,
        "standin": main is None, "standin_cfg": STANDIN,
    }
    job_path = os.path.join(OUT, "job.json")
    with open(job_path, "w") as f:
        json.dump(job, f, indent=1)
    geo_path = os.path.join(OUT, "geometry.json")
    if os.path.exists(geo_path):
        os.remove(geo_path)
    env = dict(os.environ, MECH_JOB=job_path)
    r = subprocess.run(["freecadcmd", os.path.join(HERE, "fc_check.py")], env=env, capture_output=True, text=True)
    if r.returncode != 0 or not os.path.exists(geo_path):
        raise SystemExit("FreeCAD check failed\n%s%s" % (r.stdout[-4000:], r.stderr[-4000:]))
    with open(geo_path) as f:
        geo = json.load(f)
    for cid, lines in geo["checks"].items():
        for ok, text in lines:
            if ok is None:
                res.note(cid, text)
            else:
                res.add(cid, ok, text)

    header = ["Mechanical fit (verification.md 4.7): hw/mech/fit.py",
              "boards: " + ", ".join("%s (%s)" % (b["name"], b["kind"]) for b in boards.values() if b["kind"]),
              "not slot boards, ignored: " + (", ".join(ignored) or "none"),
              "slots: " + ("STAND-IN, no main board yet: the row is 1 x %s (CPU) + 6 x %s at %.2f mm pitch "
                           "on a %.1f mm board, component sides facing away from the CPU socket"
                           % (SOCKETS["C404111"]["part"], SOCKETS["C404113"]["part"], STANDIN["pitch"],
                              STANDIN["main_t"])
                           if main is None else "main board %s: %d sockets" % (main["name"], len(frames))),
              "not yet designed: " + (", ".join(k for k in ("main", "cpu", "system")
                                                  if not any(b["kind"] == k for b in boards.values())) or "none")]
    have = {k: any(b["kind"] == k for b in boards.values()) for k in ("main", "cpu", "system")}
    if not (have["main"] and have["system"]):
        res.add("MECH-008", False, "the system card's placement can't be checked yet: needs the main board "
                "(its x4 socket) and the system card built (main: %s, system: %s)"
                % tuple("yes" if have[k] else "no" for k in ("main", "system")))
    if not have["cpu"]:
        res.add("MECH-003", False, "no CPU card built: position 1 of the row is empty, so CPU card -> I/O slot 1 "
                "is unchecked")
    if not io_cards:
        for cid in ("MECH-003", "MECH-004", "MECH-005", "MECH-006"):
            res.add(cid, False, "no I/O card found")
    out = {"key": key, "header": header, "checks": res.checks}
    with open(cache, "w") as f:
        json.dump(out, f, indent=1)
    return out


def report(out):
    lines = list(out["header"]) + [""]
    for cid, c in out["checks"].items():
        lines.append("%s %s: %s" % (cid, "PASS" if c["ok"] else "FAIL", c["title"]))
        lines += ["  " + t for t in c["lines"]]
        lines.append("")
    lines.append("overview: build/mech/overview.png")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", help="exit with this check's status only (e.g. MECH-003)")
    args = ap.parse_args()
    if args.check and args.check not in CHECKS:
        sys.exit("unknown check %s" % args.check)
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, ".lock"), "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)          # parallel test runs share one run
        out = run()
    text = report(out)
    with open(os.path.join(OUT, "report.txt"), "w") as f:
        f.write(text + "\n")
    if args.check:
        c = out["checks"][args.check]
        print("%s %s: %s" % (args.check, "PASS" if c["ok"] else "FAIL", c["title"]))
        print("\n".join("  " + t for t in c["lines"]))
        print("\n(full report: build/mech/report.txt)")
        return 0 if c["ok"] else 1
    print(text)
    return 0 if all(c["ok"] for c in out["checks"].values()) else 1


if __name__ == "__main__":
    sys.exit(main())
