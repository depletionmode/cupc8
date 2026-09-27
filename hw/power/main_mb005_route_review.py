#!/usr/bin/env python3
"""Replay the one red MB-005 placement route into an isolated DRC output.

The input PCB and DSN are pinned to the pre-route experiment. This script
produces diagnostic evidence only; it does not emit a board receipt.
"""

import argparse
from pathlib import Path
import json
import shutil
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'hw/tools'), str(ROOT / 'hw/boards'), str(ROOT / 'hw/power')]

import pcbnew
import kicadgen as kg
import main_ses_salvage as salvage

PCB_SHA = 'd29d7b76c63eaa45260e5ba0abe5ca7bf551d0feb310e6f2fbcece69e9565362'
DSN_SHA = 'c72cbe94baf2465d80f825bb9deb8949e7a77c568cab86e8e27be6c58cf54a53'
SALT = 9


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--preroute', type=Path, required=True)
    p.add_argument('--route', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    a = p.parse_args()
    pre, route, out = a.preroute.resolve(), a.route.resolve(), a.out.resolve()
    if out.exists() or any(out == src or src in out.parents or out in src.parents
                           for src in (pre, route)):
        p.error('output must be a fresh directory separate from both inputs')
    pcb = pre / 'main.kicad_pcb'
    dsn, ses, log = route / f'route-{SALT}.dsn', route / f'route-{SALT}.ses', route / 'freerouting.log'
    if salvage.digest(pcb) != PCB_SHA or salvage.digest(dsn) != DSN_SHA:
        p.error('input PCB or DSN differs from the reviewed source trial')
    if not ses.is_file() or not ses.stat().st_size or not log.is_file():
        p.error('wait for a saved session and final router log')
    if 'Auto-routing stage completed:' not in log.read_text():
        p.error('router did not complete its auto-routing stage')
    out.mkdir(parents=True)
    for name in ('main.kicad_pcb', 'main.kicad_pro', 'main.kicad_sch',
                 'main.net', 'fp-lib-table', 'sym-lib-table'):
        salvage.copy_verified(pre / name, out / name)
    for source in (dsn, ses, log):
        salvage.copy_verified(source, out / source.name)
    board = pcbnew.LoadBoard(str(out / 'main.kicad_pcb'))
    kg.stable_uuids(board, SALT)
    check = out / 'check.dsn'
    if not pcbnew.ExportSpecctraDSN(board, str(check)):
        raise RuntimeError('DSN reproduction export failed')
    generated = kg.canonical_dsn(check.read_text(), SALT)
    # KiCad embeds the export filename in line one; the routed geometry is
    # the exact remainder, checked byte for byte.
    if generated.split('\n', 1)[1] != dsn.read_text().split('\n', 1)[1]:
        raise RuntimeError('SES DSN differs from pinned preroute geometry')
    check.unlink()
    imported = salvage.replay_import(board, out / ses.name, SALT)
    routed = out / 'main-routed-diagnostic.kicad_pcb'
    pcbnew.SaveBoard(str(routed), board)
    preroute_drc = salvage.drc(routed, out / 'drc-routed.json')
    stitches = salvage.fill(board)
    filled = out / 'main-filled-diagnostic.kicad_pcb'
    pcbnew.SaveBoard(str(filled), board)
    filled_drc = salvage.drc(filled, out / 'drc-filled.json')
    summary = {'status': 'red diagnostic, not a board receipt',
               'input_sha256': {'pcb': PCB_SHA, 'dsn': DSN_SHA,
                                'ses': salvage.digest(ses), 'log': salvage.digest(log)},
               'import': imported, 'pre_fill': preroute_drc,
               'stitch_vias': stitches, 'post_fill': filled_drc}
    (out / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
