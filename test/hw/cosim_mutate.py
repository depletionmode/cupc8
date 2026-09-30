"""Shared helpers for the routed co-simulation mutation tests.

open_pad(): a private copy of a routed board with every track that lands on
one package pad removed (the pad's copper launch opened).
Boards: the canonical routed boards passed on the command line, as the
other test/hw/test_cosim_*.py tests take them.
"""
import argparse
import json
import os
import subprocess
from pathlib import Path

import pcbnew

ROOT = Path(__file__).resolve().parents[2]
import sys  # noqa: E402
sys.path.insert(0, str(ROOT / 'hw/tools'))
from kicadgen import dump, find1, parse  # noqa: E402


def board_args(description):
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument('--main-netlist', type=Path, default=ROOT / 'build/hw/main/main.net')
    parser.add_argument('--main-board', type=Path, default=ROOT / 'build/hw/main/main.kicad_pcb')
    parser.add_argument('--card-board-dir', type=Path, default=ROOT / 'build/hw')
    parser.add_argument('--system-board', type=Path,
                        default=ROOT / 'build/hw/system/system-routed.kicad_pcb')
    parser.add_argument('--cpu-board', type=Path, default=ROOT / 'build/hw/cpu/cpu.kicad_pcb')
    parser.add_argument('--top', type=Path, help='a top generated from these boards')
    return parser


def card_boards(args):
    return {card: args.card_board_dir / card / f'{card}.kicad_pcb'
            for card in ('gpu', 'io', 'storage', 'wifi', 'eink')}


def open_pad(source, target, ref, pin, net):
    """Remove every track segment ending on pad ref.pin of `net`; returns the count."""
    board = pcbnew.LoadBoard(str(source))
    pad = next(p for p in board.FindFootprintByReference(ref).Pads() if p.GetNumber() == pin)
    # Fanout may start anywhere inside a pad, including beyond a short centre
    # stub. Removing only the centre stub leaves that physical launch intact.
    # The full track stroke matters too: a rounded track end can touch the pad
    # even when its centre lies just outside it. Use the same zero-clearance
    # native shape collision as routed_connectivity, without a distance halo.
    launch_ids = set()
    tracks = board.Tracks()
    for index in range(len(tracks)):
        track = tracks[index].Cast()
        if (type(track) is pcbnew.PCB_TRACK and track.GetNetname() == net and
                pad.IsOnLayer(track.GetLayer()) and
                track.GetEffectiveShape(track.GetLayer()).Collide(
                    pad.GetEffectiveShape(track.GetLayer()), 0)):
            launch_ids.add(track.m_Uuid.AsString())
    tree = parse(Path(source).read_text())
    matches = [item for item in tree[1:]
               if isinstance(item, list) and item and item[0] == 'segment' and
               find1(item, 'net') and find1(item, 'net')[1] == net and
               find1(item, 'uuid') and find1(item, 'uuid')[1] in launch_ids]
    if not matches:
        raise AssertionError(f'{ref}.{pin} {net}: no launch track to open')
    for item in matches:
        tree.remove(item)
    Path(target).write_text(dump(tree) + '\n')
    return len(matches)


def node_probe(script, top, *args, env=None):
    """Run a test/hw/*.mjs probe against `top`; returns its last JSON line."""
    environment = dict(os.environ, CUPC8_COSIM_TOP=str(Path(top).resolve()), **(env or {}))
    output = subprocess.check_output(['node', str(ROOT / 'test/hw' / script), *args],
                                     cwd=ROOT, env=environment, text=True)
    return json.loads(output.strip().splitlines()[-1])
