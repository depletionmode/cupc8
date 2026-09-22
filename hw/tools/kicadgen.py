"""Generate KiCad schematics and boards from Python descriptions.

KiCad has no scripting API for schematics, so .kicad_sch files are written
as S-expressions. Symbols come from the KiCad libraries and are flattened
(derived symbols merged with their parent), which is how KiCad itself embeds
them. Every connection is a short wire stub from the pin plus a net label,
so a schematic is a set of parts with named nets on their pins.

Boards are built with the pcbnew API from the netlist that kicad-cli exports
from the schematic, so the board can only contain what the schematic says.
"""

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


def symbol_pins(sym, unit=1):
    """{number: (x, y, angle, name, type)} for one unit (style 1)."""
    pins = {}
    base = str(sym[1]).split(":")[-1]
    for sub in find(sym, "symbol"):
        m = re.match(re.escape(base) + r"_(\d+)_(\d+)$", str(sub[1]))
        if not m or int(m.group(1)) not in (0, unit) or int(m.group(2)) not in (0, 1):
            continue
        for p in find(sub, "pin"):
            at = find1(p, "at")
            num = find1(p, "number")[1]
            name = find1(p, "name")[1]
            pins[str(num)] = (float(at[1]), float(at[2]), float(at[3]) if len(at) > 3 else 0.0,
                              str(name), str(p[1]))
    return pins


# --------------------------------------------------------------- schematic

class Part:
    def __init__(self, sch, lib_id, ref, value, footprint, at, rot, fields, unit):
        self.sch, self.lib_id, self.ref, self.value = sch, lib_id, ref, value
        self.footprint, self.at, self.rot, self.fields, self.unit = footprint, at, rot, fields, unit
        self.uuid = uid()
        self.sym = sch._symbol(lib_id)
        self.pins = symbol_pins(self.sym, unit)
        self.used = set()

    def pin(self, key):
        """A pin by number, or by name if the name is unique."""
        key = str(key)
        if key in self.pins:
            return key
        hits = [n for n, p in self.pins.items() if p[3] == key]
        if len(hits) != 1:
            raise KeyError("%s: no single pin %r (have %s)" % (self.ref, key, sorted(self.pins)))
        return hits[0]

    def pin_xy(self, num):
        """Schematic position of a pin's connection point, and its outward direction."""
        x, y, ang, _, _ = self.pins[num]
        # symbol Y is up, schematic Y is down; then rotate by the placement
        r = self.rot % 360
        rx, ry = {0: (x, -y), 90: (-y, -x), 180: (-x, y), 270: (y, x)}[r]
        # a pin points from its connection point into the body at `ang`
        out = (ang + 180 + r) % 360
        dx, dy = {0: (1, 0), 90: (0, -1), 180: (-1, 0), 270: (0, 1)}[round(out) % 360]
        return (self.at[0] + rx, self.at[1] + ry), (dx, dy)


class Schematic:
    def __init__(self, project, title="", paper="A3"):
        self.project, self.title, self.paper = project, title, paper
        self.uuid = uid()
        self.parts = []
        self.syms = {}
        self.items = []

    def _symbol(self, lib_id):
        if lib_id not in self.syms:
            self.syms[lib_id] = load_symbol(lib_id)
        return self.syms[lib_id]

    def add(self, lib_id, ref, value, footprint="", at=(0, 0), rot=0, fields=None, unit=1):
        p = Part(self, lib_id, ref, value, footprint, at, rot, fields or {}, unit)
        self.parts.append(p)
        return p

    def connect(self, part, pin, net, stub=2 * GRID):
        num = part.pin(pin)
        if num in part.used:
            raise ValueError("%s pin %s connected twice" % (part.ref, num))
        part.used.add(num)
        (x, y), (dx, dy) = part.pin_xy(num)
        ex, ey = round(x + dx * stub, 4), round(y + dy * stub, 4)
        self.items.append(["wire", ["pts", ["xy", x, y], ["xy", ex, ey]],
                           ["stroke", ["width", 0], ["type", "default"]], ["uuid", uid()]])
        angle = {(1, 0): 0, (0, -1): 90, (-1, 0): 180, (0, 1): 270}[(dx, dy)]
        justify = {0: "left", 90: "left", 180: "right", 270: "right"}[angle]
        self.items.append(["label", Q(net), ["at", ex, ey, angle % 180],
                           ["fields_autoplaced", "yes"],
                           ["effects", ["font", ["size", 1.27, 1.27]], ["justify", justify, "bottom"]],
                           ["uuid", uid()]])

    def nc(self, part, pin):
        num = part.pin(pin)
        part.used.add(num)
        (x, y), _ = part.pin_xy(num)
        self.items.append(["no_connect", ["at", x, y], ["uuid", uid()]])

    def unconnected(self):
        return [(p.ref, n) for p in self.parts for n in p.pins if n not in p.used]

    def _instance(self, p):
        props = []
        fields = [("Reference", p.ref), ("Value", p.value), ("Footprint", p.footprint)]
        fields += list(p.fields.items())
        for i, (k, v) in enumerate(fields):
            props.append(["property", Q(k), Q(v), ["at", p.at[0], p.at[1] - 5 - 2 * i if i < 2 else p.at[1], 0],
                          ["effects", ["font", ["size", 1.27, 1.27]]] + ([] if i < 2 else [["hide", "yes"]])])
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
        """footprint_libs: extra libraries the board uses (logos and such)."""
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
