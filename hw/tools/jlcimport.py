#!/usr/bin/env python3
"""Import JLC/LCSC parts into hw/lib/jlc with easyeda2kicad, then fix what
the conversion gets wrong, and check the result.

    python3 hw/tools/jlcimport.py C165948 [C... ]

Fix-ups, applied to every symbol in hw/lib/jlc.kicad_sym:
  - EasyEDA types every pin "unspecified", which ERC flags on every
    connection: pins get their type from PIN_TYPES for the part, else
    passive (the KiCad convention for connectors and passives)
  - EasyEDA pins are 2.54 mm, too short for numbers like "A1B12": every pin
    of a symbol is lengthened to fit its longest number with room for a
    no-connect cross, keeping the body end fixed, in 2.54 mm steps (on grid)
Fix-ups, applied to every footprint in hw/lib/jlc.pretty:
  - unnamed plated holes with no copper ring (drill = pad size) are EasyEDA's
    locating pegs: they become non-plated (np_thru_hole)
  - 3D model paths become ${CUPC8_LIB}/jlc.3dshapes/..., which
    hw/tools/kicadgen.py resolves; easyeda2kicad writes absolute paths
  - custom pads that are one rectangle become plain rect pads of the same
    size: easyeda2kicad strokes the polygon 0.1 mm wide, which grows the
    pad 0.05 mm all round and eats the clearance to its neighbours
  - silkscreen is kept 0.15 mm clear of every pad and hole: lines are cut
    where they pass one, and marks (circles) on a pad are dropped
Checks, per imported part:
  - every symbol pin number has a pad in the footprint and every named pad
    has a pin, so nothing can be left unwired
  - the 3D model sits on the footprint: its outline's centre is within
    MODEL_TOLERANCE of the courtyard's. EasyEDA models are sometimes offset
    (C165948's was 2 mm out), which hides real fit problems. A part that
    fails needs its model fixed, or KiCad's own footprint if it has one.
"""

import math
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
import kicadgen as kg  # noqa: E402

LIB = os.path.join(ROOT, "hw", "lib", "jlc")


# per-part pin types, by pin name, for parts where ERC should check more than
# connectivity (ICs: power inputs, outputs and so on)
PIN_TYPES = {}


NC_ROOM = 1.6                            # a no-connect cross at the pin's end


def lengthen_pins(chunk):
    nums = re.findall(r'\(pin \w+ \w+\s*\(at [-\d.]+ [-\d.]+ \d+\)\s*\(length [\d.]+\)'
                      r'[^)]*?\(name "[^"]*"[^\n]*\n\s*\(number "([^"]*)"', chunk)
    if not nums:
        return chunk
    need = max(kg.text_extent(n)[0] for n in nums) + NC_ROOM
    length = max(2.54, math.ceil(need / 2.54) * 2.54)

    def fix(m):
        # groups: 1 "(pin type style", 2 x, 3 y, 4 angle, 5 whitespace, 6 length
        x, y, ang, ln = float(m.group(2)), float(m.group(3)), int(m.group(4)), float(m.group(6))
        extra = length - ln
        if extra <= 1e-6:
            return m.group(0)
        # the pin runs from (at) into the body at `ang`: move (at) back by `extra`
        dx, dy = {0: (-1, 0), 90: (0, -1), 180: (1, 0), 270: (0, 1)}[ang]
        return "%s(at %s %s %d)%s(length %s)" % (m.group(1), fmt(x + dx * extra), fmt(y + dy * extra),
                                                  ang, m.group(5), fmt(length))
    return re.sub(r'(\(pin \w+ \w+\s*)\(at ([-\d.]+) ([-\d.]+) (\d+)\)(\s*)\(length ([\d.]+)\)',
                  fix, chunk)


def fmt(v):
    return ("%.4f" % v).rstrip("0").rstrip(".")


def fix_symbols(path):
    with open(path) as f:
        text = f.read()
    out, pos = [], 0
    # symbol by symbol, so each part gets its own pin-type table
    for m in re.finditer(r'\n  \(symbol "([^"]+)"', text):
        out.append(text[pos:m.start()])
        pos = m.start()
    out.append(text[pos:])
    fixed = []
    for chunk in out:
        lcsc = re.search(r'"LCSC Part"\s*"([^"]+)"', chunk)
        types = PIN_TYPES.get(lcsc.group(1) if lcsc else "", {})

        def pin(m, chunk=chunk):
            name = re.search(r'\(name "([^"]*)"', chunk[m.end():m.end() + 400])
            kind = types.get(name.group(1) if name else "", "passive")
            return m.group(0).replace("unspecified", kind)
        chunk = re.sub(r'\(pin unspecified', pin, chunk)
        fixed.append(lengthen_pins(chunk))
    text2 = "".join(fixed)
    if text2 != text:
        with open(path, "w") as f:
            f.write(text2)


def rect_pads(text):
    def fix(m):
        name, at, layers, pts = m.group(1), m.group(2), m.group(3), m.group(4)
        xy = [(float(a), float(b)) for a, b in re.findall(r'\(xy ([-\d.]+) ([-\d.]+)\)', pts)]
        x0, x1 = min(p[0] for p in xy), max(p[0] for p in xy)
        y0, y1 = min(p[1] for p in xy), max(p[1] for p in xy)
        on_edge = all(min(abs(x - x0), abs(x - x1), abs(y - y0), abs(y - y1)) < 0.01 for x, y in xy)
        corners = all(any(abs(x - cx) < 0.01 and abs(y - cy) < 0.01 for x, y in xy)
                      for cx in (x0, x1) for cy in (y0, y1))
        if not (on_edge and corners) or abs((x0 + x1) / 2) > 0.01 or abs((y0 + y1) / 2) > 0.01:
            return m.group(0)
        return "(pad %s smd rect %s (size %.3f %.3f) %s)" % (name, at, x1 - x0, y1 - y0, layers)
    return re.sub(r'\(pad (\S+) smd custom (\(at [^)]*\)) \(size [^)]*\) (\(layers [^)]*\))\s*'
                  r'\(primitives\s*\(gr_poly\s*\(pts ((?:\(xy [-\d.]+ [-\d.]+\))+)\s*\)\s*'
                  r'\(width [\d.]+\)\s*\)\s*\)\s*\)', fix, text)


SILK_PAD_GAP = 0.15


def pad_boxes(text):
    boxes = []
    for m in re.finditer(r'\(pad \S+ \w+ \w+ \(at ([-\d.]+) ([-\d.]+)(?: ([-\d.]+))?\) '
                         r'\(size ([\d.]+) ([\d.]+)\)', text):
        x, y, w, h = float(m.group(1)), float(m.group(2)), float(m.group(4)), float(m.group(5))
        if m.group(3) and round(float(m.group(3))) % 180 == 90:
            w, h = h, w
        boxes.append((x - w / 2, y - h / 2, x + w / 2, y + h / 2))
    return boxes


def clear_silk_of_pads(text):
    boxes = pad_boxes(text)

    def blocked(x, y, grow):
        return any(b[0] - grow <= x <= b[2] + grow and b[1] - grow <= y <= b[3] + grow for b in boxes)

    def line(m):
        x0, y0, x1, y1, w = map(float, m.group(1, 2, 3, 4, 5))
        grow = SILK_PAD_GAP + w / 2
        n = max(2, int(math.hypot(x1 - x0, y1 - y0) / 0.01))
        ok = [not blocked(x0 + (x1 - x0) * k / n, y0 + (y1 - y0) * k / n, grow) for k in range(n + 1)]
        out, k = [], 0
        while k <= n:                     # keep each clear run longer than 0.2 mm
            if not ok[k]:
                k += 1
                continue
            j = k
            while j + 1 <= n and ok[j + 1]:
                j += 1
            if (j - k) * math.hypot(x1 - x0, y1 - y0) / n > 0.2:
                out.append("(fp_line (start %.3f %.3f) (end %.3f %.3f) (layer F.SilkS) (width %s))" % (
                    x0 + (x1 - x0) * k / n, y0 + (y1 - y0) * k / n,
                    x0 + (x1 - x0) * j / n, y0 + (y1 - y0) * j / n, m.group(5)))
            k = j + 1
        return "\n\t".join(out)
    text = re.sub(r'\(fp_line \(start ([-\d.]+) ([-\d.]+)\) \(end ([-\d.]+) ([-\d.]+)\) '
                  r'\(layer F\.SilkS\) \(width ([\d.]+)\)\)', line, text)

    def circle(m):
        cx, cy, ex, ey, w = map(float, m.group(1, 2, 3, 4, 5))
        r = math.hypot(ex - cx, ey - cy) + w / 2
        return "" if blocked(cx, cy, r + SILK_PAD_GAP) else m.group(0)
    return re.sub(r'\(fp_circle \(center ([-\d.]+) ([-\d.]+)\) \(end ([-\d.]+) ([-\d.]+)\) '
                  r'\(layer F\.SilkS\) \(width ([\d.]+)\)\)', circle, text)


def fix_footprint(path):
    with open(path) as f:
        text = f.read()
    orig = text
    text = rect_pads(text)
    text = clear_silk_of_pads(text)

    def npth(m):
        size, drill = float(m.group(2)), float(m.group(4))
        if abs(size - drill) > 1e-3 or m.group(2) != m.group(3):
            return m.group(0)
        return ('(pad "" np_thru_hole circle %s(size %s %s) (drill %s) (layers *.Cu *.Mask))'
                % (m.group(1), m.group(2), m.group(3), m.group(4)))
    text = re.sub(r'\(pad "" thru_hole circle (\(at [^)]*\) )\(size ([\d.]+) ([\d.]+)\) \(drill ([\d.]+)\) '
                  r'\(layers \*\.Cu \*\.Mask\)\)', npth, text)
    text = re.sub(r'\(model "[^"]*/(jlc\.3dshapes/[^"]+)"', r'(model "${CUPC8_LIB}/\1"', text)
    if text != orig:
        with open(path, "w") as f:
            f.write(text)


MODEL_TOLERANCE = 0.5                    # mm


def model_offset(fp_path):
    """Distance (mm) between the WRL model's XY centre and the courtyard's."""
    text = open(fp_path).read()
    m = re.search(r'\(model "\$\{CUPC8_LIB\}/([^"]+)"\s*\(offset \(xyz ([-\d.]+) ([-\d.]+) [-\d.]+\)\)'
                  r'\s*\(scale [^)]*\)\)\s*\(rotate \(xyz [-\d.]+ [-\d.]+ ([-\d.]+)\)\)', text)
    if not m:
        return None
    wrl = open(os.path.join(ROOT, "hw", "lib", m.group(1))).read()
    xs, ys = [], []
    for block in re.findall(r'point\s*\[([^\]]*)\]', wrl):
        nums = [float(v) for v in re.findall(r'-?[\d.]+(?:e-?\d+)?', block)]
        xs += nums[0::3]
        ys += nums[1::3]
    # VRML units are 0.1 inch; model Y points up the board, KiCad's Y down
    cx, cy = (min(xs) + max(xs)) / 2 * 2.54, -(min(ys) + max(ys)) / 2 * 2.54
    a = math.radians(float(m.group(4)))
    cx, cy = cx * math.cos(a) + cy * math.sin(a), -cx * math.sin(a) + cy * math.cos(a)
    cx, cy = cx + float(m.group(2)), cy - float(m.group(3))
    crt = [(float(a), float(b)) for a, b in
           re.findall(r'\(fp_line \(start ([-\d.]+) ([-\d.]+)\)[^\n]*F\.CrtYd', text)]
    crt += [(float(a), float(b)) for a, b in
            re.findall(r'\(end ([-\d.]+) ([-\d.]+)\) \(layer F\.CrtYd\)', text)]
    kx = (min(p[0] for p in crt) + max(p[0] for p in crt)) / 2
    ky = (min(p[1] for p in crt) + max(p[1] for p in crt)) / 2
    return math.hypot(cx - kx, cy - ky)


def check(lcsc):
    lib = kg.parse(open(LIB + ".kicad_sym").read())
    for sym in kg.find(lib, "symbol"):
        props = {str(p[1]): str(p[2]) for p in kg.find(sym, "property")}
        if props.get("LCSC Part") != lcsc and lcsc not in props.values():
            continue
        fp_name = props["Footprint"].split(":")[1]
        fp = kg.parse(open(os.path.join(LIB + ".pretty", fp_name + ".kicad_mod")).read())
        pads = {str(p[1]) for p in kg.find(fp, "pad") if str(p[1])}
        pins = set(kg.symbol_pins(["symbol", kg.Q("jlc:" + str(sym[1]))] + sym[2:]))
        if pins - pads or pads - pins:
            raise SystemExit("%s: pins without pads %s, pads without pins %s"
                             % (lcsc, sorted(pins - pads), sorted(pads - pins)))
        off = model_offset(os.path.join(LIB + ".pretty", fp_name + ".kicad_mod"))
        if off is None or off > MODEL_TOLERANCE:
            raise SystemExit("%s: the 3D model is %s from the footprint's courtyard centre; fix the model "
                             "or use KiCad's footprint for this part" %
                             (lcsc, "missing" if off is None else "%.2f mm" % off))
        return str(sym[1]), fp_name, len(pins)
    raise SystemExit("%s: not found in %s.kicad_sym" % (lcsc, LIB))


def main():
    for lcsc in sys.argv[1:]:
        r = subprocess.run(["easyeda2kicad", "--full", "--overwrite", "--lcsc_id", lcsc, "--output", LIB],
                           capture_output=True, text=True)
        if r.returncode != 0:
            raise SystemExit("%s: easyeda2kicad failed\n%s%s" % (lcsc, r.stdout, r.stderr))
    fix_symbols(LIB + ".kicad_sym")
    for f in os.listdir(LIB + ".pretty"):
        fix_footprint(os.path.join(LIB + ".pretty", f))
    for lcsc in sys.argv[1:]:
        sym, fp, n = check(lcsc)
        print("%s: jlc:%s, footprint jlc:%s, %d pins match their pads" % (lcsc, sym, fp, n))


if __name__ == "__main__":
    main()
