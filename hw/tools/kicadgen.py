"""Generate KiCad schematics and boards from Python descriptions.

KiCad has no scripting API for schematics, so .kicad_sch files are written
as S-expressions. Symbols come from the KiCad libraries and are flattened
(derived symbols merged with their parent), which is how KiCad itself embeds
them. Every connection is a short wire stub from the pin plus a net label,
so a schematic is a set of parts with named nets on their pins.

Boards are built with the pcbnew API from the netlist that kicad-cli exports
from the schematic, so the board can only contain what the schematic says.
"""

import math
import os
import re
import subprocess
import uuid as uuidlib

KICAD_SYMBOLS = os.environ.get("KICAD_SYMBOL_DIR", "/usr/share/kicad/symbols")
KICAD_FOOTPRINTS = os.environ.get("KICAD_FOOTPRINT_DIR", "/usr/share/kicad/footprints")
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
HW_LIB = os.path.join(ROOT, "hw", "lib")
PROJECT_FOOTPRINTS = {"cupc8": os.path.join(HW_LIB, "cupc8.pretty"), "jlc": os.path.join(HW_LIB, "jlc.pretty")}
PROJECT_SYMBOLS = {"jlc": os.path.join(HW_LIB, "jlc.kicad_sym"),       # imported by hw/tools/jlcimport.py
                   "cupc8": os.path.join(HW_LIB, "cupc8.kicad_sym")}   # hw/tools/edgesym.py

# 3D models for stock footprints whose model KiCad does not ship, placed from
# the maker's drawing: footprint -> (model under hw/lib/models, offset mm
# (x, y up, z), rotation deg (x, y, z)). check_models() verifies the fit.
MODEL_OVERRIDES = {
    # EasyEDA's model of C165948 (8.94 x 3.25 mm, as the HRO drawing). Its
    # opening is at model y = +2.85; KiCad's footprint has it at y = +3.7
    # facing +y, hence the half turn and the 0.85 mm shift.
    "Connector_USB:USB_C_Receptacle_HRO_TYPE-C-31-M-12":
        ("HRO_TYPE-C-31-M-12.wrl", (0, -0.85, 0), (0, 0, 180)),
}


def symbol_path(lib):
    return PROJECT_SYMBOLS.get(lib) or os.path.join(KICAD_SYMBOLS, lib + ".kicad_sym")


def footprint_dir(lib):
    return PROJECT_FOOTPRINTS.get(lib) or os.path.join(KICAD_FOOTPRINTS, lib + ".pretty")
GRID = 2.54
SCH_VERSION = "20231120"                 # KiCad 8 format; KiCad 10 reads it


# ----------------------------------------------------------- S-expressions

class Q(str):
    """A string that is written quoted."""


_TOKEN = re.compile(r'\s*(?:(\()|(\))|"((?:[^"\\]|\\.)*)"|([^\s()"]+))', re.S)


def parse(text):
    stack, cur = [], []
    pos = 0
    while True:
        m = _TOKEN.match(text, pos)
        if not m or m.end() == pos:
            break
        pos = m.end()
        if m.group(1):
            stack.append(cur)
            cur = []
        elif m.group(2):
            done, cur = cur, stack.pop()
            cur.append(done)
        elif m.group(3) is not None:
            cur.append(Q(re.sub(r'\\(.)', r'\1', m.group(3))))
        else:
            cur.append(m.group(4))
    return cur[0]


def dump(x, indent=0):
    if isinstance(x, list):
        if not any(isinstance(e, list) for e in x):
            return "(" + " ".join(dump(e) for e in x) + ")"
        pad = "\t" * (indent + 1)
        head = [dump(e) for e in x if not isinstance(e, list)]
        out = "(" + " ".join(head)
        for e in x:
            if isinstance(e, list):
                out += "\n" + pad + dump(e, indent + 1)
        return out + "\n" + "\t" * indent + ")"
    if isinstance(x, Q):
        return '"' + x.replace("\\", "\\\\").replace('"', '\\"') + '"'
    if isinstance(x, float):
        return ("%.4f" % x).rstrip("0").rstrip(".")
    return str(x)


def find(node, key):
    return [e for e in node if isinstance(e, list) and e and e[0] == key]


def find1(node, key):
    r = find(node, key)
    return r[0] if r else None


# UUIDs are derived from a counter, not random: KiCad orders its exports (the
# Specctra DSN among them) by UUID, and a random order gave Freerouting a
# different problem, and a different route, on every run
_UID = uuidlib.UUID("6b1c5a62-1d8e-4c3e-9f0a-c5e8a0d2b7f1")
_uid_n = [0]


def uid():
    _uid_n[0] += 1
    return Q(str(uuidlib.uuid5(_UID, "sch/%d" % _uid_n[0])))


def stable_uuids(board, salt=0):
    """Give every board item a UUID derived from what it is (footprints by
    reference, their pads and graphics by index), replacing the random ones
    pcbnew assigns, so that exports ordered by UUID are the same every run."""
    import pcbnew

    def kiid(key):
        return pcbnew.KIID(str(uuidlib.uuid5(_UID, "%d/%s" % (salt, key) if salt else key)))
    fps = sorted(board.GetFootprints(), key=lambda f: f.GetReference())
    for fp in fps:
        ref = fp.GetReference()
        fp.SetUuidDirect(kiid("fp/" + ref))
        pads = fp.Pads()
        for i in range(len(pads)):
            pads[i].SetUuidDirect(kiid("pad/%s/%d" % (ref, i)))
        gi = fp.GraphicalItems()          # indexed: iterating it breaks on Python 3.14
        for i in range(len(gi)):
            gi[i].SetUuidDirect(kiid("gfx/%s/%d" % (ref, i)))
    for name, items in (("drw", board.Drawings()), ("trk", board.Tracks()), ("zone", board.Zones())):
        for i in range(len(items)):
            items[i].SetUuidDirect(kiid("%s/%d" % (name, i)))


# ----------------------------------------------------------------- symbols

_libs = {}


def _library(name):
    if name not in _libs:
        with open(symbol_path(name)) as f:
            lib = parse(f.read())
        _libs[name] = {s[1]: s for s in find(lib, "symbol")}
    return _libs[name]


def load_symbol(lib_id):
    """The symbol, flattened, named `lib_id` as a schematic embeds it."""
    lib, name = lib_id.split(":")
    syms = _library(lib)
    sym = syms[name]
    parent = find1(sym, "extends")
    if parent:
        base = load_symbol(lib + ":" + parent[1])
        own = {p[1]: p for p in find(sym, "property")}
        flat = [e for e in base if not (isinstance(e, list) and e[0] == "property")]
        props = [own.get(p[1], p) for p in find(base, "property")]
        props += [p for k, p in own.items() if k not in {q[1] for q in props}]
        flat = flat[:2] + props + flat[2:]
        # sub-symbols are named after the symbol
        base_name = str(base[1]).split(":")[-1]
        for e in flat:
            if isinstance(e, list) and e[0] == "symbol":
                e[1] = Q(name + str(e[1])[len(base_name):])
        sym = flat
    sym = [e for e in sym if not (isinstance(e, list) and e[0] == "extends")]
    sym = list(sym)
    sym[1] = Q(lib_id)
    return sym


# --------------------------------------------------------------- schematic
#
# Layout rules, enforced by Schematic.check() on every write:
#   - no text touches other text, a symbol body, a pin or a wire
#   - no two symbol bodies overlap, and no wire crosses another part's body
#   - everything is inside the page frame and clear of the title block
# Reference and Value are placed by Schematic.write in the first free spot
# beside the symbol, so the checker is the only judge of "looks right".

TEXT = 1.27                              # field and label text size
MARGIN = 0.25                            # clearance kept around text
PAGES = {"A4": (297, 210), "A3": (420, 297), "A2": (594, 420)}
FRAME = 10                               # page border
TITLE_BLOCK = (112, 36)                  # bottom-right, width x height


_extents = {}


def text_extent(s, size=TEXT):
    """(width, height) in mm of `s` in KiCad's stroke font, measured by KiCad."""
    if (s, size) not in _extents:
        import pcbnew
        t = pcbnew.PCB_TEXT(pcbnew.BOARD())
        t.SetText(s)
        t.SetTextSize(pcbnew.VECTOR2I(pcbnew.FromMM(size), pcbnew.FromMM(size)))
        t.SetTextThickness(pcbnew.FromMM(size * 0.12))
        bb = t.GetBoundingBox()
        _extents[s, size] = (pcbnew.ToMM(bb.GetWidth()), pcbnew.ToMM(bb.GetHeight()))
    return _extents[s, size]


def text_box(x, y, s, angle=0, hj="center", vj="center", size=TEXT):
    """Axis-aligned box of a text item, angle 0 (horizontal) or 90 (reading up)."""
    w, h = text_extent(s, size)
    a0 = {"left": 0, "right": -w, "center": -w / 2}[hj]
    b0 = {"bottom": -h, "top": 0, "center": -h / 2}[vj]
    if angle % 180 == 0:
        return (x + a0, y + b0, x + a0 + w, y + b0 + h)
    # rotated 90: the text runs up the page, its bottom faces +x
    return (x + b0, y - a0 - w, x + b0 + h, y - a0)


def overlap(a, b, margin=0.0):
    return a[0] < b[2] + margin and b[0] < a[2] + margin and a[1] < b[3] + margin and b[1] < a[3] + margin


def seg_box(x0, y0, x1, y1, width=0.15):
    return (min(x0, x1) - width / 2, min(y0, y1) - width / 2, max(x0, x1) + width / 2, max(y0, y1) + width / 2)


def union(boxes):
    boxes = list(boxes)
    return (min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes))


def _units(sym, unit):
    base = str(sym[1]).split(":")[-1]
    for sub in find(sym, "symbol"):
        m = re.match(re.escape(base) + r"_(\d+)_(\d+)$", str(sub[1]))
        if m and int(m.group(1)) in (0, unit) and int(m.group(2)) in (0, 1):
            yield sub


def symbol_graphics(sym, unit=1):
    """Points of the body outline (symbol coordinates, Y up)."""
    pts = []
    for sub in _units(sym, unit):
        for e in sub:
            if not isinstance(e, list):
                continue
            if e[0] == "rectangle":
                for k in ("start", "end"):
                    p = find1(e, k)
                    pts.append((float(p[1]), float(p[2])))
            elif e[0] in ("polyline", "bezier"):
                pts += [(float(p[1]), float(p[2])) for p in find(find1(e, "pts"), "xy")]
            elif e[0] == "arc":
                pts += [(float(find1(e, k)[1]), float(find1(e, k)[2])) for k in ("start", "mid", "end")]
            elif e[0] == "circle":
                c, r = find1(e, "center"), float(find1(e, "radius")[1])
                pts += [(float(c[1]) - r, float(c[2]) - r), (float(c[1]) + r, float(c[2]) + r)]
    return pts


def symbol_pins(sym, unit=1):
    """{number: (x, y, angle, name, type, length, hidden)} for one unit (style 1)."""
    pins = {}
    for sub in _units(sym, unit):
        for p in find(sub, "pin"):
            at = find1(p, "at")
            ln = find1(p, "length")
            pins[str(find1(p, "number")[1])] = (
                float(at[1]), float(at[2]), float(at[3]) if len(at) > 3 else 0.0,
                str(find1(p, "name")[1]), str(p[1]), float(ln[1]) if ln else 2.54,
                "hide" in p or (find1(p, "hide") or [None, "no"])[1] == "yes")
    return pins


def _hidden(prop):
    if find1(prop, "hide"):
        return find1(prop, "hide")[1] == "yes"
    eff = find1(prop, "effects") or []
    return any(e == "hide" or (isinstance(e, list) and e[0] == "hide" and e[-1] != "no") for e in eff)


def not_in_bom(fpid):
    """True when the footprint marks itself exclude_from_bom (card fingers,
    test pads): the symbol must agree, or DRC's schematic parity fails."""
    if not fpid:
        return False
    lib, name = fpid.split(":")
    with open(os.path.join(footprint_dir(lib), name + ".kicad_mod")) as f:
        attr = re.search(r"\(attr [^)]*\)", f.read())
    return bool(attr and "exclude_from_bom" in attr.group(0))


class Part:
    def __init__(self, sch, lib_id, ref, value, footprint, at, rot, fields, unit):
        self.sch, self.lib_id, self.ref, self.value = sch, lib_id, ref, value
        self.footprint, self.at, self.rot, self.fields, self.unit = footprint, at, rot, fields, unit
        self.uuid = uid()
        self.sym = sch._symbol(lib_id)
        self.pins = symbol_pins(self.sym, unit)
        self.used = {}                   # pin number -> net (None for no-connect)
        props = {str(p[1]): p for p in find(self.sym, "property")}
        self.show = {k: k in props and not _hidden(props[k]) for k in ("Reference", "Value")}
        self.field_at = {}               # field -> (x, y), set by Schematic.write

    def pin(self, key):
        """A pin by number, or by name if the name is unique."""
        key = str(key)
        if key in self.pins:
            return key
        hits = [n for n, p in self.pins.items() if p[3] == key]
        if len(hits) != 1:
            raise KeyError("%s: no single pin %r (have %s)" % (self.ref, key, sorted(self.pins)))
        return hits[0]

    def xf(self, x, y):
        """Symbol coordinates (Y up) to the sheet (Y down), with the part's rotation."""
        r = self.rot % 360
        rx, ry = {0: (x, -y), 90: (-y, -x), 180: (-x, y), 270: (y, x)}[r]
        return self.at[0] + rx, self.at[1] + ry

    def pin_xy(self, num):
        """Sheet position of a pin's connection point, and its outward direction."""
        x, y, ang = self.pins[num][:3]
        # a pin points from its connection point into the body at `ang`
        out = (ang + 180 + self.rot) % 360
        dx, dy = {0: (1, 0), 90: (0, -1), 180: (-1, 0), 270: (0, 1)}[round(out) % 360]
        return self.xf(x, y), (dx, dy)

    def body_box(self):
        pts = [self.xf(x, y) for x, y in symbol_graphics(self.sym, self.unit)]
        return union((x, y, x, y) for x, y in pts) if pts else None

    def pin_boxes(self):
        out = []
        for n, (x, y, ang, _, _, ln, hidden) in self.pins.items():
            if hidden:
                continue
            a = math.radians(ang)
            ex, ey = x + ln * math.cos(a), y + ln * math.sin(a)
            (x0, y0), (x1, y1) = self.xf(x, y), self.xf(ex, ey)
            out.append(seg_box(x0, y0, x1, y1))
        return out

    def number_boxes(self):
        """Pin-number texts: centred along the pin, just above (or left of) it."""
        if find1(self.sym, "pin_numbers") and "hide" in str(find1(self.sym, "pin_numbers")):
            return []
        out = []
        for n, (x, y, ang, _, _, ln, hidden) in self.pins.items():
            if hidden:
                continue
            a = math.radians(ang)
            (x0, y0), (x1, y1) = self.xf(x, y), self.xf(x + ln * math.cos(a), y + ln * math.sin(a))
            mx, my = (x0 + x1) / 2, (y0 + y1) / 2
            if abs(y0 - y1) < 1e-6:          # horizontal pin: number above it
                out.append((text_box(mx, my - 0.25, n, 0, "center", "bottom"), n))
            else:                            # vertical: reads up, left of the pin
                out.append((text_box(mx - 0.25, my, n, 90, "center", "bottom"), n))
        return out

    def extent(self):
        boxes = self.pin_boxes() + ([self.body_box()] if self.body_box() else [])
        return union(boxes)

    def field_boxes(self):
        """Boxes of the visible Reference/Value texts, once placed."""
        out = []
        for k, text in (("Reference", self.ref), ("Value", self.value)):
            if self.show[k] and k in self.field_at:
                out.append(text_box(*self.field_at[k], text))
        return out


class Schematic:
    def __init__(self, project, title="", paper="A3"):
        self.project, self.title, self.paper = project, title, paper
        self.uuid = uid()
        self.parts = []
        self.syms = {}
        self.items = []
        self.wires = []                  # (x0, y0, x1, y1, part, net)
        self.labels = []                 # (box, text, part)
        self.ncs = []                    # (box, part): no-connect crosses

    def _symbol(self, lib_id):
        if lib_id not in self.syms:
            self.syms[lib_id] = load_symbol(lib_id)
        return self.syms[lib_id]

    def add(self, lib_id, ref, value, footprint="", at=(0, 0), rot=0, fields=None, unit=1):
        p = Part(self, lib_id, ref, value, footprint, at, rot, fields or {}, unit)
        self.parts.append(p)
        return p

    def _stacked(self, part, num):
        """Pins of `part` at the same point as `num` (stacked pins, one connection)."""
        here = part.pin_xy(num)[0]
        return [n for n in part.pins if part.pin_xy(n)[0] == here]

    def connect(self, part, pin, net, stub=2 * GRID):
        num = part.pin(pin)
        if num in part.used:
            if part.used[num] != net:
                raise ValueError("%s pin %s is on %s, not %s" % (part.ref, num, part.used[num], net))
            return                       # a stacked pin already drawn
        for n in self._stacked(part, num):
            part.used[n] = net
        (x, y), (dx, dy) = part.pin_xy(num)
        ex, ey = round(x + dx * stub, 4), round(y + dy * stub, 4)
        self.items.append(["wire", ["pts", ["xy", x, y], ["xy", ex, ey]],
                           ["stroke", ["width", 0], ["type", "default"]], ["uuid", uid()]])
        self.wires.append((x, y, ex, ey, part, net))
        angle = {(1, 0): 0, (0, -1): 90, (-1, 0): 180, (0, 1): 270}[(dx, dy)]
        justify = {0: "left", 90: "left", 180: "right", 270: "right"}[angle]
        self.items.append(["label", Q(net), ["at", ex, ey, angle % 180],
                           ["fields_autoplaced", "yes"],
                           ["effects", ["font", ["size", TEXT, TEXT]], ["justify", justify, "bottom"]],
                           ["uuid", uid()]])
        # the text sits just off the wire, running away from the pin
        box = text_box(ex, ey, net, angle % 180, justify, "bottom")
        off = 0.3                        # KiCad lifts label text off the wire
        box = (box[0], box[1] - off, box[2], box[3] - off) if angle % 180 == 0 else \
              (box[0] - off, box[1], box[2] - off, box[3])
        self.labels.append((box, net, part))

    def nc(self, part, pin, stub=0):
        """A no-connect cross on the pin, or `stub` mm out on a wire from it:
        short library pins (KiCad's FPGA symbols) leave no room for the cross
        beside the pin number."""
        num = part.pin(pin)
        for n in self._stacked(part, num):
            part.used[n] = None
        (x, y), (dx, dy) = part.pin_xy(num)
        if stub:
            ex, ey = round(x + dx * stub, 4), round(y + dy * stub, 4)
            self.items.append(["wire", ["pts", ["xy", x, y], ["xy", ex, ey]],
                               ["stroke", ["width", 0], ["type", "default"]], ["uuid", uid()]])
            self.wires.append((x, y, ex, ey, part, None))
            x, y = ex, ey
        self.items.append(["no_connect", ["at", x, y], ["uuid", uid()]])
        self.ncs.append(((x - 0.65, y - 0.65, x + 0.65, y + 0.65), part))

    def unconnected(self):
        return [(p.ref, n) for p in self.parts for n in p.pins if n not in p.used]

    # ---- layout

    def _page(self):
        w, h = PAGES[self.paper]
        drawable = (FRAME, FRAME, w - FRAME, h - FRAME)
        title = (w - FRAME - TITLE_BLOCK[0], h - FRAME - TITLE_BLOCK[1], w - FRAME, h - FRAME)
        return drawable, title

    def _obstacles(self, skip_fields_of=None):
        """(box, kind, part) for everything drawn."""
        obs = []
        for p in self.parts:
            b = p.body_box()
            if b:
                obs.append((b, "body", p))
            obs += [(pb, "pin", p) for pb in p.pin_boxes()]
            if p is not skip_fields_of:
                obs += [(fb, "text", p) for fb in p.field_boxes()]
            obs += [(nb, "number", p) for nb, _ in p.number_boxes()]
        obs += [(seg_box(*w[:4]), "wire", w[4]) for w in self.wires]
        obs += [(box, "text", part) for box, _, part in self.labels]
        obs += [(box, "nc", part) for box, part in self.ncs]
        return obs

    def _place_fields(self, p):
        texts = [(k, t) for k, t in (("Reference", p.ref), ("Value", p.value)) if p.show[k]]
        if not texts:
            return
        pitch = text_extent("X")[1] + 0.2
        w = max(text_extent(t)[0] for _, t in texts)
        h = pitch * len(texts)
        x0, y0, x1, y1 = p.extent()
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        gap = GRID / 2
        # sides with no pins first: text there never crowds wiring
        pin_sides = {p.pin_xy(n)[1] for n, pin in p.pins.items() if not pin[6]}
        sides = [(1, 0), (0, -1), (-1, 0), (0, 1)]          # right, above, left, below
        sides = [d for d in sides if d not in pin_sides] + [d for d in sides if d in pin_sides]
        spots = []
        for dx, dy in sides:
            for shift in (0, GRID, -GRID, 2 * GRID, -2 * GRID, 3 * GRID, -3 * GRID):
                if dx:
                    spots.append((x1 + gap + w / 2 if dx > 0 else x0 - gap - w / 2, cy + shift))
                else:
                    spots.append((cx + shift, y0 - gap - h / 2 if dy < 0 else y1 + gap + h / 2))
        drawable, title = self._page()
        obs = [b for b, _, q in self._obstacles(skip_fields_of=p)]
        for sx, sy in spots:
            at = {k: (sx, sy + (i - (len(texts) - 1) / 2) * pitch) for i, (k, _) in enumerate(texts)}
            boxes = [text_box(*at[k], t) for k, t in texts]
            if all(not overlap(b, o, MARGIN) for b in boxes for o in obs) and \
               all(drawable[0] <= b[0] and b[2] <= drawable[2] and drawable[1] <= b[1] and b[3] <= drawable[3]
                   and not overlap(b, title) for b in boxes):
                p.field_at = {k: (round(v[0], 3), round(v[1], 3)) for k, v in at.items()}
                return
        raise ValueError("%s: no free spot for its reference and value; move it" % p.ref)

    def check(self):
        """Every layout rule; returns a list of problems (empty = clean)."""
        bad = []
        obs = self._obstacles()
        drawable, title = self._page()
        texts = [(b, p) for b, k, p in obs if k == "text"]
        for i, (a, pa) in enumerate(texts):
            for b, pb in texts[i + 1:]:
                if overlap(a, b):
                    bad.append("text overlaps text near (%.1f, %.1f) [%s/%s]" % (a[0], a[1], pa.ref, pb.ref))
            for b, kind, q in obs:
                if kind in ("body", "pin", "wire", "nc", "number") and overlap(a, b, -0.02):
                    bad.append("text of %s overlaps a %s of %s near (%.1f, %.1f)" % (pa.ref, kind, q.ref, a[0], a[1]))
        # a pin number must fit along its pin (not run into the body) and
        # clear everything else drawn
        for p in self.parts:
            body = p.body_box()
            for nb, n in p.number_boxes():
                if body and overlap(nb, body, -0.02):
                    bad.append("pin number %s of %s runs into its body (pin too short)" % (n, p.ref))
                for b, kind, q in obs:
                    if kind in ("text", "nc", "wire") and overlap(nb, b, -0.02) and not (kind == "wire" and q is p):
                        bad.append("pin number %s of %s overlaps a %s of %s" % (n, p.ref, kind, q.ref))
        bodies = [(b, p) for b, k, p in obs if k == "body"]
        for i, (a, pa) in enumerate(bodies):
            for b, pb in bodies[i + 1:]:
                if overlap(a, b):
                    bad.append("bodies of %s and %s overlap" % (pa.ref, pb.ref))
        # KiCad joins wires that touch, so two nets' stubs must never meet
        for i, w in enumerate(self.wires):
            for v in self.wires[i + 1:]:
                if w[5] != v[5] and overlap(seg_box(*w[:4], width=0), seg_box(*v[:4], width=0), 0.01):
                    bad.append("wires of %s (%s) and %s (%s) touch: a short" % (w[4].ref, w[5], v[4].ref, v[5]))
        for w in self.wires:
            for b, pb in bodies:
                if pb is not w[4] and overlap(seg_box(*w[:4]), b):
                    bad.append("wire from %s crosses the body of %s" % (w[4].ref, pb.ref))
        for b, kind, p in obs:
            if not (drawable[0] <= b[0] and b[2] <= drawable[2] and drawable[1] <= b[1] and b[3] <= drawable[3]):
                bad.append("%s of %s is outside the page frame" % (kind, p.ref))
            elif overlap(b, title):
                bad.append("%s of %s is on the title block" % (kind, p.ref))
        return sorted(set(bad))

    def _instance(self, p):
        props = []
        fields = [("Reference", p.ref), ("Value", p.value), ("Footprint", p.footprint)]
        fields += list(p.fields.items())
        # KiCad draws a field's angle relative to the symbol: 90 on a quarter-
        # turned part is horizontal on the sheet
        fa = 90 if p.rot % 180 else 0
        for k, v in fields:
            x, y = p.field_at.get(k, p.at)
            shown = k in p.field_at and p.show.get(k, False)
            props.append(["property", Q(k), Q(v), ["at", x, y, fa],
                          ["effects", ["font", ["size", TEXT, TEXT]]] + ([] if shown else [["hide", "yes"]])])
        return (["symbol", ["lib_id", Q(p.lib_id)], ["at", p.at[0], p.at[1], p.rot], ["unit", p.unit],
                 ["exclude_from_sim", "no"], ["in_bom", "no" if not_in_bom(p.footprint) else "yes"],
                 ["on_board", "yes"], ["dnp", "no"],
                 ["uuid", p.uuid]] + props +
                [["pin", Q(n), ["uuid", uid()]] for n in p.pins] +
                [["instances", ["project", Q(self.project),
                                ["path", Q("/" + self.uuid), ["reference", Q(p.ref)], ["unit", p.unit]]]]])

    def write_lib_tables(self, outdir, footprints=()):
        """Project library tables for every library this design uses, so the
        project opens the same way with or without global KiCad setup."""
        syms = sorted({p.lib_id.split(":")[0] for p in self.parts})
        fps = sorted({p.footprint.split(":")[0] for p in self.parts if p.footprint} | set(footprints))
        with open(os.path.join(outdir, "sym-lib-table"), "w") as f:
            f.write(dump(["sym_lib_table", ["version", 7]] +
                         [["lib", ["name", Q(n)], ["type", Q("KiCad")],
                           ["uri", Q(symbol_path(n))],
                           ["options", Q("")], ["descr", Q("")]] for n in syms]) + "\n")
        with open(os.path.join(outdir, "fp-lib-table"), "w") as f:
            f.write(dump(["fp_lib_table", ["version", 7]] +
                         [["lib", ["name", Q(n)], ["type", Q("KiCad")],
                           ["uri", Q(footprint_dir(n))],
                           ["options", Q("")], ["descr", Q("")]] for n in fps]) + "\n")

    def write(self, path, footprint_libs=()):
        """Place the fields, check the layout, and write the sheet.
        footprint_libs: extra libraries the board uses (logos and such)."""
        for p in self.parts:
            self._place_fields(p)
        bad = self.check()
        if bad:
            raise ValueError("schematic layout:\n  " + "\n  ".join(bad))
        self.write_lib_tables(os.path.dirname(os.path.abspath(path)), footprint_libs)
        doc = (["kicad_sch", ["version", SCH_VERSION], ["generator", Q("cupc8-kicadgen")],
                ["uuid", self.uuid], ["paper", Q(self.paper)],
                ["title_block", ["title", Q(self.title)]],
                ["lib_symbols"] + list(self.syms.values())] +
               self.items + [self._instance(p) for p in self.parts] +
               [["sheet_instances", ["path", Q("/"), ["page", Q("1")]]]])
        with open(path, "w") as f:
            f.write(dump(doc) + "\n")


# ----------------------------------------------------------------- netlist

def export_netlist(sch_path, out_path):
    run(["kicad-cli", "sch", "export", "netlist", "--format", "kicadsexpr", "-o", out_path, sch_path])
    with open(out_path) as f:
        net = parse(f.read())
    comps = {}
    for c in find(find1(net, "components"), "comp"):
        ts = find1(c, "tstamps") or find1(c, "tstamp")
        comps[str(find1(c, "ref")[1])] = {
            "value": str(find1(c, "value")[1]),
            "footprint": str(find1(c, "footprint")[1]) if find1(c, "footprint") else "",
            "uuid": str(ts[1]),
            "fields": {str(f[1][1]): str(f[2]) for f in find(find1(c, "fields") or [], "field")
                       if len(f) > 2},
        }
    nets = {}
    for n in find(find1(net, "nets"), "net"):
        name = str(find1(n, "name")[1])
        nets[name] = [(str(find1(nd, "ref")[1]), str(find1(nd, "pin")[1])) for nd in find(n, "node")]
    return comps, nets


# ----------------------------------------------------------------- project

# JLCPCB standard capabilities are 0.127 mm track/space (2-layer), 0.3 mm via
# drill, 0.3 mm copper to edge; these rules keep a margin above them.
JLC_RULES = {
    "min_track_width": 0.15,
    "min_clearance": 0.15,
    "min_via_diameter": 0.6,
    "min_through_hole_diameter": 0.3,
    "min_via_annular_width": 0.13,
    "min_copper_edge_clearance": 0.3,
    "min_hole_clearance": 0.25,
    "min_hole_to_hole": 0.5,
    "min_connection": 0.15,
    "min_resolved_spokes": 2,
    "min_silk_clearance": 0.0,
    "min_text_height": 0.8,
    "min_text_thickness": 0.15,
    "max_error": 0.005,
}

NET_CLASSES = [
    # name, track, clearance, via diameter, via drill
    ("Default", 0.2, 0.2, 0.6, 0.3),        # 0.2: two 0.6/0.3 vias then keep holes 0.5 apart (JLC)
    ("Power", 0.5, 0.2, 0.8, 0.4),
]


def write_project(path, power_nets=(), rules=None):
    """A .kicad_pro with the design rules and net classes kicad-cli DRC uses."""
    import json
    classes = [{"name": n, "track_width": w, "clearance": c, "via_diameter": vd, "via_drill": vdr,
                "diff_pair_width": 0.2, "diff_pair_gap": 0.2, "diff_pair_via_gap": 0.25,
                "microvia_diameter": 0.3, "microvia_drill": 0.1, "bus_width": 12, "wire_width": 6,
                "line_style": 0, "pcb_color": "rgba(0, 0, 0, 0.000)",
                "schematic_color": "rgba(0, 0, 0, 0.000)", "priority": 2147483647 if n == "Default" else 0}
               for n, w, c, vd, vdr in NET_CLASSES]
    pro = {
        "board": {"design_settings": {
            "rules": dict(JLC_RULES, **(rules or {})),
            # boards are regenerated from the libraries on every run, so they
            # cannot drift from them; the only differences are the deliberate
            # edits here (designators placed, silkscreen trimmed to the edge)
            "rule_severities": {"lib_footprint_mismatch": "ignore"},
        }},
        "net_settings": {"classes": classes, "meta": {"version": 4},
                         "netclass_patterns": [{"netclass": "Power", "pattern": n} for n in power_nets]},
        "meta": {"filename": os.path.basename(path), "version": 3},
    }
    with open(path, "w") as f:
        json.dump(pro, f, indent=2)


# ------------------------------------------------------------------- board

def run(cmd, **kw):
    r = subprocess.run(cmd, capture_output=True, text=True, **kw)
    if r.returncode != 0:
        raise RuntimeError("%s failed (%d):\n%s%s" % (cmd[0], r.returncode, r.stdout, r.stderr))
    return r


def build_board(comps, nets, placement, outline, layers=2, zones=("GND",), graphics=(), edge=None,
                zone_outline=None, labels=None):
    """A pcbnew BOARD with every footprint placed and every pad on its net.

    placement: {ref: (x_mm, y_mm, rot_deg[, "B" for the bottom side])}
    outline:   (x0, y0, x1, y1) in mm
    graphics:  board-only footprints such as logos: ("lib:name", x, y, rot)
    zones:     nets poured on F.Cu and B.Cu, or (net, (layer names)) for
               chosen layers; an inner layer with a zone becomes a plane
    edge:      Edge.Cuts as an open polyline [(x, y), ...] in place of the
               outline rectangle - for a card whose edge-connector footprint
               draws its own tab. Silk, designators and zones still keep
               inside `outline`, the card body.
    zone_outline: the copper pours' polygon, if not `outline` less 0.5 mm
    labels:    {ref: word}: the word (what an LED shows) printed where the part's
               designator would go, in its place
    """
    import pcbnew
    mm = pcbnew.FromMM
    board = pcbnew.BOARD()
    board.SetCopperLayerCount(layers)

    netinfo = {}
    for name in nets:
        ni = pcbnew.NETINFO_ITEM(board, name)
        board.Add(ni)
        netinfo[name] = ni
    pad_net = {(r, p): n for n, nodes in nets.items() for r, p in nodes}

    for ref, c in comps.items():
        lib, name = c["footprint"].split(":")
        fp = pcbnew.FootprintLoad(footprint_dir(lib), name)
        if fp is None:
            raise KeyError("%s: footprint %s not found" % (ref, c["footprint"]))
        override = MODEL_OVERRIDES.get(c["footprint"])
        if override:
            m = pcbnew.FP_3DMODEL()
            m.m_Filename = os.path.join(HW_LIB, "models", override[0])
            m.m_Offset = pcbnew.VECTOR3D(*override[1])
            m.m_Rotation = pcbnew.VECTOR3D(*override[2])
            fp.Models().clear()
            fp.Models().push_back(m)
        models = fp.Models()                 # index it: iterating yields copies
        for i in range(len(models)):         # imported parts: ${CUPC8_LIB}/jlc.3dshapes/...
            models[i].m_Filename = models[i].m_Filename.replace("${CUPC8_LIB}", HW_LIB)
        fp.SetReference(ref)
        fp.SetValue(c["value"])
        fp.SetFPID(pcbnew.LIB_ID(lib, name))
        fp.SetPath(pcbnew.KIID_PATH("/" + c["uuid"]))
        for k, v in c["fields"].items():
            if k not in ("Footprint", "Datasheet", "Description"):
                fp.SetField(k, v)
                fp.GetField(k).SetVisible(False)   # LCSC etc. are data, not silkscreen
        if ref not in placement:
            raise KeyError("%s has no placement" % ref)
        x, y, rot, *side = placement[ref]
        board.Add(fp)
        if side and side[0] == "B":
            fp.Flip(fp.GetPosition(), pcbnew.FLIP_DIRECTION_TOP_BOTTOM)
        fp.SetPosition(pcbnew.VECTOR2I(mm(x), mm(y)))
        fp.SetOrientationDegrees(rot)
        for pad in fp.Pads():
            n = pad_net.get((ref, pad.GetNumber()))
            if n:
                pad.SetNet(netinfo[n])

    for i, (fpid, x, y, rot) in enumerate(graphics):
        lib, name = fpid.split(":")
        fp = pcbnew.FootprintLoad(footprint_dir(lib), name)
        if fp is None:
            raise KeyError("footprint %s not found" % fpid)
        fp.SetReference("G%d" % (i + 1))
        fp.SetFPID(pcbnew.LIB_ID(lib, name))
        board.Add(fp)
        fp.SetPosition(pcbnew.VECTOR2I(mm(x), mm(y)))
        fp.SetOrientationDegrees(rot)

    x0, y0, x1, y1 = outline
    corners = edge or [(x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)]
    for a, b in zip(corners, corners[1:]):
        seg = pcbnew.PCB_SHAPE(board)
        seg.SetShape(pcbnew.SHAPE_T_SEGMENT)
        seg.SetStart(pcbnew.VECTOR2I(mm(a[0]), mm(a[1])))
        seg.SetEnd(pcbnew.VECTOR2I(mm(b[0]), mm(b[1])))
        seg.SetLayer(pcbnew.Edge_Cuts)
        seg.SetWidth(mm(0.1))
        board.Add(seg)

    clip_silk_to_board(board, outline)
    clip_silk_to_pads(board)
    place_designators(board, outline, labels or {})

    copper = [pcbnew.F_Cu, pcbnew.B_Cu]
    for zone in zones:
        # a zone is a net on both outer layers, or (net, ("In1.Cu", ...)):
        # inner layers named that way become planes (power layers), which
        # Freerouting reaches with vias and never routes signals on
        net, names = (zone, None) if isinstance(zone, str) else zone
        layers = [board.GetLayerID(n) for n in names] if names else copper
        for layer in layers:
            if layer not in copper:
                board.SetLayerType(layer, pcbnew.LT_POWER)
            z = pcbnew.ZONE(board)
            z.SetLayer(layer)
            z.SetNet(netinfo[net])
            z.SetLocalClearance(mm(0.3))
            z.SetMinThickness(mm(0.25))
            z.SetPadConnection(pcbnew.ZONE_CONNECTION_FULL)   # solid: fine for reflow, no starved spokes
            z.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_ALWAYS)   # no floating copper
            ol = z.Outline()
            ol.NewOutline()
            for px, py in zone_outline or ((x0 + .5, y0 + .5), (x1 - .5, y0 + .5), (x1 - .5, y1 - .5),
                                           (x0 + .5, y1 - .5)):
                ol.Append(mm(px), mm(py))
            board.Add(z)
    return board


def card_zone(body, tab, reach):
    """A card's pour outline: the body less 0.5 mm, plus the finger tab
    (x from tab[0] to tab[1]) down to y = `reach`, over the top ends of the
    fingers, so the GND fingers join the pour (clearance keeps it out from
    between them). `body` ends where the tab starts."""
    x0, y0, x1, y1 = body
    tx0, tx1 = tab
    return [(x0 + .5, y0 + .5), (x1 - .5, y0 + .5), (x1 - .5, y1 - .5), (tx1 - .5, y1 - .5),
            (tx1 - .5, reach), (tx0 + .5, reach), (tx0 + .5, y1 - .5), (x0 + .5, y1 - .5)]


def clip_silk_to_board(board, outline, gap=0.15):
    """Trim footprint silkscreen to the board: a connector that overhangs the
    edge (as its maker intends) has outline lines that cannot be printed.
    Segments are clipped `gap` inside the edge; any other silk shape that
    leaves the board is an error, so nothing is dropped silently."""
    import pcbnew
    mm, to = pcbnew.FromMM, pcbnew.ToMM
    x0, y0, x1, y1 = outline
    for fp in board.GetFootprints():
        gi = fp.GraphicalItems()          # indexed: iterating it breaks on Python 3.14
        for g in [gi[i].Cast() for i in range(len(gi))]:
            if g.GetLayer() not in (pcbnew.F_SilkS, pcbnew.B_SilkS):
                continue
            w = to(g.GetWidth()) / 2 + gap
            lo_x, lo_y, hi_x, hi_y = x0 + w, y0 + w, x1 - w, y1 - w
            if not (isinstance(g, pcbnew.PCB_SHAPE) and g.GetShape() == pcbnew.SHAPE_T_SEGMENT):
                b = g.GetBoundingBox()
                if to(b.GetLeft()) < lo_x or to(b.GetTop()) < lo_y or to(b.GetRight()) > hi_x or to(b.GetBottom()) > hi_y:
                    raise ValueError("%s: silkscreen shape leaves the board" % fp.GetReference())
                continue
            ax, ay, bx, by = to(g.GetStart().x), to(g.GetStart().y), to(g.GetEnd().x), to(g.GetEnd().y)
            # Liang-Barsky
            t0, t1, dx, dy = 0.0, 1.0, bx - ax, by - ay
            for p, q in ((-dx, ax - lo_x), (dx, hi_x - ax), (-dy, ay - lo_y), (dy, hi_y - ay)):
                if p == 0:
                    if q < 0:
                        t0, t1 = 1, 0
                elif p < 0:
                    t0 = max(t0, q / p)
                else:
                    t1 = min(t1, q / p)
            if t1 - t0 <= 1e-9 or math.hypot(dx, dy) * (t1 - t0) < 0.2:
                fp.Remove(g)
                continue
            g.SetStart(pcbnew.VECTOR2I(mm(ax + dx * t0), mm(ay + dy * t0)))
            g.SetEnd(pcbnew.VECTOR2I(mm(ax + dx * t1), mm(ay + dy * t1)))


def clip_silk_to_pads(board, gap=0.15):
    """Trim footprint silkscreen segments that come within `gap` of a pad on
    their side (edge to pad, the line's width counted): some library
    footprints stop their outline 0.15 mm from a pad at the line's centre,
    which leaves its edge 0.09 mm away (the HRO TYPE-C-31-M-12's shield
    pads). The part of a segment inside a pad's box grown by gap + half the
    width goes; what is left under 0.2 mm long goes too."""
    import pcbnew
    mm, to = pcbnew.FromMM, pcbnew.ToMM
    pads = []
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            bb = pad.GetBoundingBox()
            pads.append((to(bb.GetLeft()), to(bb.GetTop()), to(bb.GetRight()), to(bb.GetBottom()),
                         pad.IsOnLayer(pcbnew.F_Cu), pad.IsOnLayer(pcbnew.B_Cu)))
    for fp in board.GetFootprints():
        gi = fp.GraphicalItems()          # indexed: iterating it breaks on Python 3.14
        for g in [gi[i].Cast() for i in range(len(gi))]:
            if g.GetLayer() not in (pcbnew.F_SilkS, pcbnew.B_SilkS):
                continue
            if not (isinstance(g, pcbnew.PCB_SHAPE) and g.GetShape() == pcbnew.SHAPE_T_SEGMENT):
                continue
            front = g.GetLayer() == pcbnew.F_SilkS
            ax, ay, bx, by = to(g.GetStart().x), to(g.GetStart().y), to(g.GetEnd().x), to(g.GetEnd().y)
            dx, dy = bx - ax, by - ay
            w = to(g.GetWidth()) / 2 + gap + 0.01          # 10 um clear of check_silk's inclusive edge
            keep = [(0.0, 1.0)]
            for x0, y0, x1, y1, on_f, on_b in pads:
                if not (on_f if front else on_b):
                    continue
                # Liang-Barsky: the part of the segment inside the grown pad box
                t0, t1 = 0.0, 1.0
                for p, q in ((-dx, ax - (x0 - w)), (dx, (x1 + w) - ax), (-dy, ay - (y0 - w)), (dy, (y1 + w) - ay)):
                    if p == 0:
                        if q < 0:
                            t0, t1 = 1, 0
                    elif p < 0:
                        t0 = max(t0, q / p)
                    else:
                        t1 = min(t1, q / p)
                if t1 <= t0:
                    continue
                keep = [piece for a0, a1 in keep
                        for piece in ((a0, min(a1, t0)), (max(a0, t1), a1)) if piece[1] > piece[0]]
            if keep == [(0.0, 1.0)]:
                continue
            length = math.hypot(dx, dy)
            keep = [(a0, a1) for a0, a1 in keep if length * (a1 - a0) >= 0.2]
            for k, (a0, a1) in enumerate(keep):
                seg = g if k == 0 else g.Duplicate()
                seg.SetStart(pcbnew.VECTOR2I(mm(ax + dx * a0), mm(ay + dy * a0)))
                seg.SetEnd(pcbnew.VECTOR2I(mm(ax + dx * a1), mm(ay + dy * a1)))
                if k:
                    fp.Add(seg)
            if not keep:
                fp.Remove(g)


SILK_TEXT = (1.0, 0.15)                 # designator height and stroke (JLC minimum stroke)


def mark_revision(board, title, revision, at):
    """The board's name and revision, "<title> rev <revision>", on the top
    silkscreen with its bottom-right corner at `at` (mm; normally 1 mm in from
    the body's bottom-right corner), and in its title block (the Gerbers' X2
    file attributes carry it), so boards of different builds can be told
    apart (doc/milestone-1.md, Board revision)."""
    import pcbnew
    mm = pcbnew.FromMM
    t = pcbnew.PCB_TEXT(board)
    t.SetText("%s rev %s" % (title, revision))
    t.SetLayer(pcbnew.F_SilkS)
    t.SetTextSize(pcbnew.VECTOR2I(mm(SILK_TEXT[0]), mm(SILK_TEXT[0])))
    t.SetTextThickness(mm(SILK_TEXT[1]))
    t.SetHorizJustify(pcbnew.GR_TEXT_H_ALIGN_RIGHT)
    t.SetVertJustify(pcbnew.GR_TEXT_V_ALIGN_BOTTOM)
    t.SetPosition(pcbnew.VECTOR2I(mm(at[0]), mm(at[1])))
    board.Add(t)
    tb = board.GetTitleBlock()
    tb.SetTitle(title)
    tb.SetRevision(revision)
    tb.SetCompany("Kaplan Labs")
    board.SetTitleBlock(tb)


def place_designators(board, outline, labels=None, gap=0.3):
    """Put every reference designator horizontal, in the first spot around its
    part that clears all pads, every other part's courtyard, the other
    designators, board-only graphics (logos) and the board edge. A part in
    `labels` ({ref: word}) gets that word there instead, and its designator
    is hidden: an LED says what it shows, not "D3"."""
    import pcbnew
    mm = pcbnew.FromMM

    def box(bb, grow=0.0):
        return (pcbnew.ToMM(bb.GetLeft()) - grow, pcbnew.ToMM(bb.GetTop()) - grow,
                pcbnew.ToMM(bb.GetRight()) + grow, pcbnew.ToMM(bb.GetBottom()) + grow)

    def courtyard(fp):
        cy = fp.GetCourtyard(pcbnew.F_CrtYd if not fp.IsFlipped() else pcbnew.B_CrtYd)
        return box(cy.BBox()) if cy.OutlineCount() else box(fp.GetBoundingBox(False))

    fps = list(board.GetFootprints())
    pads = [box(p.GetBoundingBox(), 0.15) for fp in fps for p in fp.Pads()]
    courts = {fp.GetReference(): courtyard(fp) for fp in fps}
    x0, y0, x1, y1 = outline
    inside = (x0 + 0.3, y0 + 0.3, x1 - 0.3, y1 - 0.3)
    placed = []
    labels = labels or {}
    for fp in sorted(fps, key=lambda f: f.GetReference()):
        ref = fp.Reference()
        if not ref.IsVisible() or fp.GetAttributes() & pcbnew.FP_BOARD_ONLY:
            continue
        if fp.GetReference() in labels:
            ref.SetVisible(False)
            ref = pcbnew.PCB_TEXT(board)
            ref.SetText(labels[fp.GetReference()])
            ref.SetLayer(pcbnew.F_SilkS)
            board.Add(ref)
        ref.SetTextSize(pcbnew.VECTOR2I(mm(SILK_TEXT[0]), mm(SILK_TEXT[0])))
        ref.SetTextThickness(mm(SILK_TEXT[1]))
        ref.SetTextAngleDegrees(0)
        ref.SetHorizJustify(pcbnew.GR_TEXT_H_ALIGN_CENTER)
        ref.SetVertJustify(pcbnew.GR_TEXT_V_ALIGN_CENTER)
        others = [c for r, c in courts.items() if r != fp.GetReference()]
        spots = []
        # round the courtyard, then (for an imported footprint whose courtyard
        # is only its body, leads outside it) round its pads
        for cx0, cy0, cx1, cy1 in (courts[fp.GetReference()],
                                   union([courts[fp.GetReference()]] + [box(p.GetBoundingBox(), 0.5) for p in fp.Pads()])):
            mx, my = (cx0 + cx1) / 2, (cy0 + cy1) / 2
            for shift in (0, 1, -1, 2, -2, 3, -3):
                spots += [(mx + shift, cy0 - gap - 0.6), (mx + shift, cy1 + gap + 0.6),
                          (cx0 - gap - 1.5, my + shift), (cx1 + gap + 1.5, my + shift)]
        for sx, sy in spots:
            ref.SetPosition(pcbnew.VECTOR2I(mm(sx), mm(sy)))
            t = box(ref.GetBoundingBox())
            if t[0] < inside[0] or t[1] < inside[1] or t[2] > inside[2] or t[3] > inside[3]:
                continue
            if any(overlap(t, o, 0.1) for o in pads + others + placed):
                continue
            placed.append(t)
            break
        else:
            raise ValueError("%s: no room for its designator; move parts apart" % fp.GetReference())


def check_silk(board, clearance=0.15):          # JLC: silkscreen 0.15 mm from pads
    """Silkscreen lines and texts that touch a pad (KiCad's DRC does not check
    a footprint's silkscreen against its own pads). Returns problems."""
    import pcbnew
    mm = pcbnew.FromMM
    pads = []
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            bb = pad.GetBoundingBox()
            bb.Inflate(mm(clearance))
            pads.append((fp.GetReference(), pad.GetNumber(), pad.IsOnLayer(pcbnew.F_Cu),
                         pad.IsOnLayer(pcbnew.B_Cu), bb, pad))
    bad = []
    for fp in board.GetFootprints():
        gi = fp.GraphicalItems()          # indexed: iterating it breaks on Python 3.14
        graphics = [gi[i].Cast() for i in range(len(gi))]
        items = [(g, g.GetLayer()) for g in graphics if g.GetLayer() in (pcbnew.F_SilkS, pcbnew.B_SilkS)]
        items += [(t, t.GetLayer()) for t in (fp.Reference(), fp.Value())
                  if t.IsVisible() and t.GetLayer() in (pcbnew.F_SilkS, pcbnew.B_SilkS)]
        for g, layer in items:
            front = layer == pcbnew.F_SilkS
            if isinstance(g, pcbnew.PCB_SHAPE) and g.GetShape() == pcbnew.SHAPE_T_SEGMENT:
                a, b = g.GetStart(), g.GetEnd()
                steps = max(2, int(pcbnew.ToMM((b - a).EuclideanNorm()) / 0.02))
                probes = [pcbnew.VECTOR2I(int(a.x + (b.x - a.x) * k / steps), int(a.y + (b.y - a.y) * k / steps))
                          for k in range(steps + 1)]
                # the line's edge, not its centre: the pad box grows by half its width
                half = g.GetWidth() // 2
                hit = lambda bb, pad, half=half: any(                          # noqa: E731
                    pcbnew.BOX2I(bb.GetPosition() - pcbnew.VECTOR2I(half, half),
                                 bb.GetSize() + pcbnew.VECTOR2L(2 * half, 2 * half)).Contains(pt) for pt in probes)
            elif isinstance(g, pcbnew.PCB_SHAPE) and g.GetShape() == pcbnew.SHAPE_T_CIRCLE:
                # the ring, not its bounding box (which holds the pad it rings)
                c, r = g.GetCenter(), g.GetRadius() + g.GetWidth() / 2
                probes = [pcbnew.VECTOR2I(int(c.x + r * math.cos(k * math.pi / 90)),
                                          int(c.y + r * math.sin(k * math.pi / 90))) for k in range(180)]
                probes += [pcbnew.VECTOR2I(int(c.x + (r - g.GetWidth()) * math.cos(k * math.pi / 90)),
                                           int(c.y + (r - g.GetWidth()) * math.sin(k * math.pi / 90)))
                           for k in range(180)]
                hit = lambda bb, pad, probes=probes: any(                        # noqa: E731
                    bb.Contains(pt) and pad.HitTest(pt, mm(clearance)) for pt in probes)
            else:
                gb = g.GetBoundingBox()
                hit = lambda bb, pad, gb=gb: bb.Intersects(gb)           # noqa: E731
            for ref, num, on_f, on_b, bb, pad in pads:
                if (on_f if front else on_b) and hit(bb, pad):
                    bad.append("silkscreen of %s touches pad %s of %s" % (fp.GetReference(), num, ref))
    # the board's own silkscreen words (labels, the revision) against every
    # pad, and the free-standing ones (not a part's label) against every
    # part's courtyard on their side
    courts = []
    for fp in board.GetFootprints():
        side = pcbnew.F_CrtYd if fp.GetLayer() == pcbnew.F_Cu else pcbnew.B_CrtYd
        if len(fp.Pads()):
            cb = fp.GetCourtyard(side).BBox() if fp.GetCourtyard(side).OutlineCount() else None
            if cb is not None:
                courts.append((fp.GetReference(), fp.GetLayer() == pcbnew.F_Cu, cb))
    dr = board.Drawings()                        # indexed: iterating it breaks on Python 3.14
    for d in [dr[i].Cast() for i in range(len(dr))]:
        if d.Type() == pcbnew.PCB_TEXT_T and d.GetLayer() in (pcbnew.F_SilkS, pcbnew.B_SilkS):
            front = d.GetLayer() == pcbnew.F_SilkS
            gb = d.GetBoundingBox()
            for ref, num, on_f, on_b, bb, _ in pads:
                if (on_f if front else on_b) and bb.Intersects(gb):
                    bad.append("label %r touches pad %s of %s" % (d.GetText(), num, ref))
            if " rev " in d.GetText():
                for ref, on_f, cb in courts:
                    if on_f == front and cb.Intersects(gb):
                        bad.append("label %r overlaps the courtyard of %s" % (d.GetText(), ref))
    return sorted(set(bad))


def wrl_box(path, offset, rotation):
    """XY box (footprint coordinates, Y down) of a VRML model's parts at or
    above the board surface, placed with KiCad's offset and Z rotation."""
    xs, ys = [], []
    for block in re.findall(r'point\s*\[([^\]]*)\]', open(path).read()):
        n = [float(v) * 2.54 for v in re.findall(r'-?[\d.]+(?:e-?\d+)?', block)]   # VRML unit: 0.1"
        for x, y, z in zip(n[0::3], n[1::3], n[2::3]):
            if z < 0:
                continue                             # legs through the board
            a = math.radians(rotation[2])
            x, y = x * math.cos(a) - y * math.sin(a), x * math.sin(a) + y * math.cos(a)
            xs.append(x + offset[0])
            ys.append(-(y + offset[1]))              # model Y is up, the footprint's down
    return min(xs), min(ys), max(xs), max(ys)


def check_models(tolerance=0.6):
    """Every MODEL_OVERRIDES model sits on its footprint's F.Fab outline: the
    box centres agree within `tolerance` and so do the widths."""
    import pcbnew
    bad = []
    for fpid, (model, offset, rotation) in MODEL_OVERRIDES.items():
        lib, name = fpid.split(":")
        fp = pcbnew.FootprintLoad(footprint_dir(lib), name)
        gi = fp.GraphicalItems()
        fab = [gi[i].Cast().GetBoundingBox() for i in range(len(gi)) if gi[i].GetLayer() == pcbnew.F_Fab
               and gi[i].Cast().GetClass() == "PCB_SHAPE"]
        f = (min(pcbnew.ToMM(b.GetLeft()) for b in fab), min(pcbnew.ToMM(b.GetTop()) for b in fab),
             max(pcbnew.ToMM(b.GetRight()) for b in fab), max(pcbnew.ToMM(b.GetBottom()) for b in fab))
        m = wrl_box(os.path.join(HW_LIB, "models", model), offset, rotation)
        dc = math.hypot((m[0] + m[2] - f[0] - f[2]) / 2, (m[1] + m[3] - f[1] - f[3]) / 2)
        dw = abs((m[2] - m[0]) - (f[2] - f[0]))
        if dc > tolerance or dw > tolerance:
            bad.append("%s: model %s is %.2f mm off the fab outline (width differs %.2f mm)"
                       % (fpid, model, dc, dw))
    return bad


def canonical_dsn(text, seed=0):
    """The Specctra DSN in an order of our own: KiCad's export lists parts,
    images and net pins in an order that changes from run to run, and
    Freerouting's result depends on it. Everything order-free is sorted;
    `seed` > 0 then shuffles those lists by a seeded generator, so a retry
    gets a different, but still reproducible, problem."""
    import random
    rnd = random.Random(seed)
    text = text.replace('(string_quote ")', "(string_quote QUOTE_CHAR)")
    tree = parse(text)

    def order(items, key):
        items.sort(key=key)
        if seed:
            rnd.shuffle(items)
        return items

    def reorder(node, tag, key):
        """sort (and maybe shuffle) node's `tag` children in place, keeping
        everything else where it was"""
        slots = [i for i, e in enumerate(node) if isinstance(e, list) and e and e[0] == tag]
        for i, e in zip(slots, order([node[i] for i in slots], key)):
            node[i] = e
    name = lambda e: str(e[1])                                     # noqa: E731
    # KiCad names a footprint's variants base, base::1, base::2 in the order
    # it meets them: name them by content instead
    rename = {}
    for library in find(tree, "library"):
        groups = {}
        for img in find(library, "image"):
            groups.setdefault(str(img[1]).split("::")[0], []).append(img)
        for base, imgs in groups.items():
            imgs.sort(key=lambda img: dump(img[2:]))
            for n, img in enumerate(imgs):
                new = base if n == 0 else "%s::%d" % (base, n)
                rename[str(img[1])] = new
                img[1] = type(img[1])(new)
    for placement in find(tree, "placement"):
        for comp in find(placement, "component"):
            comp[1] = type(comp[1])(rename.get(str(comp[1]), str(comp[1])))
    for placement in find(tree, "placement"):
        reorder(placement, "component", name)
        for comp in find(placement, "component"):
            reorder(comp, "place", name)
    for wiring in find(tree, "wiring"):                # pre-routed copper
        # KiCad sometimes joins connected segments into one path: split every
        # path into its segments
        out = []
        for e in wiring:
            path = find1(e, "path") if isinstance(e, list) and e and e[0] == "wire" else None
            if path is None or len(path) <= 7:
                out.append(e)
                continue
            pts = path[3:]
            for i in range(0, len(pts) - 2, 2):
                out.append([p if p is not path else path[:3] + pts[i:i + 4] for p in e])
        wiring[:] = out
        reorder(wiring, "wire", dump)
        reorder(wiring, "via", dump)
    for library in find(tree, "library"):
        reorder(library, "image", name)
        reorder(library, "padstack", name)
    for network in find(tree, "network"):
        reorder(network, "net", name)
        for net in find(network, "net"):
            for pins in find(net, "pins"):
                pins[1:] = order(pins[1:], str)
        for cls in find(network, "class"):
            cls[2:] = [e for e in cls[2:] if isinstance(e, list)] + order(
                [e for e in cls[2:] if not isinstance(e, list)], str)
    return dump(tree).replace("(string_quote QUOTE_CHAR)", '(string_quote ")')


def remove_dangling(board, pours=()):
    """What Freerouting sometimes leaves behind: a via joined on one layer
    only, or a track whose end meets nothing. Removed until none is left, as
    KiCad's own cleanup does. Nets in `pours` are left alone: their pours
    are not filled yet, so their vias would look dangling. Returns the count."""
    import pcbnew
    removed = 0
    while True:
        tracks = board.Tracks()                  # indexed: iterating it breaks on Python 3.14
        items = [tracks[i].Cast() for i in range(len(tracks))]
        items = [t for t in items if t.GetNetname() not in pours]
        segs = [t for t in items if t.Type() == pcbnew.PCB_TRACE_T]
        vias = [t for t in items if t.Type() == pcbnew.PCB_VIA_T]
        pads = [p for fp in board.GetFootprints() for p in fp.Pads()]

        def seg_dist(pt, t):
            ax, ay, bx, by = t.GetStart().x, t.GetStart().y, t.GetEnd().x, t.GetEnd().y
            dx, dy = bx - ax, by - ay
            k = 0.0 if dx == dy == 0 else max(0.0, min(1.0, ((pt.x - ax) * dx + (pt.y - ay) * dy) / (dx * dx + dy * dy)))
            return math.hypot(pt.x - ax - k * dx, pt.y - ay - k * dy)

        def joined(pt, layer, net, reach, skip=None):
            """anything of `net` on `layer` at `pt`: a pad, a via, another track"""
            for p in pads:
                if p.GetNetname() == net and p.IsOnLayer(layer) and p.HitTest(pt, reach):
                    return True
            for v in vias:
                if v is not skip and v.GetNetname() == net and v.HitTest(pt, reach):
                    return True
            for t in segs:
                if t is not skip and t.GetNetname() == net and t.GetLayer() == layer and \
                        seg_dist(pt, t) <= t.GetWidth() / 2 + reach:
                    return True
            return False
        gone = []
        for v in vias:
            layers = [l for l in (pcbnew.F_Cu, pcbnew.B_Cu) if joined(v.GetPosition(), l, v.GetNetname(), v.GetWidth(l) // 2, skip=v)]
            if len(layers) < 2:
                gone.append(v)
        for t in segs:
            for end in (t.GetStart(), t.GetEnd()):
                if not joined(end, t.GetLayer(), t.GetNetname(), t.GetWidth() // 2, skip=t):
                    gone.append(t)
                    break
        if not gone:
            return removed
        for t in gone:
            board.Remove(t)
        removed += len(gone)


def autoroute(board, workdir, passes=40, pours=(), tries=3):
    """Route with Freerouting through a Specctra DSN/SES round trip. Its run
    sometimes stops with connections left; those outside the `pours` nets
    (which the pours and stitching join) mean another try with more passes,
    and an error after `tries`."""
    import pcbnew
    dsn = os.path.join(workdir, "route.dsn")
    ses = os.path.join(workdir, "route.ses")
    env = dict(os.environ, JAVA_TOOL_OPTIONS="-Djava.awt.headless=true")
    # tracks pre-routed on inner plane layers (presence_link's run on a wide
    # card) are not in the DSN, and the SES import drops them: keep them
    tracks = board.Tracks()
    inner = [(tracks[i].GetStart(), tracks[i].GetEnd(), tracks[i].GetWidth(), tracks[i].GetLayer(),
              tracks[i].GetNet()) for i in range(len(tracks))
             if tracks[i].Type() == pcbnew.PCB_TRACE_T and tracks[i].GetLayer() not in (pcbnew.F_Cu, pcbnew.B_Cu)]
    for attempt in range(tries):
        # each try orders the problem differently (a UUID salt): Freerouting
        # can stall on one order and complete on another, and the salt keeps
        # every run of the pipeline the same
        stable_uuids(board, attempt)
        if not pcbnew.ExportSpecctraDSN(board, dsn):
            raise RuntimeError("DSN export failed")
        with open(dsn) as f:
            text = canonical_dsn(f.read(), attempt)
        with open(dsn, "w") as f:
            f.write(text)
        if os.path.exists(ses):
            os.remove(ses)
        # one optimiser thread: with a pool, the route (and whether it
        # completes) changes from run to run
        r = run(["freerouting", "-de", dsn, "-do", ses, "-mp", str(passes * (attempt + 1)), "-mt", "1",
                 "--gui.enabled=false"], env=env)
        with open(os.path.join(workdir, "freerouting.log"), "w") as f:
            f.write(r.stdout + r.stderr)
        left = [n for n in re.findall(r"Net '([^']+)' \(\d+ unrouted", r.stdout + r.stderr) if n not in pours]
        if not left and os.path.exists(ses):
            break
    else:
        raise RuntimeError("Freerouting left %s unrouted after %d tries (see freerouting.log)" % (left, tries))
    if not os.path.exists(ses):
        raise RuntimeError("Freerouting wrote no session file")
    if not pcbnew.ImportSpecctraSES(board, ses):
        raise RuntimeError("SES import failed")
    for start, end, width, layer, net in inner:
        t = pcbnew.PCB_TRACK(board)
        t.SetStart(start)
        t.SetEnd(end)
        t.SetWidth(width)
        t.SetLayer(layer)
        t.SetNet(net)
        t.SetLocked(True)
        board.Add(t)
    remove_dangling(board, pours)
    # the import can pair one net class's via diameter with another's drill
    # (0.6 mm with 0.4 mm: a 0.1 mm ring, under JLC's 0.13): keep a 0.15 mm ring
    tracks = board.Tracks()                      # indexed: iterating it breaks on Python 3.14
    for v in [tracks[i].Cast() for i in range(len(tracks)) if tracks[i].Type() == pcbnew.PCB_VIA_T]:
        if v.GetWidth(pcbnew.F_Cu) - v.GetDrillValue() < pcbnew.FromMM(0.3):
            v.SetDrill(v.GetWidth(pcbnew.F_Cu) - pcbnew.FromMM(0.3))


def ground_fingers(board, net, tab_top, rise=1.0, rise_top=4.5, width=0.5, via=0.6, drill=0.3):
    """Tie every `net` finger of each card-edge footprint into the body: a
    locked track on the finger's own layer, from its top up into the pour
    `rise` mm above the tab. Pours alone can't reach fingers the key notch
    and neighbouring signals cut off. A column (An facing Bn) gets a via at
    the track's end when both its fingers are on `net` or the other is
    unused: a via there blocks nobody, and it joins the layers where a strip
    of pour is too narrow for a stitching via. Top-side (B) ties rise
    `rise_top`, past the presence link's bottom-layer run, and end in a via
    onto the bottom pour above it: below that run the fingers' strips of
    pour are fenced in on both layers. Returns the fingers tied."""
    import pcbnew
    mm, to = pcbnew.FromMM, pcbnew.ToMM
    ni = board.FindNet(net)
    n = 0
    for fp in board.GetFootprints():
        if not str(fp.GetFPID().GetLibNickname()).startswith("Connector_PCBEdge"):
            continue
        pads = {p.GetNumber(): p for p in fp.Pads()}
        done = set()
        for num, pad in pads.items():
            if pad.GetNetname() != net:
                continue
            x = to(pad.GetPosition().x)
            top = to(pad.GetBoundingBox().GetTop())
            front = pad.IsOnLayer(pcbnew.F_Cu)
            end = tab_top - (rise_top if front else rise)
            t = pcbnew.PCB_TRACK(board)
            t.SetStart(pcbnew.VECTOR2I(mm(x), mm(top + width / 2)))
            t.SetEnd(pcbnew.VECTOR2I(mm(x), mm(end)))
            t.SetWidth(mm(width))
            t.SetLayer(pcbnew.F_Cu if front else pcbnew.B_Cu)
            t.SetNet(ni)
            t.SetLocked(True)
            board.Add(t)
            n += 1
            if front:
                v = pcbnew.PCB_VIA(board)
                v.SetPosition(pcbnew.VECTOR2I(mm(x), mm(end)))
                v.SetWidth(mm(via))
                v.SetDrill(mm(drill))
                v.SetNet(ni)
                v.SetLocked(True)
                board.Add(v)
            facing = pads.get(("B" if num.startswith("A") else "A") + num[1:])
            unused = facing is None or not facing.GetNetname() or facing.GetNetname().startswith("unconnected-")
            if num[1:] not in done and (unused or facing.GetNetname() == net):
                done.add(num[1:])
                v = pcbnew.PCB_VIA(board)
                v.SetPosition(pcbnew.VECTOR2I(mm(x), mm(tab_top - rise)))
                v.SetWidth(mm(via))
                v.SetDrill(mm(drill))
                v.SetNet(ni)
                v.SetLocked(True)
                board.Add(v)
    return n


def ground_fanout(board, net, via=0.6, drill=0.3, track=0.3, gap=0.2):
    """Before routing, give every SMD pad on `net` (edge fingers aside) a
    short track to its own via, pointing away from a small part's centre
    (towards a big one's), so the
    router routes round it instead of walling it in (a pad boxed in by
    signals reaches the pour through a sliver or not at all). No sharing a
    neighbour's via: a signal routed between them would cut the pad off.
    Returns the vias placed."""
    import pcbnew
    mm, to = pcbnew.FromMM, pcbnew.ToMM
    ni = board.FindNet(net)
    pads = [(p, fp) for fp in board.GetFootprints() for p in fp.Pads()
            if not str(fp.GetFPID().GetLibNickname()).startswith("Connector_PCBEdge")]
    others = []                                   # other nets' pads, grown for a via / a track
    for p, _ in pads:
        if p.GetNetname() != net:
            bb = p.GetBoundingBox()
            others.append((to(bb.GetLeft()), to(bb.GetTop()), to(bb.GetRight()), to(bb.GetBottom())))
    vias = []
    edge = board.GetBoardEdgesBoundingBox()
    ex0, ey0, ex1, ey1 = to(edge.GetLeft()) + 0.8, to(edge.GetTop()) + 0.8, to(edge.GetRight()) - 0.8, to(edge.GetBottom()) - 0.8
    tracks = board.Tracks()
    locked = [(to(tracks[i].GetStart().x), to(tracks[i].GetStart().y), to(tracks[i].GetEnd().x),
               to(tracks[i].GetEnd().y), tracks[i].GetNetname()) for i in range(len(tracks))]

    def clear_of(x, y, grow):
        return not any(b[0] - grow < x < b[2] + grow and b[1] - grow < y < b[3] + grow for b in others)

    def seg_dist(px, py, ax, ay, bx, by):
        dx, dy = bx - ax, by - ay
        t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy or 1e-12)))
        return math.hypot(px - ax - t * dx, py - ay - t * dy)
    n = 0
    for p, fp in pads:
        if p.GetNetname() != net or p.GetAttribute() != pcbnew.PAD_ATTRIB_SMD:
            continue
        cx, cy = to(p.GetPosition().x), to(p.GetPosition().y)
        fx, fy = to(fp.GetPosition().x), to(fp.GetPosition().y)
        base = math.atan2(cy - fy, cx - fx) if math.hypot(cx - fx, cy - fy) > 0.1 else -math.pi / 2
        if len(fp.Pads()) > 8:
            # a module or IC: in, under the part (tented), not out, where a
            # row of GND pins' vias would wall in the pins between them
            base += math.pi
        layer = pcbnew.F_Cu if p.IsOnLayer(pcbnew.F_Cu) else pcbnew.B_Cu
        placed = False
        for r in (1.0, 1.3, 1.6, 2.0):
            for da in (0, 30, -30, 60, -60, 90, -90, 135, -135, 180):
                a = base + math.radians(da)
                vx, vy = cx + r * math.cos(a), cy + r * math.sin(a)
                if not (ex0 < vx < ex1 and ey0 < vy < ey1):
                    continue
                if not clear_of(vx, vy, via / 2 + gap):
                    continue
                if any(math.hypot(vx - ox, vy - oy) < via + 0.25 for ox, oy in vias):
                    continue
                if any(l[4] != net and seg_dist(vx, vy, *l[:4]) < via / 2 + gap + 0.25 for l in locked):
                    continue
                samples = [(cx + (vx - cx) * i / 12, cy + (vy - cy) * i / 12) for i in range(13)]
                if not all(clear_of(sx, sy, track / 2 + gap) for sx, sy in samples):
                    continue
                if any(l[4] != net and seg_dist(sx, sy, *l[:4]) < track / 2 + gap + 0.25
                       for l in locked for sx, sy in samples):
                    continue
                t = pcbnew.PCB_TRACK(board)
                t.SetStart(p.GetPosition())
                t.SetEnd(pcbnew.VECTOR2I(mm(vx), mm(vy)))
                t.SetWidth(mm(track))
                t.SetLayer(layer)
                t.SetNet(ni)
                t.SetLocked(True)
                board.Add(t)
                v = pcbnew.PCB_VIA(board)
                v.SetPosition(pcbnew.VECTOR2I(mm(vx), mm(vy)))
                v.SetWidth(mm(via))
                v.SetDrill(mm(drill))
                v.SetNet(ni)
                v.SetLocked(True)
                board.Add(v)
                vias.append((vx, vy))
                n += 1
                placed = True
                break
            if placed:
                break
    return n


def presence_link(board, tab_top, rise=3.0, width=0.25, via=0.6, drill=0.3, layer="B.Cu"):
    """Pre-route the presence link every card makes (PRSNT1_n on A1 joined
    to PRSNT2_n on the last B finger): up from A1 on B.Cu, across `rise` mm
    above the tab, a via, and down to the B finger on F.Cu. It must cross
    the other fingers' escapes, and Freerouting gives up on it; the few it
    crosses it routes round. `layer` carries the run across: on a wide card
    whose bottom-side fingers all have signals (the CPU card's address bus)
    a B.Cu run walls them off, so it goes on an inner layer between vias.
    Returns True if a link was drawn."""
    import pcbnew
    mm, to = pcbnew.FromMM, pcbnew.ToMM
    for fp in board.GetFootprints():
        if not str(fp.GetFPID().GetLibNickname()).startswith("Connector_PCBEdge"):
            continue
        pads = {p.GetNumber(): p for p in fp.Pads()}
        last_b = max((k for k in pads if k.startswith("B")), key=lambda k: int(k[1:]))
        a1, bn = pads.get("A1"), pads[last_b]
        if a1 is None or not a1.GetNetname() or a1.GetNetname() != bn.GetNetname():
            continue
        y = tab_top - rise
        ax, bx = to(a1.GetPosition().x), to(bn.GetPosition().x)
        run = board.GetLayerID(layer)
        pts = [(pcbnew.B_Cu, (ax, to(a1.GetBoundingBox().GetTop()) + width / 2), (ax, y)),
               (run, (ax, y), (bx, y)),
               (pcbnew.F_Cu, (bx, y), (bx, to(bn.GetBoundingBox().GetTop()) + width / 2))]
        for layer, a, b in pts:
            t = pcbnew.PCB_TRACK(board)
            t.SetStart(pcbnew.VECTOR2I(mm(a[0]), mm(a[1])))
            t.SetEnd(pcbnew.VECTOR2I(mm(b[0]), mm(b[1])))
            t.SetWidth(mm(width))
            t.SetLayer(layer)
            t.SetNet(a1.GetNet())
            t.SetLocked(True)
            board.Add(t)
        for vx in ((bx,) if run == pcbnew.B_Cu else (ax, bx)):
            v = pcbnew.PCB_VIA(board)
            v.SetPosition(pcbnew.VECTOR2I(mm(vx), mm(y)))
            v.SetWidth(mm(via))
            v.SetDrill(mm(drill))
            v.SetNet(a1.GetNet())
            v.SetLocked(True)
            board.Add(v)
        return True
    return False


UNJOINED = []                            # pour pieces stitch(fragments=True) could not join, for the report


def stitch(board, net, polygon, pitch=4.0, via=0.6, drill=0.3, clearance=0.3, fragments=False):
    """GND stitching: a via on a `pitch` grid inside `polygon` wherever it
    clears every pad, track, other via and the board edge
    by `clearance`, so the pours on each layer are one net and don't leave
    islands. Freerouting adds none. With `fragments`, instead one via in each
    filled piece of the pour that has none, at the first free spot on a fine
    grid: the strips signals cut off, too narrow for the coarse grid to hit.
    Returns the count."""
    import pcbnew
    mm, to = pcbnew.FromMM, pcbnew.ToMM
    ni = board.FindNet(net)
    keep = via / 2 + clearance
    boxes = []                                   # (x0, y0, x1, y1) keep-outs, mm

    def add_box(bb, grow=0.0):
        boxes.append((to(bb.GetLeft()) - grow, to(bb.GetTop()) - grow,
                       to(bb.GetRight()) + grow, to(bb.GetBottom()) + grow))
    # pads, not courtyards: a tented via under a part is fine (Espressif
    # asks for vias under the module's GND pads), and inside a module's pad
    # ring it is the only way that copper joins the rest of the pour
    raw_pads = []                                # (x0, y0, x1, y1, net, pad) as drawn, mm
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            add_box(pad.GetBoundingBox(), keep)
            bb = pad.GetBoundingBox()
            raw_pads.append((to(bb.GetLeft()), to(bb.GetTop()), to(bb.GetRight()), to(bb.GetBottom()),
                             pad.GetNetname(), pad))
        if not len(fp.Pads()):                   # artwork (the logo): no via through its silkscreen
            add_box(fp.GetBoundingBox(False), keep)
    segs = []
    tracks = board.Tracks()                      # indexed: iterating it breaks on Python 3.14
    for t in [tracks[i] for i in range(len(tracks))]:
        if t.Type() == pcbnew.PCB_VIA_T:
            add_box(t.GetBoundingBox(), keep + 0.2)
        else:
            segs.append((to(t.GetStart().x), to(t.GetStart().y), to(t.GetEnd().x), to(t.GetEnd().y),
                         to(t.GetWidth()) / 2 + keep, t.GetNetname(), to(t.GetWidth()) / 2))

    def seg_dist(px, py, ax, ay, bx, by):
        dx, dy = bx - ax, by - ay
        t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy or 1e-12)))
        return math.hypot(px - ax - t * dx, py - ay - t * dy)

    def inside(px, py):                          # even-odd point in polygon
        n, c = len(polygon), False
        for i in range(n):
            (ax, ay), (bx, by) = polygon[i], polygon[(i + 1) % n]
            if (ay > py) != (by > py) and px < ax + (py - ay) * (bx - ax) / (by - ay):
                c = not c
        return c

    def edge_ok(px, py):
        n = len(polygon)
        return all(seg_dist(px, py, *polygon[i], *polygon[(i + 1) % n]) >= keep + 0.3 for i in range(n))
    # the pours as filled now: a via only where copper surrounds it on both
    # layers, else it would dangle in a gap or hold up an island
    pours = [z for z in board.Zones() if z.GetNetname() == net]

    def filled(px, py):
        pt = pcbnew.VECTOR2I(mm(px), mm(py))
        return all(any(z.HitTestFilledArea(layer, pt, 0) for z in pours if z.IsOnLayer(layer))
                   for layer in (pcbnew.F_Cu, pcbnew.B_Cu))
    def ok(x, y):
        return (inside(x, y) and edge_ok(x, y) and filled(x, y)
                and not any(b[0] < x < b[2] and b[1] < y < b[3] for b in boxes)
                and all(seg_dist(x, y, *sg[:4]) >= sg[4] for sg in segs))

    def place(x, y):
        v = pcbnew.PCB_VIA(board)
        v.SetPosition(pcbnew.VECTOR2I(mm(x), mm(y)))
        v.SetWidth(mm(via))
        v.SetDrill(mm(drill))
        v.SetNet(ni)
        board.Add(v)
        boxes.append((x - keep - 0.2, y - keep - 0.2, x + keep + 0.2, y + keep + 0.2))
        return v

    def fan_out(layer, out, other, good, track=0.25, gap=0.2):
        for x0, y0, x1, y1, pnet, pad in raw_pads:
            if pnet != net or not pad.IsOnLayer(layer) or not out.PointInside(pad.GetPosition()):
                continue
            cx, cy = to(pad.GetPosition().x), to(pad.GetPosition().y)
            own = (x0 - keep, y0 - keep, x1 + keep, y1 + keep)
            for r in (0.9, 1.1, 1.3, 1.6, 2.0, 2.5):
                for a in range(0, 360, 15):
                    px, py = cx + r * math.cos(math.radians(a)), cy + r * math.sin(math.radians(a))
                    pt = pcbnew.VECTOR2I(mm(px), mm(py))
                    if not (inside(px, py) and edge_ok(px, py) and good(pt)):
                        continue
                    if any(b != own and b[0] < px < b[2] and b[1] < py < b[3] for b in boxes):
                        continue
                    if not all(seg_dist(px, py, *sg[:4]) >= sg[4] for sg in segs):
                        continue
                    # the track from the pad to the via clears every other net
                    samples = [(cx + (px - cx) * i / 20, cy + (py - cy) * i / 20) for i in range(21)]
                    grow = track / 2 + gap
                    if any(q[4] != net and q[0] - grow < sx < q[2] + grow and q[1] - grow < sy < q[3] + grow
                           for q in raw_pads for sx, sy in samples):
                        continue
                    if any(sg[5] != net and seg_dist(sx, sy, *sg[:4]) < sg[6] + grow
                           for sg in segs for sx, sy in samples):
                        continue
                    place(px, py)
                    t = pcbnew.PCB_TRACK(board)
                    t.SetStart(pad.GetPosition())
                    t.SetEnd(pt)
                    t.SetWidth(mm(track))
                    t.SetLayer(layer)
                    t.SetNet(ni)
                    board.Add(t)
                    return True
        return False

    if fragments:
        # the pieces of the pour on each layer, joined by vias; walk from the
        # biggest piece on each layer and give each piece not reached a via
        # onto copper that is
        vias = [tracks[i] for i in range(len(tracks))
                if tracks[i].Type() == pcbnew.PCB_VIA_T and tracks[i].GetNetname() == net]
        pieces = []                              # (layer, outline)
        for z in pours:
            for layer in (pcbnew.F_Cu, pcbnew.B_Cu):
                if z.IsOnLayer(layer):
                    polys = z.GetFilledPolysList(layer)
                    pieces += [(layer, polys.Outline(i)) for i in range(polys.OutlineCount())]

        def piece_at(layer, pt):
            for k, (ly, out) in enumerate(pieces):
                if ly == layer and out.PointInside(pt):
                    return k
            return None
        reached = set()
        for layer in (pcbnew.F_Cu, pcbnew.B_Cu):
            own = [k for k, (ly, _) in enumerate(pieces) if ly == layer]
            if own:
                reached.add(max(own, key=lambda k: pieces[k][1].Area()))
        links = []
        for v in vias:
            a, b = piece_at(pcbnew.F_Cu, v.GetPosition()), piece_at(pcbnew.B_Cu, v.GetPosition())
            if a is not None and b is not None:
                links.append((a, b))
        grew = True
        while grew:
            grew = False
            for a, b in links:
                if (a in reached) != (b in reached):
                    reached |= {a, b}
                    grew = True
        count = 0
        for k, (layer, out) in enumerate(pieces):
            if k in reached:
                continue
            other = pcbnew.B_Cu if layer == pcbnew.F_Cu else pcbnew.F_Cu
            bb = out.BBox()
            y = to(bb.GetTop())
            found = None
            while found is None and y < to(bb.GetBottom()):
                x = to(bb.GetLeft())
                while x < to(bb.GetRight()):
                    pt = pcbnew.VECTOR2I(mm(x), mm(y))
                    if out.PointInside(pt) and piece_at(other, pt) in reached and ok(x, y):
                        found = (x, y)
                        break
                    x += 0.25
                y += 0.25
            if found:
                place(*found)
                reached.add(k)
                count += 1
                continue
            # no room inside (a pocket between one part's pads): fan out from
            # a pad of the net in it, to a via on reached copper beside it
            fan = fan_out(layer, out, other, lambda pt: piece_at(other, pt) in reached)
            if fan:
                reached.add(k)
                count += 1
            else:
                UNJOINED.append("%s piece at %.1f,%.1f..%.1f,%.1f mm" % (
                    "top" if layer == pcbnew.F_Cu else "bottom",
                    to(bb.GetLeft()), to(bb.GetTop()), to(bb.GetRight()), to(bb.GetBottom())))
        return count
    xs = [p[0] for p in polygon]
    ys = [p[1] for p in polygon]
    count = 0
    y = min(ys) + pitch / 2
    while y < max(ys):
        x = min(xs) + pitch / 2
        while x < max(xs):
            if ok(x, y):
                place(x, y)
                count += 1
            x += pitch
        y += pitch
    return count


def fill_zones(board):
    import pcbnew
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())


# ------------------------------------------------------ the I/O card outline
# doc/hardware/slot.md, Mechanical: every I/O card is this shape, in the
# frame of KiCad's BUS_PCIexpress_x1 (finger B1 at the origin, fingers +y)
IO_CARD_BODY = (-6.0, -44.0, 56.0, -4.95)
IO_CARD_EDGE = [(-0.65, -4.95), (-6.0, -4.95), (-6.0, -44.0), (56.0, -44.0), (56.0, -4.95), (19.65, -4.95)]
IO_CARD_TAB = (-0.65, 19.65)
IO_CARD_HOLE = (52.0, -40.0)             # M3, non-plated
IO_CARD_PWR_LED = (-3.0, -41.0)          # the power LED, the same on every board: 3 mm in from top-left
MOUNTING_HOLE = "MountingHole:MountingHole_3.2mm_M3"


def power_led_at(body):
    """Where a board's power LED goes: 3 mm in from its body's top-left
    corner (milestone-1.md, Indicator LEDs)."""
    return (body[0] + 3.0, body[1] + 3.0)


# ---------------------------------------------------------------- pipeline

# footprints that are not parts: nothing to buy, nothing for JLC to place
NOT_PARTS = ("Connector_PCBEdge:", "cupc8:KaplanLabs_Logo", "cupc8:TestPad", "TestPoint:", "MountingHole:")


def jlc_fab(sch, pcb, comps, fab):
    """JLC's assembly files: bom.csv (Comment, Designator, Footprint, LCSC Part #)
    and cpl.csv (Designator, Mid X, Mid Y, Layer, Rotation: KiCad's plus the
    footprint's hw/parts/jlc_rotation.yaml correction). Every part must
    carry an LCSC number, because nothing is fitted by hand."""
    import csv

    def lcsc(c):                          # our field, or the one easyeda2kicad writes
        return c.get("fields", {}).get("LCSC") or c.get("fields", {}).get("LCSC Part")
    missing = sorted(r for r, c in comps.items() if not lcsc(c) and not c["footprint"].startswith(NOT_PARTS))
    if missing:
        raise SystemExit("parts without an LCSC number: %s" % ", ".join(missing))
    placed = {r: c for r, c in comps.items() if lcsc(c)}
    groups = {}
    for r, c in placed.items():
        groups.setdefault((c["value"], c["footprint"], lcsc(c)), []).append(r)
    with open(os.path.join(fab, "bom.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Comment", "Designator", "Footprint", "LCSC Part #"])
        for (val, fp, lcsc), refs in sorted(groups.items(), key=lambda g: g[1][0]):
            w.writerow([val, ",".join(sorted(refs)), fp.split(":")[1], lcsc])
    raw = os.path.join(fab, "kicad-pos.csv")
    run(["kicad-cli", "pcb", "export", "pos", "--format", "csv", "--units", "mm", "--side", "both",
         "-o", raw, pcb])
    import bomcheck
    turn = bomcheck.rotations()           # JLC's footprint zero vs KiCad's (hw/parts/jlc_rotation.yaml)
    with open(raw) as f, open(os.path.join(fab, "cpl.csv"), "w", newline="") as g:
        w = csv.writer(g)
        w.writerow(["Designator", "Mid X", "Mid Y", "Layer", "Rotation"])
        for row in csv.DictReader(f):
            if row["Ref"] in placed:
                rot = (float(row["Rot"]) + turn.get(placed[row["Ref"]]["footprint"], 0)) % 360
                w.writerow([row["Ref"], row["PosX"] + "mm", row["PosY"] + "mm",
                            "Top" if row["Side"] == "top" else "Bottom", "%.6f" % rot])
    os.remove(raw)
    counts = {}
    for (_, _, code), refs in groups.items():
        counts[code] = counts.get(code, 0) + len(refs)
    return counts


def check_stock(counts, boards, margin=2):
    """Every part in JLC's assembly library with `margin` times the stock the
    order needs (`boards` assembled, each part's count per board):
    verification.md 4.8. CUPC8_OFFLINE=1 skips it (and says so)."""
    if os.environ.get("CUPC8_OFFLINE"):
        return "skipped: CUPC8_OFFLINE"
    import jlcparts
    short = []
    for code, n in sorted(counts.items()):
        need = n * boards * margin
        hits = [p for p in jlcparts.query(code, 5) if p["componentCode"] == code]
        if not hits:
            short.append("%s not in JLC's library" % code)
        elif hits[0]["stockCount"] < need:
            short.append("%s: %d in stock, under %dx the %d the order places"
                         % (code, hits[0]["stockCount"], margin, n * boards))
    if short:
        raise SystemExit("JLC stock:\n  " + "\n  ".join(short))
    return "%d parts, %dx stock for %d boards" % (len(counts), margin, boards)


def order_spec(layers, card_edge):
    """The JLC order options, written next to the Gerbers as order.json.
    Cards (card_edge) are 1.6 mm with hard-gold fingers and a 30 degree
    chamfer (milestone-1.md, Board thickness); check_order enforces it."""
    spec = {"layers": layers, "thickness_mm": 1.6, "surface_finish": "ENIG", "min_hole_mm": 0.3,
            "assembly": "PCBA top side, parts from bom.csv/cpl.csv, all LCSC",
            "gold_fingers": card_edge, "finger_finish": "hard gold" if card_edge else None,
            "finger_chamfer_deg": 30 if card_edge else None}
    if layers == 4:
        spec["stackup"] = "JLC04161H-7628"
    return spec


def check_order(spec, card_edge):
    bad = []
    if spec["thickness_mm"] != 1.6:
        bad.append("thickness %s mm, cards must be 1.6" % spec["thickness_mm"])
    if card_edge and (not spec["gold_fingers"] or spec["finger_finish"] != "hard gold"
                      or spec["finger_chamfer_deg"] != 30):
        bad.append("card edge needs hard-gold fingers with a 30 degree chamfer")
    if bad:
        raise SystemExit("fab order: " + "; ".join(bad))


def pipeline(name, schematic, placement, outline, out=None, zones=("/GND",), power_nets=(),
             graphics=(), edge=None, layers=2, footprint_libs=("cupc8",), passes=40, card_edge=False,
             zone_outline=None, boards=2, labels=None, title=None, revision=None, revision_at=None,
             io_card=False, prepare=None, presence=None):
    """Schematic -> ERC -> netlist -> board -> Freerouting -> zones -> silk and
    3D-model checks -> DRC with schematic parity -> Gerbers, drill, JLC BOM and
    CPL -> BOM check (bomcheck.py) -> JLC stock for `boards` assembled -> 3D
    renders. `schematic(path, footprint_libs)` writes the sheet. Returns {LCSC number: count per board}.

    Every board carries its name and revision (doc/milestone-1.md, Board
    revision): `title` and `revision` are printed as "<title> rev <revision>"
    on the top silkscreen, in the body's bottom-right corner unless
    `revision_at` names another bottom-right anchor (mm), and go in the
    board's title block, which the Gerbers' X2 attributes carry.

    `prepare(board)`, if given, runs after the pad fan-out and before
    Freerouting: a board's own locked pre-routing (layer changes the router
    would otherwise scatter)."""
    import pcbnew
    if io_card:
        # every I/O card is the same shape (slot.md, Mechanical): the outline,
        # finger edge and pour come from here, and the parts every card has in
        # the same place are checked
        if outline not in (None, IO_CARD_BODY) or edge not in (None, IO_CARD_EDGE):
            raise SystemExit("%s: an I/O card has the standard outline (IO_CARD_BODY/EDGE), not its own" % name)
        outline, edge, card_edge = IO_CARD_BODY, IO_CARD_EDGE, True
        zone_outline = zone_outline or card_zone(IO_CARD_BODY, IO_CARD_TAB, -1.5)
        for ref, want in (("J1", (0, 0, 0)), ("H1", IO_CARD_HOLE + (0,)), ("D1", IO_CARD_PWR_LED + (0,))):
            if tuple(placement.get(ref, ())[:3]) != want:
                raise SystemExit("%s: an I/O card has %s at %s (slot.md, Mechanical), not %s" % (
                    name, ref, want, placement.get(ref)))
    if not (title and revision):
        raise SystemExit("%s: every board needs a title and a revision (doc/milestone-1.md, Board revision)" % name)
    revision_at = revision_at or (outline[2] - 1.0, outline[3] - 1.0)
    out = os.path.abspath(out or os.path.join(ROOT, "build", "hw", name))
    os.makedirs(out, exist_ok=True)
    sch, pcb, pro = (os.path.join(out, name + e) for e in (".kicad_sch", ".kicad_pcb", ".kicad_pro"))
    state = {}
    pour_nets = list(dict.fromkeys(z if isinstance(z, str) else z[0] for z in zones))

    def step(label, fn):
        print("%-28s" % label, end=" ", flush=True)
        r = fn()
        print("ok" + (" (%s)" % r if r else ""))

    def sheet():
        schematic(sch, footprint_libs)
        write_project(pro, power_nets=power_nets)   # before ERC: it carries the library tables
    step("schematic", sheet)
    step("ERC", lambda: run(["kicad-cli", "sch", "erc", "--format", "json", "--severity-all",
                             "--exit-code-violations", "-o", os.path.join(out, "erc.json"), sch]) and None)

    def netlist():
        c, n = export_netlist(sch, os.path.join(out, name + ".net"))
        state["c"] = {r: v for r, v in c.items() if not r.startswith("#")}
        state["n"] = n
        return "%d parts, %d nets" % (len(state["c"]), len(n))
    step("netlist", netlist)

    def build():
        b = build_board(state["c"], state["n"], placement, outline, layers=layers, zones=zones,
                        graphics=graphics, edge=edge, zone_outline=zone_outline, labels=labels)
        mark_revision(b, title, revision, revision_at)
        if card_edge:
            state["fingers"] = ground_fingers(b, zones[0], outline[3])
            presence_link(b, outline[3], **(presence or {}))   # e.g. {"layer": "In2.Cu"}
        # every poured net's pads get a via: GND, and any net on a plane
        # (build_board's (net, layers) zones), which is reached no other way
        state["fanout"] = sum(ground_fanout(b, n) for n in pour_nets)
        if prepare:                   # the board's own locked pre-routing, before Freerouting
            prepare(b)
        pcbnew.SaveBoard(pcb, b, True)
        state["b"] = pcbnew.LoadBoard(pcb)
        return ("%d GND fingers tied to the pour, " % state["fingers"] if card_edge else "") + \
            "%d GND pad vias" % state["fanout"]
    step("board", build)
    step("autoroute", lambda: autoroute(state["b"], out, passes, pours=pour_nets))

    def fill():
        x0, y0, x1, y1 = outline
        # the body only: no vias on a card's finger tab, even where the pour reaches it
        poly = [(x0 + .5, y0 + .5), (x1 - .5, y0 + .5), (x1 - .5, y1 - .5), (x0 + .5, y1 - .5)]
        # fill once keeping islands, so both layers' pours exist wherever
        # there is room (a layer with no pads of its own would otherwise be
        # dropped whole as an island), stitch where both have copper, then
        # fill again removing whatever still floats
        zs = list(state["b"].Zones())
        for z in zs:
            z.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_NEVER)
        fill_zones(state["b"])
        n = sum(stitch(state["b"], z, poly, pitch=3.0) for z in zones[:1])   # the first pour net (GND)
        for z in zs:
            z.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_ALWAYS)
        fill_zones(state["b"])
        for _ in range(3):                      # then any piece signals cut off, until none is left
            del UNJOINED[:]
            k = sum(stitch(state["b"], z, poly, fragments=True) for z in zones[:1])
            if not k:
                break
            n += k
            fill_zones(state["b"])
        pcbnew.SaveBoard(pcb, state["b"])
        return "%d stitching vias" % n + ("; NOT JOINED: " + "; ".join(UNJOINED) if UNJOINED else "")
    step("stitch + zones + save", fill)

    def silk():
        bad = check_silk(state["b"]) + check_models()
        if bad:
            raise SystemExit("silkscreen / 3D models:\n  " + "\n  ".join(bad))
    step("silkscreen, 3D models", silk)
    step("DRC + schematic parity", lambda: run(
        ["kicad-cli", "pcb", "drc", "--format", "json", "--schematic-parity", "--severity-all",
         "--exit-code-violations", "-o", os.path.join(out, "drc.json"), pcb]) and None)

    fab = os.path.join(out, "fab")
    os.makedirs(fab, exist_ok=True)

    def gerbers():
        # only what JLC fabricates from: copper, mask, paste, silkscreen, outline
        cu = ",".join(["F.Cu", "B.Cu"] + ["In%d.Cu" % i for i in range(1, layers - 1)])
        run(["kicad-cli", "pcb", "export", "gerbers", "--layers",
             cu + ",F.Mask,B.Mask,F.Paste,B.Paste,F.SilkS,B.SilkS,Edge.Cuts", "-o", fab + "/", pcb])
        run(["kicad-cli", "pcb", "export", "drill", "-o", fab + "/", pcb])
        return "%d files" % len(os.listdir(fab))
    step("gerbers + drill", gerbers)

    def bom():
        state["lcsc"] = jlc_fab(sch, pcb, state["c"], fab)
        return "%d distinct parts" % len(state["lcsc"])
    step("JLC BOM + CPL", bom)

    def parts():                          # verification 4.3 and 4.8's BOM <-> schematic (BRD-001)
        import bomcheck
        return bomcheck.check(name, out)
    step("BOM: parts, pins, rotations", parts)
    step("JLC stock", lambda: check_stock(state["lcsc"], boards))

    def order():
        import json
        spec = order_spec(layers, card_edge)
        check_order(spec, card_edge)
        with open(os.path.join(fab, "order.json"), "w") as f:
            json.dump(spec, f, indent=2)
    step("fab order spec", order)

    def render():
        for side in ("top", "bottom"):
            run(["kicad-cli", "pcb", "render", "--width", "1200", "--height", "800", "--quality", "high",
                 "--side", side, "-o", os.path.join(out, "%s-%s.png" % (name, side)), pcb])
    step("3D render", render)
    print("all steps passed; outputs in", out)
    return state["lcsc"]
