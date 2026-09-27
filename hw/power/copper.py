#!/usr/bin/env python3
"""Nominal DC resistance model for the main board's 5 V distribution.

Each routed track is a resistor; parallel tracks and vias form a graph.
The lowest-resistance single path bounds that graph's equivalent resistance.
Pad copper is idealized as zero resistance, pours are omitted, and each
through via costs a full-board barrel resistance even for a shorter hop.
Those approximations push in different directions, so the result is an
estimate rather than a certified upper bound for physical copper. It also
does not certify conductor temperature.
"""

from collections import defaultdict
import heapq
import math
import sys


# JLC06161H-3313: 1 oz outer, 0.5 oz inner. TI SLYW038D p. 72 uses
# 17e-6 ohm mm for copper and 0.0348 mm per oz.
RHO = 17e-6
REFERENCE_C = 20.0
COPPER_ALPHA_PER_C = 0.00393
THICKNESS = {"outer": 0.0348, "inner": 0.0174}
VIA_PLATING = 0.025  # mm; conservatively use one full 1.6 mm barrel per hop
BOARD_THICKNESS = 1.6
TRACE_WIDTH_FACTOR = 1.0


def pad(board, ref, number):
    fp = board.FindFootprintByReference(ref)
    if fp is None:
        raise ValueError("missing footprint " + ref)
    hits = [p for p in fp.Pads() if p.GetNumber() == str(number)]
    if len(hits) != 1:
        raise ValueError("missing/duplicate pad %s:%s" % (ref, number))
    return hits[0]


def network(board, netname):
    import pcbnew

    graph = defaultdict(list)
    tracks = board.Tracks()  # KiCad/Python 3.14: use indexes, not SWIG iteration
    layers = (pcbnew.F_Cu, pcbnew.In1_Cu, pcbnew.In2_Cu,
              pcbnew.In3_Cu, pcbnew.In4_Cu, pcbnew.B_Cu)
    segments, vias = [], []
    points = defaultdict(set)
    for i in range(len(tracks)):
        item = tracks[i]
        if item.GetNetname() != netname:
            continue
        if item.Type() == pcbnew.PCB_TRACE_T:
            a, b = item.GetStart(), item.GetEnd()
            layer = item.GetLayer()
            width = TRACE_WIDTH_FACTOR * pcbnew.ToMM(item.GetWidth())
            segments.append(((a.x, a.y), (b.x, b.y), layer, width))
            points[layer].update(((a.x, a.y), (b.x, b.y)))
        elif item.Type() == pcbnew.PCB_VIA_T:
            via = pcbnew.Cast_to_PCB_VIA(item)
            vias.append(via)
            p = via.GetPosition()
            for layer in layers:
                if via.IsOnLayer(layer):
                    points[layer].add((p.x, p.y))

    def edge(a, b, resistance, width=0, length=0):
        graph[a].append((b, resistance, width, length))
        graph[b].append((a, resistance, width, length))

    # KiCad tracks can meet in the middle of a segment: branch taps and vias
    # are often there, not at an endpoint. Split at every copper overlap.
    for a, b, layer, width in segments:
        dx, dy = b[0] - a[0], b[1] - a[1]
        square = dx * dx + dy * dy
        if square == 0:
            continue
        half_width_nm = width * 1e6 / 2
        split = [(0.0, a), (1.0, b)]
        for x, y in points[layer]:
            t = max(0.0, min(1.0, ((x - a[0]) * dx + (y - a[1]) * dy) / square))
            proj = (round(a[0] + t * dx), round(a[1] + t * dy))
            if math.hypot(x - proj[0], y - proj[1]) <= half_width_nm + 1:
                split.append((t, proj))
                if (x, y) != proj:
                    edge((x, y, layer), (*proj, layer), 0)
        split.sort()
        thickness = THICKNESS["outer" if layer in (pcbnew.F_Cu, pcbnew.B_Cu) else "inner"]
        for (_, p), (_, q) in zip(split, split[1:]):
            length = math.hypot(p[0] - q[0], p[1] - q[1]) / 1e6
            if length:
                edge((*p, layer), (*q, layer), 1000 * RHO * length / (width * thickness), width, length)

    for via in vias:
        d = pcbnew.ToMM(via.GetDrillValue())
        copper_area = math.pi * ((d + 2 * VIA_PLATING) ** 2 - d * d) / 4
        milliohms = 1000 * RHO * BOARD_THICKNESS / copper_area
        p = via.GetPosition()
        active = [layer for layer in layers if via.IsOnLayer(layer)]
        # One common barrel, represented by a hub. A complete graph of all
        # copper layers would invent parallel resistors *inside one via* and
        # understate its resistance when both inner and outer layers carry
        # this net. Each layer-to-hub edge costs half a full barrel, making
        # every two-layer transfer cost one full barrel conservatively.
        hub = (p.x, p.y, None)
        for layer in active:
            edge((p.x, p.y, layer), hub, milliohms / 2)
    return graph


def near_pad(graph, contact):
    import pcbnew

    layers = contact.GetLayerSet()
    hits = []
    for x, y, layer in graph:
        if layer is None:
            continue
        if not layers.Contains(layer):
            continue
        if contact.HitTest(pcbnew.VECTOR2I(x, y)):
            hits.append((x, y, layer))
    if not hits:
        raise ValueError("no routed copper touches net %s pad %s" %
                         (contact.GetNetname(), contact.GetNumber()))
    return hits


def path(board, netname, source, target):
    graph = network(board, netname)
    start = near_pad(graph, pad(board, *source))
    end = set(near_pad(graph, pad(board, *target)))
    dist = {node: 0.0 for node in start}
    heap = [(0.0, node) for node in start]
    heapq.heapify(heap)
    prev = {}
    while heap:
        value, node = heapq.heappop(heap)
        if value > dist[node]:
            continue
        if node in end:
            segments = []
            while node in prev:
                before, width, length = prev[node]
                segments.append((width, length))
                node = before
            return value, segments
        for other, resistance, width, length in graph[node]:
            next_value = value + resistance
            if next_value < dist.get(other, math.inf):
                dist[other] = next_value
                prev[other] = (node, width, length)
                heapq.heappush(heap, (next_value, other))
    raise ValueError("open copper path %s %s to %s" % (netname, source, target))


def effective_resistance(board, netname, source, target):
    """DC resistance of the *track and via* graph, including parallel paths.

    Conductive pads are ideal equipotentials, and copper pours are omitted.
    The result uses nominal thickness and does not include solder joints.
    The solve fixes the source at 1 V and the load at 0 V, then sums current.
    Resistances in ``network`` are milliohms, so the result is milliohms.
    """
    graph = network(board, netname)
    start = near_pad(graph, pad(board, *source))
    end = near_pad(graph, pad(board, *target))
    parent = {}

    def find(node):
        parent.setdefault(node, node)
        while parent[node] != node:
            parent[node] = parent[parent[node]]
            node = parent[node]
        return node

    def join(a, b):
        parent[find(a)] = find(b)

    for group in (start, end):
        for node in group[1:]:
            join(group[0], node)
    for node, edges in graph.items():
        for other, resistance, _, _ in edges:
            if resistance == 0:
                join(node, other)
    source_node, sink_node = find(start[0]), find(end[0])
    if source_node == sink_node:
        return 0.0

    # Build the positive-resistance conductance graph after contracting pads
    # and zero-length copper. Every edge occurs in both adjacency lists.
    conductance = defaultdict(lambda: defaultdict(float))
    for node, edges in graph.items():
        for other, resistance, _, _ in edges:
            if repr(node) >= repr(other) or resistance <= 0:
                continue
            a, b = find(node), find(other)
            if a != b:
                g = 1.0 / resistance
                conductance[a][b] += g
                conductance[b][a] += g
    if source_node not in conductance or sink_node not in conductance:
        raise ValueError("open copper path %s %s to %s" % (netname, source, target))

    # A tiny sparse, Jacobi-preconditioned conjugate-gradient solve avoids a
    # SciPy dependency in the hardware generation environment. Restrict the
    # system to the source's component, which may be only partly routed.
    seen = {source_node}
    stack = [source_node]
    while stack:
        node = stack.pop()
        for other in conductance[node]:
            if other not in seen:
                seen.add(other)
                stack.append(other)
    if sink_node not in seen:
        raise ValueError("open copper path %s %s to %s" % (netname, source, target))
    interior = [node for node in seen if node not in (source_node, sink_node)]
    index = {node: i for i, node in enumerate(interior)}
    diagonal = [sum(conductance[node].values()) for node in interior]
    rhs = [conductance[node].get(source_node, 0.0) for node in interior]

    def matvec(vector):
        return [diagonal[i] * vector[i] - sum(g * vector[index[other]]
                for other, g in conductance[node].items() if other in index)
                for i, node in enumerate(interior)]

    voltage = [0.0] * len(interior)
    residual = rhs[:]
    direction = [r / d for r, d in zip(residual, diagonal)]
    rz = sum(r * p for r, p in zip(residual, direction))
    initial = math.sqrt(sum(r * r for r in rhs))
    for _ in range(max(100, 20 * len(interior))):
        if math.sqrt(sum(r * r for r in residual)) <= 1e-10 * max(initial, 1.0):
            break
        ad = matvec(direction)
        denom = sum(p * a for p, a in zip(direction, ad))
        if denom <= 0:
            raise ValueError("nonpositive copper network")
        alpha = rz / denom
        voltage = [v + alpha * p for v, p in zip(voltage, direction)]
        residual = [r - alpha * a for r, a in zip(residual, ad)]
        rz_next = sum(r * r / d for r, d in zip(residual, diagonal))
        beta = rz_next / rz
        direction = [r / d + beta * p for r, d, p in zip(residual, diagonal, direction)]
        rz = rz_next
    else:
        raise ValueError("copper network solve did not converge")
    potential = {node: voltage[i] for i, node in enumerate(interior)}
    potential[sink_node] = 0.0
    amps_per_millivolt = sum(g * (1.0 - potential[other])
                            for other, g in conductance[source_node].items())
    return 1.0 / amps_per_millivolt


def main():
    import pcbnew

    board = pcbnew.LoadBoard(sys.argv[1] if len(sys.argv) > 1 else "build/hw/main/main-routed.kicad_pcb")
    upstream, up_segments = path(board, "/5V_SYS", ("U2", "6"), ("R4", "1"))
    upstream_parallel = effective_resistance(board, "/5V_SYS", ("U2", "6"), ("R4", "1"))
    print("5V_SYS U2:6 to R4:1: %.2f mOhm parallel-track estimate, %.2f mOhm single-path bound" %
          (upstream_parallel, upstream))
    worst = 0.0
    for n in range(1, 7):
        branch, segments = path(board, "/+5V", ("R4", "2"), ("F%d00" % (n + 1), "1"))
        branch_parallel = effective_resistance(board, "/+5V", ("R4", "2"), ("F%d00" % (n + 1), "1"))
        total = upstream_parallel + branch_parallel
        longest_fine = max((length for width, length in up_segments + segments if 0 < width < 2.8), default=0)
        print("slot %d: %.2f + %.2f = %.2f mOhm parallel-track estimate; "
              "%.2f mOhm single-path bound; longest <2.8 mm trace %.2f mm" %
              (n, upstream_parallel, branch_parallel, total, upstream + branch, longest_fine))
        worst = max(worst, total)
    # The buck's two VIN pads are also on 5V_SYS, downstream of the eFuse
    # but upstream of R4. A long thin spur there would violate the same
    # power-budget assumption even if every slot branch were broad.
    for pin in ("1", "4"):
        buck = effective_resistance(board, "/5V_SYS", ("U2", "6"), ("U3", pin))
        print("buck U3:%s: %.2f mOhm parallel-track estimate" % (pin, buck))
        worst = max(worst, buck)
    # hw/power/design.py R_5VSYS assumes <= 20 mOhm of copper to any slot.
    if worst > 20:
        raise SystemExit("FAIL 5V_SYS track/via resistance >20 mOhm; widen the route")
    threshold_c = REFERENCE_C + (20.0 / worst - 1.0) / COPPER_ALPHA_PER_C
    hot_70 = worst * (1.0 + COPPER_ALPHA_PER_C * (70.0 - REFERENCE_C))
    print("NOMINAL MODEL PASS <=20 mOhm at %.0f C; estimated %.2f mOhm at 70 C; "
          "20 mOhm reached at %.1f C uniform copper" % (REFERENCE_C, hot_70, threshold_c))
    print("THERMAL/TOLERANCE OPEN: at 40 C ambient, only %.1f C conductor rise remains "
          "before 20 mOhm, even before copper-thickness tolerance" % (threshold_c - 40.0))


if __name__ == "__main__":
    main()
