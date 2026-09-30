#!/usr/bin/env python3
"""Source-bound independent plotted silkscreen glyph-height report.

The review report lives outside the receipt-owned board directory. It is
created only after validating that receipt and comparing all Gerber geometry
against a fresh export of its saved PCB.
"""
import argparse
import json
from pathlib import Path

import pcbnew

import boardevidence
import fabcheck
import silk_glyph_coverage


SILK_LAYERS = {pcbnew.F_SilkS: 'F.Silkscreen',
               pcbnew.B_SilkS: 'B.Silkscreen'}
FAB_MIN_HEIGHT_MM = 0.8


def inventory(board):
    """Return a complete source inventory of visible silk text or fail closed."""
    minimum = board.GetDesignSettings().m_MinSilkTextHeight
    if minimum < pcbnew.FromMM(FAB_MIN_HEIGHT_MM):
        raise ValueError('board minimum silk text height is below %.3f mm fab rule' %
                         FAB_MIN_HEIGHT_MM)
    items = []
    seen = set()

    def add(item, kind, owner=None):
        if item.GetLayer() not in SILK_LAYERS or not item.IsVisible():
            return
        uuid = item.m_Uuid.AsString()
        if not uuid or uuid in seen:
            raise ValueError('missing or duplicate silkscreen text UUID: ' + uuid)
        seen.add(uuid)
        height = item.GetTextSize().y
        if height < minimum:
            raise ValueError('%s %s: nominal silk text height %.6f mm < %.6f mm' %
                             (kind, uuid, pcbnew.ToMM(height), pcbnew.ToMM(minimum)))
        items.append(dict(uuid=uuid, kind=kind, owner=owner, visible=True,
                          layer=SILK_LAYERS[item.GetLayer()], literal=item.GetText(),
                          shown_text=item.GetShownText(False),
                          nominal_height_mm=pcbnew.ToMM(height),
                          nominal_width_mm=pcbnew.ToMM(item.GetTextSize().x),
                          stroke_mm=pcbnew.ToMM(item.GetTextThickness())))

    drawings = board.Drawings()
    for n in range(len(drawings)):
        item = drawings[n].Cast()
        if item.GetLayer() in SILK_LAYERS and item.Type() == pcbnew.PCB_TEXT_T:
            add(item, 'board_text')
        elif item.GetLayer() in SILK_LAYERS and hasattr(item, 'GetTextSize'):
            raise ValueError('unsupported board text-like item on silk: ' + item.GetClass())
    for footprint in board.GetFootprints():
        owner = footprint.GetReference()
        add(footprint.Reference(), 'reference', owner)
        add(footprint.Value(), 'value', owner)
        graphics = footprint.GraphicalItems()
        for n in range(len(graphics)):
            item = graphics[n].Cast()
            if item.GetLayer() in SILK_LAYERS and item.Type() == pcbnew.PCB_TEXT_T:
                add(item, 'footprint_text', owner)
            elif item.GetLayer() in SILK_LAYERS and hasattr(item, 'GetTextSize'):
                raise ValueError('unsupported footprint text-like item on silk: ' + item.GetClass())
    return pcbnew.ToMM(minimum), sorted(items, key=lambda item: item['uuid'])


def audit(out, report):
    out, report = Path(out).resolve(), Path(report).resolve()
    if report.is_relative_to(out):
        raise ValueError('text review report must be outside receipt-owned board output')
    evidence = boardevidence.validate(out.name, out)
    board, layer_count = fabcheck.export_parity(out, out / 'fab')
    minimum, items = inventory(board)
    silk = {side: out / 'fab' / (out.name + '-' + side + '_Silkscreen.' + extension)
            for side, extension in (('F', 'gto'), ('B', 'gbo'))}
    if any(not path.is_file() for path in silk.values()):
        raise ValueError('front and back plotted silkscreen layers required')
    glyphs = silk_glyph_coverage.certify(board, silk.values())
    payload = dict(schema=2, board=out.name, review_status='passed',
                   conclusion='source-bound independent plotted glyph heights pass',
                   plotted_glyph_proof=glyphs,
                   minimum_height_mm=minimum, count=len(items), texts=items,
                   binding=dict(receipt_sha256=boardevidence.digest(out / 'evidence.json'),
                                pcb_sha256=boardevidence.digest(out / (out.name + '.kicad_pcb')),
                                gerber_sha256={side: boardevidence.digest(path)
                                               for side, path in silk.items()},
                                parity_layer_count=layer_count,
                                receipt_version=evidence['version']))
    temporary = report.with_name(report.name + '.tmp')
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + '\n')
    temporary.replace(report)
    return payload


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('board_output', type=Path)
    parser.add_argument('--output', type=Path, required=True,
                        help='review JSON outside receipt-owned board output')
    options = parser.parse_args()
    result = audit(options.board_output, options.output)
    print('%s: %d visible silk text objects; independent plotted heights pass' %
          (result['board'], result['count']))
