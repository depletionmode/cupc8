#!/usr/bin/env python3
"""The main board's route seed: the proven route, locked, outside the areas
a board revision re-lays.

The main board takes Freerouting about three hours per ordering and has only
once completed (salt 9). A local change (the MB-005 input copper, the MB-051
reset qualifier, the 1V2 regulator next to the chipset) must not throw that
route away. `main-route-seed.json` holds every track and via of the last
receipt-bound routed board (`main-routed.kicad_pcb`: after the SES import and
the post-route repairs, before stitching and zones), one item per line, with
the SHA-256 of the board it came from. `apply()` adds them to the pre-route
board as locked copper, which the DSN hands Freerouting as fixed wiring, so
the router only lays what is left:

  - every item inside a rip-up box, or on a rip-up net, is dropped;
  - an item already on the board (the source's own pre-routing, the
    fan-out) is not added twice;
  - an item that would touch a pad or new copper of another net, or end on
    a pad of another net, is dropped (a part that moved, a pad whose net
    changed).

The board's final KiCad DRC and connectivity checks remain the authority.

    python3 hw/boards/main_seed.py extract <main-routed.kicad_pcb> [seed.json]
"""

import hashlib
import json
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
SEED = os.path.join(HERE, "main-route-seed.json")
CLEARANCE_NM = 200_000            # vs changed pads and new copper; the DRC checks the real rules


def extract(pcb, out=SEED):
    import pcbnew
    board = pcbnew.LoadBoard(pcb)
    tracks = board.Tracks()
    lines = []
    for i in range(len(tracks)):
        t = tracks[i].Cast()
        if t.Type() == pcbnew.PCB_VIA_T:
            p = t.GetPosition()
            lines.append(["via", t.GetNetname(), p.x, p.y, t.GetWidth(pcbnew.F_Cu), t.GetDrillValue()])
        elif t.Type() == pcbnew.PCB_TRACE_T:
            a, b = t.GetStart(), t.GetEnd()
            lines.append(["track", t.GetNetname(), board.GetLayerName(t.GetLayer()), a.x, a.y, b.x, b.y,
                          t.GetWidth()])
        else:
            raise ValueError("unsupported routed item %s" % t.GetClass())
    for fp in board.GetFootprints():
        p = fp.GetPosition()
        lines.append(["footprint", fp.GetReference(), p.x, p.y, round(fp.GetOrientationDegrees(), 3),
                      sorted([q.GetNumber(), q.GetNetname()] for q in fp.Pads())])
    lines.sort(key=lambda item: json.dumps(item))
    with open(pcb, "rb") as f:
        digest = hashlib.sha256(f.read()).hexdigest()
    with open(out, "w") as f:
        f.write(json.dumps({"source": os.path.basename(pcb), "source_sha256": digest,
                            "items": len(lines)}) + "\n")
        for item in lines:
            f.write(json.dumps(item, separators=(",", ":")) + "\n")
    return len(lines), digest


def load(path=SEED):
    with open(path) as f:
        head = json.loads(f.readline())
        items = [json.loads(line) for line in f if line.strip()]
    if len(items) != head["items"]:
        raise ValueError("route seed truncated: %d of %d items" % (len(items), head["items"]))
    return head, items


def placements(path=SEED):
    """{ref: (x, y, rot)} in mm: the placement the seed was routed on."""
    _, items = load(path)
    return {i[1]: (round(i[2] / 1e6, 4), round(i[3] / 1e6, 4), i[4]) for i in items if i[0] == "footprint"}


def _seg_dist(px, py, ax, ay, bx, by):
    """Distance (vectorized over a..b arrays) from point p to segments a-b."""
    dx, dy = bx - ax, by - ay
    sq = dx * dx + dy * dy
    t = np.where(sq > 0, np.clip(((px - ax) * dx + (py - ay) * dy) / np.where(sq > 0, sq, 1), 0, 1), 0)
    return np.hypot(px - ax - t * dx, py - ay - t * dy)


def _samples(item):
    if item[0] == "via":
        return [(item[2], item[3])], item[4] / 2
    ax, ay, bx, by = item[3:7]
    n = max(1, int(math.hypot(bx - ax, by - ay) / 100_000))
    return [(ax + (bx - ax) * k / n, ay + (by - ay) * k / n) for k in range(n + 1)], item[7] / 2


def _in_box(item, boxes):
    """Any part of the item inside a box: (x0, y0, x1, y1[, layer name]) in nm;
    a box with a layer takes only that layer's tracks (and every via, which
    crosses every layer)."""
    pts, half = _samples(item)
    for box in boxes:
        x0, y0, x1, y1 = box[:4]
        if len(box) > 4 and item[0] == "track" and item[2] != box[4]:
            continue
        if any(x0 - half <= x <= x1 + half and y0 - half <= y <= y1 + half for x, y in pts):
            return True
    return False


def apply(board, boxes_mm, ripup_nets=(), path=SEED):
    """Add the seed to `board` (pcbnew), locked. Returns (added, dropped by
    reason) for the build log."""
    import pcbnew
    mm = pcbnew.FromMM
    boxes = [tuple(mm(v) for v in b[:4]) + tuple(b[4:]) for b in boxes_mm]
    _, items = load(path)
    placed = {i[1]: i for i in items if i[0] == "footprint"}
    items = [i for i in items if i[0] != "footprint"]
    seeded_t = {(i[1], i[2], *i[3:7]) for i in items if i[0] == "track"}
    seeded_v = {(i[1], i[2], i[3]) for i in items if i[0] == "via"}
    layer_id = {board.GetLayerName(l): l for l in board.GetEnabledLayers().CuStack()}
    nets = board.GetNetsByName()

    # what is on the board already: tracks by (net, layer), vias, pads
    tracks = board.Tracks()
    have_t, have_v = set(), set()
    segs = {l: [] for l in layer_id.values()}          # other-net checks, per layer
    vias = []
    for i in range(len(tracks)):
        t = tracks[i].Cast()
        if t.Type() == pcbnew.PCB_VIA_T:
            p = t.GetPosition()
            have_v.add((t.GetNetname(), p.x, p.y))
            if (t.GetNetname(), p.x, p.y) not in seeded_v:            # new copper only
                vias.append((t.GetNetname(), p.x, p.y, t.GetWidth(pcbnew.F_Cu) / 2))
        elif t.Type() == pcbnew.PCB_TRACE_T:
            a, b = t.GetStart(), t.GetEnd()
            key = (t.GetNetname(), t.GetLayer())
            have_t.add(key + (a.x, a.y, b.x, b.y))
            have_t.add(key + (b.x, b.y, a.x, a.y))
            name = board.GetLayerName(t.GetLayer())
            if not ({(t.GetNetname(), name, a.x, a.y, b.x, b.y), (t.GetNetname(), name, b.x, b.y, a.x, a.y)}
                    & seeded_t):
                segs[t.GetLayer()].append((t.GetNetname(), a.x, a.y, b.x, b.y, t.GetWidth() / 2))
    pads = []
    for fp in board.GetFootprints():
        old = placed.get(fp.GetReference())
        pos = fp.GetPosition()
        if old and old[2:5] == [pos.x, pos.y, round(fp.GetOrientationDegrees(), 3)] and \
                old[5] == sorted([q.GetNumber(), q.GetNetname()] for q in fp.Pads()):
            continue                                   # unchanged: the seed was clean against it
        for p in fp.Pads():
            bb = p.GetBoundingBox()
            on = [l for l in layer_id.values() if p.IsOnLayer(l)]
            pads.append((p.GetNetname(), bb.GetLeft(), bb.GetTop(), bb.GetRight(), bb.GetBottom(), on, p))

    def arrays(rows):
        if not rows:
            return None
        names = np.array([r[0] for r in rows], dtype=object)
        return names, np.array([r[1:] for r in rows], dtype=float)
    seg_arr = {l: arrays(v) for l, v in segs.items()}
    via_arr = arrays(vias)

    def conflicts(net, layers, pts, half):
        for x, y in pts:
            for l in layers:
                arr = seg_arr.get(l)
                if arr is not None:
                    names, g = arr
                    d = _seg_dist(x, y, g[:, 0], g[:, 1], g[:, 2], g[:, 3]) - g[:, 4] - half
                    if ((d < CLEARANCE_NM) & (names != net)).any():
                        return True
            if via_arr is not None:
                names, g = via_arr
                d = np.hypot(x - g[:, 0], y - g[:, 1]) - g[:, 2] - half
                if ((d < CLEARANCE_NM) & (names != net)).any():
                    return True
            for pnet, x0, y0, x1, y1, on, _ in pads:
                if pnet != net and set(on) & set(layers):
                    dx = max(x0 - x, 0, x - x1)
                    dy = max(y0 - y, 0, y - y1)
                    if math.hypot(dx, dy) - half < CLEARANCE_NM:
                        return True
        return False

    added, dropped = 0, {"box": 0, "net": 0, "duplicate": 0, "conflict": 0, "orphan": 0}
    keep = []
    for item in items:
        net = item[1]
        if net in ripup_nets or net not in nets:
            dropped["net"] += 1
            continue
        if _in_box(item, boxes):
            dropped["box"] += 1
            continue
        pts, half = _samples(item)
        if item[0] == "via":
            if (net, item[2], item[3]) in have_v:
                dropped["duplicate"] += 1
                continue
            layers = list(layer_id.values())
        else:
            layer = layer_id[item[2]]
            if (net, layer) + tuple(item[3:7]) in have_t:
                dropped["duplicate"] += 1
                continue
            layers = [layer]
        if conflicts(net, layers, pts, half):
            dropped["conflict"] += 1
            continue
        keep.append(item)

    # A kept piece that now reaches no pad and no copper of the new board
    # (the stub of a part that moved, a fan-out via of a pad now elsewhere)
    # would only be dangling copper: drop it.
    anchors = {}
    for fp in board.GetFootprints():
        for p in fp.Pads():
            anchors.setdefault(p.GetNetname(), []).append(("pad", p))
    for i in range(len(tracks)):
        t = tracks[i].Cast()
        if t.Type() == pcbnew.PCB_VIA_T:
            anchors.setdefault(t.GetNetname(), []).append(("via", t.GetPosition().x, t.GetPosition().y,
                                                           t.GetWidth(pcbnew.F_Cu) / 2))
        elif t.Type() == pcbnew.PCB_TRACE_T:
            a, b = t.GetStart(), t.GetEnd()
            anchors.setdefault(t.GetNetname(), []).append(("track", t.GetLayer(), a.x, a.y, b.x, b.y,
                                                           t.GetWidth() / 2))

    def ends(item):
        if item[0] == "via":
            return [(None, item[2], item[3], item[4] / 2)]
        layer = layer_id[item[2]]
        return [(layer, item[3], item[4], item[7] / 2), (layer, item[5], item[6], item[7] / 2)]

    def touches(item, other):
        """Copper of one net meeting: an end of one on the other."""
        for layer, x, y, r in ends(item):
            if other[0] == "via" and (layer is None or True):
                if math.hypot(x - other[2], y - other[3]) <= r + other[4] / 2 + 1:
                    return True
            elif other[0] == "track" and (layer is None or layer_id[other[2]] == layer):
                if _seg_dist(x, y, other[3], other[4], other[5], other[6]) <= r + other[7] / 2 + 1:
                    return True
        for layer, x, y, r in ends(other):
            if item[0] == "via":
                if math.hypot(x - item[2], y - item[3]) <= r + item[4] / 2 + 1:
                    return True
            elif layer is None or layer_id[item[2]] == layer:
                if _seg_dist(x, y, item[3], item[4], item[5], item[6]) <= r + item[7] / 2 + 1:
                    return True
        return False

    def anchored(item, net):
        for a in anchors.get(net, ()):
            if a[0] == "pad":
                p = a[1]
                for layer, x, y, r in ends(item):
                    if (layer is None or p.IsOnLayer(layer)) and p.HitTest(pcbnew.VECTOR2I(int(x), int(y)), int(r)):
                        return True
            elif a[0] == "via":
                for layer, x, y, r in ends(item):
                    if math.hypot(x - a[1], y - a[2]) <= r + a[3] + 1:
                        return True
            else:
                for layer, x, y, r in ends(item):
                    if (layer is None or layer == a[1]) and _seg_dist(x, y, a[2], a[3], a[4], a[5]) <= r + a[6] + 1:
                        return True
        return False

    by_net = {}
    for k, item in enumerate(keep):
        by_net.setdefault(item[1], []).append(k)
    live = set()
    for net, ks in by_net.items():
        cell = {}
        for k in ks:
            for _, x, y, _ in ends(keep[k]):
                cell.setdefault((int(x // 1_000_000), int(y // 1_000_000)), set()).add(k)
            item = keep[k]
            if item[0] == "track":                   # a long track: its body too (a tap on it)
                n = max(1, int(math.hypot(item[5] - item[3], item[6] - item[4]) / 500_000))
                for f in range(1, n):
                    x = item[3] + (item[5] - item[3]) * f / n
                    y = item[4] + (item[6] - item[4]) * f / n
                    cell.setdefault((int(x // 1_000_000), int(y // 1_000_000)), set()).add(k)
        todo = [k for k in ks if anchored(keep[k], net)]
        live.update(todo)
        while todo:
            k = todo.pop()
            near = set()
            item = keep[k]
            if item[0] == "via":
                span = [(item[2], item[3])]
            else:
                n = max(1, int(math.hypot(item[5] - item[3], item[6] - item[4]) / 500_000))
                span = [(item[3] + (item[5] - item[3]) * f / n, item[4] + (item[6] - item[4]) * f / n)
                        for f in range(n + 1)]
            for x, y in span:
                cx, cy = int(x // 1_000_000), int(y // 1_000_000)
                for dx in (-1, 0, 1):
                    for dy in (-1, 0, 1):
                        near |= cell.get((cx + dx, cy + dy), set())
            for j in near - live:
                if touches(item, keep[j]):
                    live.add(j)
                    todo.append(j)
    for k, item in enumerate(keep):
        if k not in live:
            dropped["orphan"] += 1
            continue
        net = item[1]
        if item[0] == "via":
            v = pcbnew.PCB_VIA(board)
            v.SetPosition(pcbnew.VECTOR2I(int(item[2]), int(item[3])))
            v.SetWidth(int(item[4]))
            v.SetDrill(int(item[5]))
            v.SetNet(nets[net])
            v.SetLocked(True)
            board.Add(v)
        else:
            layer = layer_id[item[2]]
            t = pcbnew.PCB_TRACK(board)
            t.SetStart(pcbnew.VECTOR2I(int(item[3]), int(item[4])))
            t.SetEnd(pcbnew.VECTOR2I(int(item[5]), int(item[6])))
            t.SetWidth(int(item[7]))
            t.SetLayer(layer)
            t.SetNet(nets[net])
            t.SetLocked(True)
            board.Add(t)
        added += 1
    return added, dropped


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "extract":
        n, digest = extract(sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else SEED)
        print("route seed: %d items from %s (sha256 %s)" % (n, sys.argv[2], digest))
    else:
        sys.exit(__doc__)
