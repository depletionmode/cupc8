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
PROJECT_FOOTPRINTS = {"cupc8": os.path.join(ROOT, "hw", "lib", "cupc8.pretty")}


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


def uid():
    return Q(str(uuidlib.uuid4()))


# ----------------------------------------------------------------- symbols

_libs = {}


def _library(name):
    if name not in _libs:
        with open(os.path.join(KICAD_SYMBOLS, name + ".kicad_sym")) as f:
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
CHAR_W = 0.9                             # stroke-font character width / size (a little generous)
MARGIN = 0.25                            # clearance kept around text
PAGES = {"A4": (297, 210), "A3": (420, 297), "A2": (594, 420)}
FRAME = 10                               # page border
TITLE_BLOCK = (112, 36)                  # bottom-right, width x height


def text_box(x, y, s, angle=0, hj="center", vj="center", size=TEXT):
    """Axis-aligned box of a text item, angle 0 (horizontal) or 90 (reading up)."""
    w, h = len(s) * size * CHAR_W, size * 1.1
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
    """{number: (x, y, angle, name, type, length)} for one unit (style 1)."""
    pins = {}
    for sub in _units(sym, unit):
        for p in find(sub, "pin"):
            at = find1(p, "at")
            ln = find1(p, "length")
            pins[str(find1(p, "number")[1])] = (
                float(at[1]), float(at[2]), float(at[3]) if len(at) > 3 else 0.0,
                str(find1(p, "name")[1]), str(p[1]), float(ln[1]) if ln else 2.54)
    return pins


def _hidden(prop):
    if find1(prop, "hide"):
        return find1(prop, "hide")[1] == "yes"
    eff = find1(prop, "effects") or []
    return any(e == "hide" or (isinstance(e, list) and e[0] == "hide" and e[-1] != "no") for e in eff)


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
        for n, (x, y, ang, _, _, ln) in self.pins.items():
            a = math.radians(ang)
            ex, ey = x + ln * math.cos(a), y + ln * math.sin(a)
            (x0, y0), (x1, y1) = self.xf(x, y), self.xf(ex, ey)
            out.append(seg_box(x0, y0, x1, y1))
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
        self.wires = []                  # (x0, y0, x1, y1, part)
        self.labels = []                 # (box, text, part)

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
        self.wires.append((x, y, ex, ey, part))
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

    def nc(self, part, pin):
        num = part.pin(pin)
        for n in self._stacked(part, num):
            part.used[n] = None
        (x, y), _ = part.pin_xy(num)
        self.items.append(["no_connect", ["at", x, y], ["uuid", uid()]])

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
        obs += [(seg_box(*w[:4]), "wire", w[4]) for w in self.wires]
        obs += [(box, "text", part) for box, _, part in self.labels]
        return obs

    def _place_fields(self, p):
        texts = [(k, t) for k, t in (("Reference", p.ref), ("Value", p.value)) if p.show[k]]
        if not texts:
            return
        pitch = TEXT * 1.6
        w = max(len(t) for _, t in texts) * TEXT * CHAR_W
        h = pitch * len(texts)
        x0, y0, x1, y1 = p.extent()
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        gap = 1.0
        spots = []
        for shift in (0, GRID, -GRID, 2 * GRID, -2 * GRID, 3 * GRID, -3 * GRID):
            spots += [(x1 + gap + w / 2, cy + shift), (x0 - gap - w / 2, cy + shift),
                      (cx + shift, y0 - gap - h / 2), (cx + shift, y1 + gap + h / 2)]
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
                if kind in ("body", "pin", "wire") and overlap(a, b, -0.02):
                    bad.append("text of %s overlaps a %s of %s near (%.1f, %.1f)" % (pa.ref, kind, q.ref, a[0], a[1]))
        bodies = [(b, p) for b, k, p in obs if k == "body"]
        for i, (a, pa) in enumerate(bodies):
            for b, pb in bodies[i + 1:]:
                if overlap(a, b):
                    bad.append("bodies of %s and %s overlap" % (pa.ref, pb.ref))
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
                 ["exclude_from_sim", "no"], ["in_bom", "yes"], ["on_board", "yes"], ["dnp", "no"],
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
                           ["uri", Q(os.path.join(KICAD_SYMBOLS, n + ".kicad_sym"))],
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
    ("Default", 0.2, 0.15, 0.6, 0.3),
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
        "board": {"design_settings": {"rules": dict(JLC_RULES, **(rules or {}))}},
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


def build_board(comps, nets, placement, outline, layers=2, zones=("GND",), graphics=()):
    """A pcbnew BOARD with every footprint placed and every pad on its net.

    placement: {ref: (x_mm, y_mm, rot_deg[, "B" for the bottom side])}
    outline:   (x0, y0, x1, y1) in mm
    graphics:  board-only footprints such as logos: ("lib:name", x, y, rot)
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
    for a, b in (((x0, y0), (x1, y0)), ((x1, y0), (x1, y1)), ((x1, y1), (x0, y1)), ((x0, y1), (x0, y0))):
        seg = pcbnew.PCB_SHAPE(board)
        seg.SetShape(pcbnew.SHAPE_T_SEGMENT)
        seg.SetStart(pcbnew.VECTOR2I(mm(a[0]), mm(a[1])))
        seg.SetEnd(pcbnew.VECTOR2I(mm(b[0]), mm(b[1])))
        seg.SetLayer(pcbnew.Edge_Cuts)
        seg.SetWidth(mm(0.1))
        board.Add(seg)

    copper = [pcbnew.F_Cu, pcbnew.B_Cu]
    for net in zones:
        for layer in copper:
            z = pcbnew.ZONE(board)
            z.SetLayer(layer)
            z.SetNet(netinfo[net])
            z.SetLocalClearance(mm(0.3))
            z.SetMinThickness(mm(0.25))
            z.SetPadConnection(pcbnew.ZONE_CONNECTION_FULL)   # solid: fine for reflow, no starved spokes
            ol = z.Outline()
            ol.NewOutline()
            for px, py in ((x0 + .5, y0 + .5), (x1 - .5, y0 + .5), (x1 - .5, y1 - .5), (x0 + .5, y1 - .5)):
                ol.Append(mm(px), mm(py))
            board.Add(z)
    return board


def autoroute(board, workdir, passes=40):
    """Route with Freerouting through a Specctra DSN/SES round trip."""
    import pcbnew
    dsn = os.path.join(workdir, "route.dsn")
    ses = os.path.join(workdir, "route.ses")
    if os.path.exists(ses):
        os.remove(ses)
    if not pcbnew.ExportSpecctraDSN(board, dsn):
        raise RuntimeError("DSN export failed")
    env = dict(os.environ, JAVA_TOOL_OPTIONS="-Djava.awt.headless=true")
    run(["freerouting", "-de", dsn, "-do", ses, "-mp", str(passes), "--gui.enabled=false"], env=env)
    if not os.path.exists(ses):
        raise RuntimeError("Freerouting wrote no session file")
    if not pcbnew.ImportSpecctraSES(board, ses):
        raise RuntimeError("SES import failed")


def fill_zones(board):
    import pcbnew
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
