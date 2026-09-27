#!/usr/bin/env python3
"""Sandboxed diagnostic replay of one completed main Freerouting SES.

Run only after route-N.ses exists and its router has completed. All PCB writes
go to --out; --build is read-only. This deliberately creates no evidence
receipt and cannot mark MB-005 or a board gate passed.
"""

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'hw' / 'boards'), str(ROOT / 'hw' / 'tools')]

import pcbnew
import kicadgen as kg
import main

EXPECTED_PREROUTE_SHA256 = '71e33e9f197487dc417f5a0e2bd47bb10e12ab347ce5d8bbf29493814e388e61'
POURS = ('/GND', '/+3V3')
# main.prepare returns the eFuse, standby, SPI nCS6, and +5V escape nets.
ESCAPES = ('/VBUS_F', '/5V_SYS', '/PWR_EN', '/SPI_nCS6_SRC', '/+5V')
POWER = {'/VBUS', '/VBUS_F', '/5V_SYS', '/+5V', '/GND', '/+3V3', '/+1V2',
         '/3V3_BUCK', '/1V2_LDO', '/3V3_STBY'}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def copy_verified(src, dst):
    before = digest(src)
    shutil.copy2(src, dst)
    after = digest(src)
    if before != after or digest(dst) != before:
        raise RuntimeError(f'input changed while copying: {src}')
    return before


def replay_import(board, ses, salt):
    """The inner-net retention and SES cleanup in kg.autoroute, without a router."""
    tracks = board.Tracks()
    items = [tracks[i].Cast() for i in range(len(tracks))]
    held = {t.GetNetname() for t in items
            if t.Type() == pcbnew.PCB_TRACE_T and t.GetLayer() not in (pcbnew.F_Cu, pcbnew.B_Cu)}
    inner = [(t.Type() == pcbnew.PCB_VIA_T,
              pcbnew.VECTOR2I(t.GetStart().x, t.GetStart().y),
              pcbnew.VECTOR2I(t.GetEnd().x, t.GetEnd().y),
              t.GetWidth(pcbnew.F_Cu) if t.Type() == pcbnew.PCB_VIA_T else t.GetWidth(),
              t.GetLayer(), t.GetNet(),
              t.GetDrillValue() if t.Type() == pcbnew.PCB_VIA_T else 0)
             for t in items if t.GetNetname() in held]
    kg.stable_uuids(board, salt)
    if not pcbnew.ImportSpecctraSES(board, str(ses)):
        raise RuntimeError('SES import failed')
    tracks = board.Tracks()
    have = set()
    for t in [tracks[i] for i in range(len(tracks)) if tracks[i].GetNetname() in held]:
        via = t.Type() == pcbnew.PCB_VIA_T
        have.add((via, t.GetStart().x, t.GetStart().y) +
                 (() if via else (t.GetEnd().x, t.GetEnd().y, t.GetLayer())))
    restored = 0
    for is_via, start, end, width, layer, net, drill in inner:
        if (is_via, start.x, start.y) + (() if is_via else (end.x, end.y, layer)) in have:
            continue
        if is_via:
            t = pcbnew.PCB_VIA(board)
            t.SetPosition(start)
            t.SetDrill(drill)
        else:
            t = pcbnew.PCB_TRACK(board)
            t.SetStart(start)
            t.SetEnd(end)
            t.SetLayer(layer)
        t.SetWidth(width)
        t.SetNet(net)
        t.SetLocked(True)
        board.Add(t)
        restored += 1
    removed = kg.remove_dangling(board, POURS + ESCAPES)
    tracks = board.Tracks()
    resized = 0
    for v in [tracks[i].Cast() for i in range(len(tracks)) if tracks[i].Type() == pcbnew.PCB_VIA_T]:
        if v.GetWidth(pcbnew.F_Cu) - v.GetDrillValue() < pcbnew.FromMM(0.3):
            v.SetDrill(v.GetWidth(pcbnew.F_Cu) - pcbnew.FromMM(0.3))
            resized += 1
    joined = kg.join_track_ends_to_vias(board)
    return {'held_inner_nets': sorted(held), 'restored_items': restored,
            'removed_dangling_items': removed, 'reduced_via_drills': resized,
            'joined_via_rims': joined}


def fill(board):
    zs = board.Zones()
    zones = [zs[i] for i in range(len(zs))]
    for z in zones:
        z.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_NEVER)
        if not z.GetIsRuleArea():
            z.SetMinThickness(pcbnew.FromMM(0.3))
    kg.fill_zones(board)
    x0, y0, x1, y1 = main.OUTLINE
    poly = [(x0 + .5, y0 + .5), (x1 - .5, y0 + .5),
            (x1 - .5, y1 - .5), (x0 + .5, y1 - .5)]
    count = kg.stitch(board, '/GND', poly, pitch=3.0)
    for z in zones:
        z.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_ALWAYS)
    kg.fill_zones(board)
    for _ in range(3):
        added = kg.stitch(board, '/GND', poly, fragments=True)
        if not added:
            break
        count += added
        kg.fill_zones(board)
    return count


def drc(board_path, report):
    run = subprocess.run(['kicad-cli', 'pcb', 'drc', '--format', 'json',
                          '--schematic-parity', '--severity-all', '-o',
                          str(report), str(board_path)], capture_output=True, text=True)
    if not report.is_file():
        raise RuntimeError(f'DRC produced no report: {run.stderr[-1000:]}')
    data = json.loads(report.read_text())
    opens = defaultdict(list)
    for item in data.get('unconnected_items', ()):
        descriptions = [i.get('description', '') for i in item.get('items', ())]
        nets = sorted(set(re.findall(r'\[(/[^\]]+)\]', ' '.join(descriptions))))
        for net in nets or ['<unknown>']:
            opens[net].append(descriptions)
    return {'command_exit': run.returncode,
            'violations': dict(Counter(v['type'] for v in data.get('violations', ()))),
            'open_count': len(data.get('unconnected_items', ())),
            'opens_by_net': {net: len(rows) for net, rows in sorted(opens.items())},
            'power_open_details': {net: rows for net, rows in sorted(opens.items()) if net in POWER}}


def main_cli():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--build', type=Path, required=True, help='active root build/hw/main, read-only')
    p.add_argument('--preroute-dir', type=Path, help='saved matching preroute files; defaults to --build')
    p.add_argument('--salt', type=int, required=True, choices=range(10))
    p.add_argument('--out', type=Path, required=True, help='fresh sandbox output directory')
    a = p.parse_args()
    build = a.build.resolve()
    preroute_dir = (a.preroute_dir or a.build).resolve()
    out = a.out.resolve()
    for source in (build, preroute_dir):
        if out == source or source in out.parents or out in source.parents:
            raise RuntimeError('output must be separate from every input directory')
    if out.exists() and any(out.iterdir()):
        raise RuntimeError('output directory must be empty')
    route = build / 'route-parallel' / f'route-{a.salt}'
    ses, dsn, log = (route.with_suffix(ext) for ext in ('.ses', '.dsn', '.log'))
    if not ses.is_file() or not dsn.is_file() or not log.is_file() or not ses.stat().st_size:
        raise RuntimeError('completed SES, matching DSN, and log are required')
    log_text = log.read_text()
    if 'Auto-routing stage completed:' not in log_text:
        raise RuntimeError('router log has no completed auto-routing stage; wait for finished SES')
    preroute = preroute_dir / 'main.kicad_pcb'
    if digest(preroute) != EXPECTED_PREROUTE_SHA256:
        raise RuntimeError('preroute PCB SHA-256 differs from the audited root build')
    out.mkdir(parents=True, exist_ok=True)
    hashes = {}
    for name in ('main.kicad_pcb', 'main.kicad_pro', 'main.kicad_sch', 'main.net'):
        hashes[name] = copy_verified(preroute_dir / name, out / name)
    hashes[dsn.name] = copy_verified(dsn, out / dsn.name)
    hashes[ses.name] = copy_verified(ses, out / ses.name)
    hashes[log.name] = copy_verified(log, out / log.name)
    board = pcbnew.LoadBoard(str(out / 'main.kicad_pcb'))
    kg.stable_uuids(board, a.salt)
    check = out / 'check.dsn'
    if not pcbnew.ExportSpecctraDSN(board, str(check)):
        raise RuntimeError('matching DSN export failed')
    canonical = kg.canonical_dsn(check.read_text(), a.salt)
    if canonical != (out / dsn.name).read_text():
        raise RuntimeError('saved route DSN does not match copied preroute PCB at this salt')
    check.unlink()
    stats = replay_import(board, out / ses.name, a.salt)
    imported = out / 'main-imported.kicad_pcb'
    pcbnew.SaveBoard(str(imported), board)
    stats['escaped_open_before_finish'] = kg.open_escapes(board, ESCAPES)
    try:
        main._finish_route(board)
        stats['finish_route'] = 'applied'
    except (RuntimeError, ValueError) as error:
        stats['finish_route'] = f'guard failed: {error}'
        board = pcbnew.LoadBoard(str(imported))
    stats['escaped_open_after_finish'] = kg.open_escapes(board, ESCAPES)
    routed = out / 'main-routed-salvage.kicad_pcb'
    pcbnew.SaveBoard(str(routed), board)
    stats['pre_fill_drc'] = drc(routed, out / 'drc-routed-salvage.json')
    stats['stitch_vias'] = fill(board)
    final = out / 'main-filled-salvage.kicad_pcb'
    pcbnew.SaveBoard(str(final), board)
    stats['filled_drc'] = drc(final, out / 'drc-filled-salvage.json')
    stats['input_hashes'] = hashes
    stats['salt'] = a.salt
    stats['note'] = 'diagnostic replay only; no board evidence receipt or MB-005 closure'
    (out / 'summary.json').write_text(json.dumps(stats, indent=2) + '\n')
    print(json.dumps(stats, indent=2))


if __name__ == '__main__':
    main_cli()
