"""Round plotted copper fill tips while preserving every routed conductor.

This is a source transformation, before the saved PCB's DRC and export.
It does not waive any plotted feature rule or qualify power/reset/SI.
"""
import math
import pcbnew


def routed_inventory(board):
    tracks = board.Tracks()
    wire = []
    for index in range(len(tracks)):
        item = tracks[index]
        a, b = item.GetStart(), item.GetEnd()
        if item.Type() == pcbnew.PCB_TRACE_T:
            extra = (item.GetWidth(),)
        elif item.Type() == pcbnew.PCB_VIA_T:
            via = pcbnew.Cast_to_PCB_VIA(item)
            extra = (via.GetWidth(pcbnew.F_Cu), via.GetWidth(pcbnew.B_Cu), via.GetDrillValue())
        else:
            raise ValueError('unsupported routed copper type in fill repair')
        wire.append((int(item.Type()), item.GetNetname(), a.x, a.y, b.x, b.y,
                     item.GetLayerSet().FmtHex(), bool(item.IsLocked()), extra))
    pads = []
    for footprint in board.GetFootprints():
        for pad in footprint.Pads():
            pos, size, drill = pad.GetPosition(), pad.GetSize(), pad.GetDrillSize()
            pads.append((footprint.GetReference(), pad.GetNumber(), pad.GetNetname(),
                         pos.x, pos.y, size.x, size.y, drill.x, drill.y,
                         int(pad.GetShape()), pad.GetOrientationDegrees(), pad.GetLayerSet().FmtHex()))
    return sorted(wire), sorted(pads)


def remove_rounding_islands(polys, contacts, *, can_prove_single_zone,
                            maximum_area_nm2=100):
    """Delete only nanometre fragments with no exact copper contact.

    contacts contains the bounding box and actual shape of every same-net
    pad/track/via on the layer. Other same-net zone fills require a graph
    proof that this helper does not supply; in that case it fails closed.
    """
    removed = []
    for index in range(polys.OutlineCount()):
        fragment = polys.UnitSet(index)
        box = fragment.BBox()
        if any(box.Intersects(bound) and fragment.Collide(shape)
               for bound, shape in contacts):
            continue
        area = float(fragment.Area())
        if (not can_prove_single_zone or not math.isfinite(area) or area < 0 or
                area > maximum_area_nm2):
            raise ValueError('unanchored filled copper lacks a nanometre-island proof '
                             '(area %.12g nm^2)' % area)
        removed.append((index, area))
    for index, _ in reversed(removed):
        polys.DeletePolygon(index)
    return removed


# Fixed rules and chipset positions for individually tested source layouts.
_BOARD_GUARDS = {
    'main': (6, .1, 'U7', 'ICE40HX4K-TQ144', (101000000, 49000000)),
    'cpu': (6, .1, 'U1', 'ICE40HX4K-TQ144', (24500000, -31300000)),
    'gpu': (4, .1, 'U1', 'RP2040', (26000000, -16000000)),
    'io': (4, .1, 'U1', 'RP2040', (26500000, -17500000)),
    'wifi': (2, .15, 'U1', 'ESP32-C3-MINI-1U-N4', (41000000, -29000000)),
    'storage': (4, .1, 'U1', 'RP2040', (26000000, -16000000)),
    'eink': (4, .1, 'U1', 'RP2040', (26000000, -16000000)),
    'system': (4, .1, 'U1', 'RP2040', (28000000, 17000000)),
}


def round_main_fills(board):
    return round_board_fills(board, 'main')


def round_board_fills(board, name):
    """Apply the individually qualified board's circular fill opening.

    Native round offsets have 2 nm chord error and keep the 1 nm PCB grid.
    The opening diameter is 1.2 times the fixed minimum feature rule.
    No more than 0.1% of any fill's area may be removed. Actual board DRC,
    connectivity, plotted neck proof, and routed electrical checks still
    must pass afterward. A refill would undo this source transformation.
    """
    if name not in _BOARD_GUARDS:
        raise ValueError('unqualified board fill repair')
    layers, minimum, reference, value, position = _BOARD_GUARDS[name]
    chipset = board.FindFootprintByReference(reference)
    if (board.GetCopperLayerCount() != layers or
            board.GetDesignSettings().m_TrackMinWidth != pcbnew.FromMM(minimum) or
            chipset is None or chipset.GetValue() != value or
            (chipset.GetPosition().x, chipset.GetPosition().y) != position):
        raise ValueError('fill repair requires the qualified chipset layout and layer/minimum rules')
    radius = .09 if name == 'wifi' else .06
    before = routed_inventory(board)
    zones = board.Zones()
    copper_layers = (pcbnew.F_Cu, pcbnew.B_Cu, pcbnew.In1_Cu, pcbnew.In2_Cu,
                     pcbnew.In3_Cu, pcbnew.In4_Cu)
    tracks = board.Tracks()
    primitives = [pad for fp in board.GetFootprints() for pad in fp.Pads()]
    primitives.extend(tracks[index] for index in range(len(tracks)))
    contacts_by_net = {}
    changed, audit = [], []
    for index in range(len(zones)):
        zone = zones[index]
        if zone.GetIsRuleArea():
            continue
        for layer in copper_layers:
            if not zone.HasFilledPolysForLayer(layer):
                continue
            polys = zone.GetFilledPolysList(layer).CloneDropTriangulation()
            polys.Unfracture()
            original_area = float(polys.Area())
            if not math.isfinite(original_area) or original_area <= 0:
                raise ValueError('main fill has invalid area')
            polys.Deflate(pcbnew.FromMM(radius), pcbnew.CORNER_STRATEGY_ROUND_ALL_CORNERS, 2)
            polys.Inflate(pcbnew.FromMM(radius), pcbnew.CORNER_STRATEGY_ROUND_ALL_CORNERS, 2)
            # Only GND offsets produced weakly-simple nanometre fragments.
            # Normalize those before testing contacts; keep the qualified
            # supply-plane representation unchanged.
            if zone.GetNetname() == '/GND':
                polys.Fracture()
                polys.Unfracture()
            key = zone.GetNetname(), layer
            if key not in contacts_by_net:
                contacts_by_net[key] = [(item.GetBoundingBox(), item.GetEffectiveShape(layer))
                                        for item in primitives
                                        if item.GetNetname() == key[0] and item.IsOnLayer(layer)]
            single = sum(not zones[j].GetIsRuleArea() and zones[j].GetNetname() == key[0] and
                         zones[j].HasFilledPolysForLayer(layer) for j in range(len(zones))) == 1
            removed = remove_rounding_islands(polys, contacts_by_net[key],
                                             can_prove_single_zone=single)
            area = float(polys.Area())
            if not math.isfinite(area) or area <= 0 or area < original_area * .999 or area > original_area * 1.000001:
                raise ValueError('main fill opening changed more copper than its qualified bound')
            audit.append(dict(zone=zone.GetZoneName(), net=key[0], layer=board.GetLayerName(layer),
                              before_mm2=original_area / 1e12, after_mm2=area / 1e12,
                              removed_unanchored_nm2=[a for _, a in removed]))
            polys.Fracture()
            removed_after_fracture = remove_rounding_islands(
                polys, contacts_by_net[key], can_prove_single_zone=single)
            audit[-1]['removed_unanchored_nm2'].extend(a for _, a in removed_after_fracture)
            final_area = float(polys.Area())
            if (not math.isfinite(final_area) or final_area <= 0 or
                    final_area < original_area * .999 or final_area > original_area * 1.000001):
                raise ValueError('final fill area exceeds its qualified bound')
            audit[-1]['after_mm2'] = final_area / 1e12
            changed.append((zone, layer, polys))
    if routed_inventory(board) != before:
        raise ValueError('fill preparation altered tracks, vias or pads')
    for zone, layer, polys in changed:
        zone.SetFilledPolysList(layer, polys)
    if routed_inventory(board) != before:
        raise ValueError('fill installation altered tracks, vias or pads')
    return audit
