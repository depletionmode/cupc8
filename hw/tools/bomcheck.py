#!/usr/bin/env python3
"""Verification 4.3 (footprints and symbols) and the BOM half of 4.8 (BOM <->
schematic), for every line of a board's JLC BOM (BRD-001).

    python3 hw/tools/bomcheck.py <board>... | all  [--out DIR]
                                 [--update-rotations] [--refetch]

<board> is a script in hw/boards (all: every one). With its build (build/hw/<board>, or --out)
the check reads the schematic, fab/bom.csv, fab/cpl.csv and the board that
kicadgen.pipeline wrote; without one it generates the schematic alone (a few
seconds) and checks the parts, not the fab files. kicadgen.pipeline runs it
after "JLC BOM + CPL".

Per BOM line (one LCSC part):
  1. package: JLC's package for the LCSC code (its parts API) is the
     footprint's (0603 in R_0603_..., SOT-353 in SOT-353-5_..., the size of
     an "SMD,13.2x12.5mm" in the name), and the footprint's pads are the ones
     of the EasyEDA footprint the LCSC part links to: same count, each pad
     within PAD_TOLERANCE of its match, in one of the four orientations
  2. pinout: every symbol pin has a pad and every pad a pin. A part with more
     than two pins must have hw/parts/<LCSC>.yaml, the datasheet's pin table
     (with where it came from): the symbol's pin names must be the table's,
     and the pins must run counterclockwise seen from the top as the
     datasheet's numbering does. A two-pin part with named pins (an LED:
     K and A) must put each on the pad where the EasyEDA part has it, so the
     cathode is where JLC's footprint (and its part in the tape) has it
  3. rotation: JLC places its own footprint (EasyEDA's, for the LCSC code)
     rotated by the CPL's angle, so a KiCad footprint drawn in another
     orientation needs a correction. hw/parts/jlc_rotation.yaml holds one per
     footprint, and kicadgen.jlc_fab adds it to KiCad's angle; this check
     derives each from the pads (the rotation taking the KiCad footprint onto
     EasyEDA's, pin 1 onto pin 1, cathode onto cathode) and the table must
     agree. cpl.csv must be the board's angles plus the table, top side only
  4. BOM <-> schematic: bom.csv is exactly the schematic's parts with an LCSC
     number, grouped by value, footprint and LCSC code, and cpl.csv places
     exactly those designators

JLC's zero is taken to be the EasyEDA footprint's: that is JLC's own library.
The 4.9 hand check (the CPL rendered over the board) still reviews it.

--update-rotations writes the derived corrections for this board's footprints
into jlc_rotation.yaml (other entries are kept), for a new footprint.

JLC's side of each part (its package name, and the EasyEDA footprint pads
and symbol pin names, fetched with jlcparts and easyeda2kicad) is recorded
in hw/parts/easyeda/<LCSC>.yaml the first time the part is seen: commit it.
The check then gives the same answer every run without the network (EasyEDA
refuses bursts of requests). --refetch compares the records with JLC's today.
With CUPC8_OFFLINE=1 a part not recorded yet is skipped, and the result says so.
"""

import csv
import importlib.util
import math
import re
import os
import re
import shutil
import subprocess
import sys

import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
import kicadgen as kg  # noqa: E402

PARTS = os.path.join(ROOT, "hw", "parts")
ROTATIONS = os.path.join(PARTS, "jlc_rotation.yaml")
RECORDS = os.path.join(PARTS, "easyeda")
CACHE = os.path.join(ROOT, "build", "parts", "easyeda")
PAD_TOLERANCE = 0.2          # mm: 0402 pads are 0.27 mm off 0603's, 0603's 0.04 off EasyEDA's
POLAR = {"K": "K", "A": "A", "CATHODE": "K", "ANODE": "A", "-": "K", "+": "A", "C": "K"}   # 2-pin names (C: EasyEDA diodes)


def rotations():
    """{footprint id: degrees added to KiCad's rotation for JLC's CPL}."""
    with open(ROTATIONS) as f:
        return {fp: e["rotation"] for fp, e in (yaml.safe_load(f) or {}).items()}


# ------------------------------------------------------------------ inputs

def footprint_pads(path):
    """[(number, x, y)] of the copper pads with a number, y up (mm)."""
    fp = kg.parse(open(path).read())
    out = []
    for p in kg.find(fp, "pad"):
        at = kg.find1(p, "at")
        if str(p[1]) and p[2] != "np_thru_hole":
            out.append((str(p[1]), float(at[1]), -float(at[2])))
    return out


def fp_path(fpid):
    lib, name = fpid.split(":")
    return os.path.join(kg.footprint_dir(lib), name + ".kicad_mod")


def fetch(lcsc, fresh=True):
    """JLC's part for an LCSC code, from the network: its package name (JLC's
    parts API) and the EasyEDA part it links to (easyeda2kicad), which is
    what JLC's placer turns by the CPL angle."""
    import jlcparts
    hits = [p for p in jlcparts.query(lcsc, 5) if p["componentCode"] == lcsc]
    if not hits:
        raise SystemExit("%s: not in JLC's parts library" % lcsc)
    base = os.path.join(CACHE, lcsc)
    sym_file = base + "/lib.kicad_sym"
    if fresh or not os.path.exists(sym_file):
        shutil.rmtree(base, ignore_errors=True)
        os.makedirs(base)
        r = subprocess.run(["easyeda2kicad", "--symbol", "--footprint", "--overwrite", "--lcsc_id", lcsc,
                            "--output", base + "/lib"], capture_output=True, text=True)
        if r.returncode != 0 or not os.path.exists(sym_file):
            raise SystemExit("%s: easyeda2kicad failed (EasyEDA refuses bursts: rerun later)\n%s%s"
                             % (lcsc, r.stdout, r.stderr))
        import jlcimport                 # the pad renumbering hw/lib/jlc has (PAD_RENUMBER)
        for f in os.listdir(base + "/lib.pretty"):
            jlcimport.fix_footprint(os.path.join(base + "/lib.pretty", f))
    for sym in kg.find(kg.parse(open(sym_file).read()), "symbol"):
        props = {str(p[1]): str(p[2]) for p in kg.find(sym, "property")}
        if props.get("LCSC Part") == lcsc:
            name = props["Footprint"].split(":")[1]
            pins = kg.symbol_pins(["symbol", kg.Q("ee:" + str(sym[1]))] + sym[2:])
            pads = footprint_pads(os.path.join(base, "lib.pretty", name + ".kicad_mod"))
            return {"lcsc": lcsc, "jlc_package": hits[0]["componentSpecificationEn"] or "",
                    "easyeda_footprint": name,
                    "pins": {n: p[3] for n, p in sorted(pins.items(), key=lambda kv: (len(kv[0]), kv[0]))},
                    "pads": [[n, round(x, 4) + 0.0, round(y, 4) + 0.0] for n, x, y in pads]}
    raise SystemExit("%s: no symbol for it in %s" % (lcsc, sym_file))


def record(lcsc, refetch=False):
    """JLC's part (fetch()) as recorded in hw/parts/easyeda/<LCSC>.yaml, so the
    check is the same every run and needs no network. A part not recorded yet
    is fetched and recorded (commit the file); None when CUPC8_OFFLINE stops
    that. With refetch, a part that changed at JLC is an error."""
    path = os.path.join(RECORDS, lcsc + ".yaml")
    old = yaml.safe_load(open(path)) if os.path.exists(path) else None
    if (old and not refetch) or os.environ.get("CUPC8_OFFLINE"):
        return old
    new = fetch(lcsc, fresh=bool(old))
    os.makedirs(RECORDS, exist_ok=True)
    with open(path, "w") as f:
        f.write("# JLC's part %s as hw/tools/bomcheck.py fetched it: JLC's package name, and the\n"
                "# EasyEDA footprint JLC places (pads: number, x, y up, mm) with its symbol's pin\n"
                "# names. bomcheck.py --refetch compares it with JLC's today.\n" % lcsc)
        yaml.safe_dump(new, f, sort_keys=False, width=200, allow_unicode=True, default_flow_style=None)
    if old and old != yaml.safe_load(open(path)):
        raise SystemExit("%s: JLC's part changed since it was recorded: see the diff of %s"
                         % (lcsc, os.path.relpath(path, ROOT)))
    return new


def schematic_parts(sch):
    """{ref: {value, footprint, lcsc, pins {number: name}}} for the placed
    parts, from the netlist kicad-cli exports (as jlc_fab reads it) and the
    symbols the schematic embeds."""
    comps, _ = kg.export_netlist(sch, sch[:-len(".kicad_sch")] + ".bomcheck.net")
    os.remove(sch[:-len(".kicad_sch")] + ".bomcheck.net")
    doc = kg.parse(open(sch).read())
    lib = {str(s[1]): s for s in kg.find(kg.find1(doc, "lib_symbols"), "symbol")}
    libid = {}
    for s in kg.find(doc, "symbol"):
        ref = {str(p[1]): str(p[2]) for p in kg.find(s, "property")}.get("Reference")
        libid.setdefault(ref, str(kg.find1(s, "lib_id")[1]))
    out = {}
    for ref, c in comps.items():
        if ref.startswith("#"):
            continue
        f = c.get("fields", {})
        pins = {}
        if libid.get(ref) in lib:                 # every unit's pins: an FPGA is drawn in several
            sym = lib[libid[ref]]
            units = {int(m.group(1)) for m in (re.search(r"_(\d+)_\d+$", str(s[1])) for s in kg.find(sym, "symbol"))
                     if m}
            for u in sorted(units | {1}):
                pins.update(kg.symbol_pins(sym, u))
        out[ref] = {"value": c["value"], "footprint": c["footprint"], "lcsc": f.get("LCSC") or f.get("LCSC Part"),
                    "pins": {n: p[3] for n, p in pins.items()}}
    return out


def board_rotations(pcb):
    """{ref: (rotation, layer)} of the footprints on the board."""
    out = {}
    for fp in kg.find(kg.parse(open(pcb).read()), "footprint"):
        at = kg.find1(fp, "at")
        ref = {str(p[1]): str(p[2]) for p in kg.find(fp, "property")}.get("Reference")
        out[ref] = (float(at[3]) if len(at) > 3 else 0.0, str(kg.find1(fp, "layer")[1]))
    return out


# ------------------------------------------------------------------ checks

def rot(pads, deg):
    a = math.radians(deg)
    c, s = round(math.cos(a)), round(math.sin(a))
    return [(n, x * c - y * s, x * s + y * c) for n, x, y in pads]


def fits(kpads, epads, key):
    """The KiCad pads (already turned) land each on an EasyEDA pad with the
    same key (a pin number or function), within PAD_TOLERANCE."""
    if len(kpads) != len(epads):
        return False
    for n, x, y in kpads:
        near = min(epads, key=lambda e: math.hypot(e[1] - x, e[2] - y))
        if math.hypot(near[1] - x, near[2] - y) > PAD_TOLERANCE or (key and key(n, "k") != key(near[0], "e")):
            return False
    return True


# JLC package strings that no footprint name spells out: what the name says
# instead (upper case). The pads are still compared with EasyEDA's.
PACKAGE_NAMES = {
    "LQFN-56(7X7)": "QFN-56-1EP_7X7MM",          # RP2040
    "SOIC-8-208MIL": "SOIC-8_5.3X5.3MM",         # W25Q16JVSSIQ
    "SOT-23-6L": "SOT-23-6",                     # USBLC6-2SC6
    "SMD3225-4P": "SMD_4P-L3.2-W2.5",            # 3225 crystal
}


def package_ok(pkg, fp_name):
    """JLC's package string names the footprint's package."""
    p = pkg.upper().replace(" ", "")
    name = fp_name.upper()
    if p in PACKAGE_NAMES and PACKAGE_NAMES[p] in name:
        return True
    if p.startswith("SMD,") and "X" in p:           # "SMD,13.2x12.5mm": the body size
        a, b = (float(v) for v in p[4:].rstrip("M").split("X")[:2])
        # as numbers: JLC writes "3x3mm" where the footprint says L3.0-W3.0
        body = [(float(l), float(w)) for l, w in re.findall(r"L([\d.]+)-W([\d.]+)", name)]
        return (a, b) in body or (b, a) in body
    if p.isdigit():                                  # chip sizes: 0402, 0603, 0805 ...
        return ("_%s_" % p) in name or name.startswith(p) or ("_%s" % p) in name
    m = re.fullmatch(r"(\d{4})X(\d)", p)             # "0603x4": an array of n chips, 2n pads
    if m:
        return ("_%s" % m.group(1)) in name and ("-%dP" % (2 * int(m.group(2))) in name or p in name)
    m = re.fullmatch(r"(.+)\((\d+(?:\.\d+)?)X(\d+(?:\.\d+)?)\)", p)   # "TQFP-144(20x20)": and its body
    if m:
        body = ["%.1f" % float(v) for v in m.group(2, 3)]
        return name.startswith(m.group(1)) and "L%s-W%s" % tuple(body) in name
    m = re.fullmatch(r"(.+)-(150|208)MIL", p)        # "SOIC-8-208mil": the body width in mils
    if m:
        return name.startswith(m.group(1)) and "-W%s-" % {"150": "3.9", "208": "5.3"}[m.group(2)] in name
    m = re.fullmatch(r"(SOT-23-\d)L", p)             # "SOT-23-6L": JLC's name for a plain SOT-23-6
    if m:
        return name.startswith(m.group(1) + "_")
    return name.startswith(p) or ("_%s" % p) in name or ("_%s_" % p) in name


def ccw(pads, first, last):
    """Pins first..last run counterclockwise round their centre, seen from the top."""
    by = {n: (x, y) for n, x, y in pads}
    pts = [by[str(i)] for i in range(first, last + 1)]
    cx, cy = sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts)
    ang = [math.atan2(y - cy, x - cx) for x, y in pts]
    steps = [(b - a) % (2 * math.pi) for a, b in zip(ang, ang[1:] + ang[:1])]   # each in [0, 2pi)
    # counterclockwise: every step turns left, and once round in all
    return all(s > 1e-9 for s in steps) and abs(sum(steps) - 2 * math.pi) < 1e-6


def datasheet_table(lcsc):
    path = os.path.join(PARTS, lcsc + ".yaml")
    if not os.path.exists(path):
        return None
    d = yaml.safe_load(open(path))
    pins = {str(k): ([v] if isinstance(v, str) else list(v)) for k, v in d["pins"].items()}
    for src, copies in (d.get("pad_copies") or {}).items():
        for n in copies:
            pins[str(n)] = pins[str(src)]
    return d, pins


def check_line(fpid, lcsc, refs, parts, table, problems, notes, refetch=False):
    """Checks 1-3 for one BOM line; returns the corrections that fit (or None
    when EasyEDA's part is unavailable offline)."""
    say = lambda msg: problems.append("%s %s (%s): %s" % (lcsc, fpid, ",".join(refs), msg))
    fp_name = fpid.split(":")[1]
    kpads = footprint_pads(fp_path(fpid))
    pins = parts[refs[0]]["pins"]
    for r in refs[1:]:
        if parts[r]["pins"] != pins:
            say("%s's symbol differs from %s's" % (r, refs[0]))
    # 2: symbol <-> footprint <-> datasheet
    pads = {n for n, _, _ in kpads}
    if set(pins) != pads:
        say("symbol pins without pads %s, pads without pins %s" % (sorted(set(pins) - pads), sorted(pads - set(pins))))
    ds = datasheet_table(lcsc)
    if ds:
        d, want = ds
        for n in sorted(set(want) | set(pins), key=lambda s: (len(s), s)):
            if n not in pins or n not in want or pins[n].upper() not in [w.upper() for w in want[n]]:
                say("pin %s is %r in the symbol, %r in the datasheet (%s)"
                    % (n, pins.get(n), "/".join(want.get(n, ["none"])), d["source"]))
        if d.get("ccw") and set(str(i) for i in range(d["ccw"][0], d["ccw"][1] + 1)) <= pads \
                and not ccw(kpads, *d["ccw"]):
            say("pads %d-%d do not run counterclockwise (top view) as the datasheet numbers them" % tuple(d["ccw"]))
    elif len(pins) > 2:
        say("no datasheet pin table: add hw/parts/%s.yaml" % lcsc)
    polar = len(pins) == 2 and all(p.upper() in POLAR for p in pins.values())
    # 1: package, JLC's name for it and EasyEDA's pads
    jlc = record(lcsc, refetch)
    if jlc is None:
        notes.add("%s not recorded in hw/parts/easyeda and CUPC8_OFFLINE: package and rotation unchecked" % lcsc)
        return None
    pkg = jlc["jlc_package"]
    # a footprint whose name doesn't spell JLC's package ("LQFN-56(7x7)" for
    # KiCad's QFN-56-1EP_7x7mm_..., "SMD" for a connector) passes when the
    # part's datasheet table names it under `footprints:`, checked by hand;
    # the pads are still compared with EasyEDA's below
    if not package_ok(pkg, fp_name) and not (ds and fp_name in (ds[0].get("footprints") or [])):
        say("JLC's package is %r, the footprint is %s" % (pkg, fp_name))
    if ds and ds[0].get("package") and pkg.upper().replace(" ", "") != ds[0]["package"].upper().replace(" ", ""):
        say("JLC's package is %r, the datasheet table's %r" % (pkg, ds[0]["package"]))
    ee_name, epins = jlc["easyeda_footprint"], {str(k): v for k, v in jlc["pins"].items()}
    epads = [(str(n), x, y) for n, x, y in jlc["pads"]]
    if polar:
        names = {"k": {n: POLAR[v.upper()] for n, v in pins.items()},
                 "e": {n: POLAR.get(v.upper(), "?" + v) for n, v in epins.items()}}
        key = lambda n, side: names[side].get(n)
        if sorted(names["e"].values()) != ["A", "K"]:
            say("EasyEDA's symbol (%s) names its pins %s, not a cathode and an anode" % (ee_name, epins))
    elif len(pins) == 2:
        key = None                              # a resistor or capacitor turns either way
    else:
        key = lambda n, side: n                 # pad numbers are the datasheet's pin numbers
    turns = [a for a in (0, 90, 180, 270) if fits(rot(kpads, a), epads, key)]
    if not turns:
        say("its pads match EasyEDA's %s in no orientation (%d pads vs %d, within %.1f mm%s)"
            % (ee_name, len(kpads), len(epads), PAD_TOLERANCE, ", by pin" if key else ""))
        return []
    # the KiCad footprint turned by a is JLC's at 0: JLC's angle is KiCad's - a
    ok = sorted((-a) % 360 for a in turns)
    if fpid not in table:
        say("no entry in hw/parts/jlc_rotation.yaml; the pads say %s (bomcheck.py --update-rotations)"
            % " or ".join(map(str, ok)))
    elif table[fpid] % 360 not in ok:
        say("jlc_rotation.yaml adds %s degrees, but JLC's footprint (EasyEDA %s) is KiCad's turned by %s"
            % (table[fpid], ee_name, " or ".join(map(str, ok))))
    return ok, ee_name


def bom_groups(parts):
    groups = {}
    for r, p in parts.items():
        if p["lcsc"]:
            groups.setdefault((p["value"], p["footprint"], p["lcsc"]), []).append(r)
    return {k: sorted(v, key=lambda r: (r.rstrip("0123456789"), int(r[len(r.rstrip("0123456789")):] or 0)))
            for k, v in groups.items()}


def check_fab(fab, groups, pcb, table, problems):
    """4: bom.csv and cpl.csv against the schematic and the board."""
    with open(os.path.join(fab, "bom.csv")) as f:
        rows = list(csv.DictReader(f))
    want = {(v, fp.split(":")[1], code, ",".join(sorted(refs))) for (v, fp, code), refs in groups.items()}
    have = {(r["Comment"], r["Footprint"], r["LCSC Part #"], ",".join(sorted(r["Designator"].split(","))))
            for r in rows}
    for line in sorted(have - want):
        problems.append("bom.csv line %s is not the schematic's" % (line,))
    for line in sorted(want - have):
        problems.append("the schematic's %s is not in bom.csv" % (line,))
    fps = {r: fp for (_, fp, _), refs in groups.items() for r in refs}
    board = board_rotations(pcb)
    with open(os.path.join(fab, "cpl.csv")) as f:
        cpl = {r["Designator"]: r for r in csv.DictReader(f)}
    if set(cpl) != set(fps):
        problems.append("cpl.csv places %s; the BOM has %s" % (sorted(set(cpl) - set(fps)) or "no extra",
                                                                 sorted(set(fps) - set(cpl)) or "none missing"))
    for ref in sorted(set(cpl) & set(fps)):
        row = cpl[ref]
        if row["Layer"] != "Top":
            problems.append("%s: cpl.csv has it on the %s; JLC assembles the top side" % (ref, row["Layer"]))
        want_rot = (board[ref][0] + table.get(fps[ref], 0)) % 360
        if abs((float(row["Rotation"]) - want_rot + 180) % 360 - 180) > 0.01:
            problems.append("%s: cpl.csv rotation %s, the board's %g plus jlc_rotation.yaml's %s is %g"
                            % (ref, row["Rotation"], board[ref][0], table.get(fps[ref], 0), want_rot))


def update_rotations(derived):
    with open(ROTATIONS) as f:
        text = f.read()
    head = text[:text.index("\n\n") + 2] if "\n\n" in text else ""
    entries = yaml.safe_load(text) or {}
    for fpid, (ok, sources) in derived.items():
        if fpid in entries and entries[fpid]["rotation"] % 360 in ok:
            continue
        entries[fpid] = {"rotation": ok[0],
                         "source": "derived by bomcheck.py: the KiCad pads onto EasyEDA's %s (%s)"
                                   % (", ".join(sorted({s[0] for s in sources})),
                                      ", ".join(sorted({s[1] for s in sources})))}
    with open(ROTATIONS, "w") as f:
        f.write(head + yaml.safe_dump(entries, sort_keys=True, width=200, allow_unicode=True))


def check(name, out=None, update=False, refetch=False):
    """Run every check on board `name`; raise SystemExit listing the problems,
    or return a one-line summary. kicadgen.pipeline calls this."""
    out = os.path.abspath(out or os.path.join(ROOT, "build", "hw", name))
    sch, pcb, fab = (os.path.join(out, name + ".kicad_sch"), os.path.join(out, name + ".kicad_pcb"),
                     os.path.join(out, "fab"))
    have_fab = all(os.path.exists(p) for p in (sch, pcb, os.path.join(fab, "bom.csv"), os.path.join(fab, "cpl.csv")))
    if not have_fab:                             # no build: the schematic alone
        spec = importlib.util.spec_from_file_location("board_" + name, os.path.join(ROOT, "hw", "boards", name + ".py"))
        board = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(board)
        tmp = os.path.join(ROOT, "build", "bomcheck", name)
        os.makedirs(tmp, exist_ok=True)
        sch = os.path.join(tmp, name + ".kicad_sch")
        board.schematic(sch, ("cupc8", "jlc"))
        kg.write_project(os.path.join(tmp, name + ".kicad_pro"))
    parts = schematic_parts(sch)
    table = rotations()
    groups = bom_groups(parts)
    problems, notes, derived = [], set(), {}
    for (_, fpid, lcsc), refs in sorted(groups.items(), key=lambda g: g[1][0]):
        r = check_line(fpid, lcsc, refs, parts, table, problems, notes, refetch)
        if r and r[0]:
            ok, ee_name = r
            prev = derived.get(fpid)
            if prev and not set(prev[0]) & set(ok):
                problems.append("%s: %s needs %s but %s needs %s; key the table by part"
                                % (fpid, lcsc, ok, prev[1][0][1], prev[0]))
            derived[fpid] = (sorted(set(ok) & set(prev[0])) if prev else ok,
                             (prev[1] if prev else []) + [(ee_name, lcsc)])
    if update:
        update_rotations(derived)
        return "jlc_rotation.yaml updated"
    if have_fab:
        check_fab(fab, groups, pcb, table, problems)
    else:
        notes.add("no build in %s: bom.csv/cpl.csv not checked" % out.replace(ROOT + "/", ""))
    if problems:
        raise SystemExit("BOM check (verification 4.3, 4.8), %d problem%s:\n  %s"
                         % (len(problems), "" if len(problems) == 1 else "s", "\n  ".join(problems)))
    return "%d BOM lines pass%s" % (len(groups), "; " + "; ".join(sorted(notes)) if notes else "")


def main():
    import argparse
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("boards", nargs="+", help="scripts in hw/boards, or all")
    ap.add_argument("--out", help="the board's build directory (default build/hw/<board>)")
    ap.add_argument("--update-rotations", action="store_true")
    ap.add_argument("--refetch", action="store_true", help="compare the recorded JLC parts with JLC's today")
    a = ap.parse_args()
    boards = a.boards
    if boards == ["all"]:
        # every board script: one that draws a schematic (not a shared module
        # such as rp2040card.py)
        here = os.path.join(ROOT, "hw", "boards")
        boards = sorted(f[:-3] for f in os.listdir(here) if f.endswith(".py")
                        and "\ndef schematic(" in open(os.path.join(here, f)).read())
    failed = 0
    for b in boards:
        try:
            print("BRD-001 %s: %s" % (b, check(b, a.out, a.update_rotations, a.refetch)), flush=True)
        except SystemExit as e:
            print("BRD-001 %s: FAIL %s" % (b, e), flush=True)
            failed += 1
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
