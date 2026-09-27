#!/usr/bin/env python3
"""Report plotted fabrication rules separately so one failure cannot hide others.

This diagnostic does not replace ``boardcheck.py <board> fab`` or close its
human CPL review and unsupported filled-geometry/text checks.
"""

import hashlib
import json
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'hw/tools'))
import pcbnew
import boardevidence
import fabcheck
import gerberdrc

if len(sys.argv) < 2:
    raise SystemExit('usage: tools/fab_diagnostics.py BOARD [BOARD ...]')

failed = False
for name in sys.argv[1:]:
    out = ROOT / 'build/hw' / name
    boardevidence.validate(name, out)
    fab = out / 'fab'
    results = {}
    def run(label, fn):
        try:
            value = fn()
            results[label] = {'ok': True, 'count': value if isinstance(value, int) else None}
        except Exception as exc:
            results[label] = {'ok': False, 'error': str(exc)}
    board, layers = fabcheck.export_parity(out, fab)
    holes, cuts, npth = fabcheck.check_drills(board, fab, return_hits=True)
    run('drill_spacing', lambda: fabcheck.check_drill_spacing(cuts, pcbnew.ToMM(board.GetDesignSettings().m_HoleToHoleMin)))
    copper = sorted(p for p in fab.iterdir() if p.suffix.lower() in ('.gtl', '.gbl', '.g1', '.g2', '.g3', '.g4'))
    outline = next(fab.glob('*.gm1'))
    masks = {p.suffix.lower(): p for p in fab.iterdir() if p.suffix.lower() in ('.gts', '.gbs')}
    surfaces = {p.suffix.lower(): p for p in copper if p.suffix.lower() in ('.gtl', '.gbl')}
    paste = {p.suffix.lower(): p for p in fab.iterdir() if p.suffix.lower() in ('.gtp', '.gbp')}
    silk = {p.suffix.lower(): p for p in fab.iterdir() if p.suffix.lower() in ('.gto', '.gbo')}
    settings = board.GetDesignSettings()
    run('copper_clearance_width', lambda: gerberdrc.check_clearance(copper, pcbnew.ToMM(settings.m_MinClearance), pcbnew.ToMM(settings.m_TrackMinWidth)))
    run('via_annular', lambda: gerberdrc.check_via_annular(board, copper, pcbnew.ToMM(settings.m_ViasMinAnnularWidth)))
    run('pth_annular', lambda: gerberdrc.check_pth_annular(board, copper, .20))
    run('copper_edge', lambda: gerberdrc.check_edge(copper, outline, pcbnew.ToMM(settings.m_CopperEdgeClearance)))
    run('hole_clearance', lambda: gerberdrc.check_holes(cuts, npth, copper, outline, pcbnew.ToMM(settings.m_HoleClearance), 1.0))
    run('mask_web', lambda: gerberdrc.check_mask(masks.values(), pcbnew.ToMM(settings.m_SolderMaskMinWidth)))
    run('mask_alignment', lambda: gerberdrc.check_mask_alignment(surfaces['.gtl'], masks['.gts']) + gerberdrc.check_mask_alignment(surfaces['.gbl'], masks['.gbs']))
    run('paste_registration', lambda: gerberdrc.check_paste_registration(surfaces['.gtl'], masks['.gts'], paste['.gtp']) + gerberdrc.check_paste_registration(surfaces['.gbl'], masks['.gbs'], paste['.gbp']))
    run('silk_clearance', lambda: gerberdrc.check_silk_clearance(silk['.gto'], masks['.gts'], .15, .15) + gerberdrc.check_silk_clearance(silk['.gbo'], masks['.gbs'], .15, .15))
    failed |= any(not item['ok'] for item in results.values())
    receipt_sha = hashlib.sha256((out / 'evidence.json').read_bytes()).hexdigest()
    print(json.dumps({'board': name, 'receipt_sha256': receipt_sha,
                      'layers': layers, 'drills': holes, 'results': results}), flush=True)
sys.exit(int(failed))
