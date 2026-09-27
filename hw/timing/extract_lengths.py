#!/usr/bin/env python3
"""Extract conservative CPU-bus and clock copper lengths from routed KiCad boards.

For each net, sum every straight trace and a full board thickness per via.
This bounds a point-to-point path even when a test point adds a branch. The
main and CPU boards must both be routed; their hashes are recorded so BUS-005
can reject a stale report after either layout changes.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import sys

import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'hw/tools'))
from kicadgen import parse  # noqa: E402


def bus_nets():
    pins = yaml.safe_load((ROOT / 'hw/pins.yaml').read_text())['devices']
    groups = []
    for device in ('chipset', 'cpu_fpga'):
        signals = pins[device]['groups']['cpu_bus']['signals']
        expanded = set()
        for entry in signals:
            if 'width' in entry:
                expanded.update(entry['name'] + str(i) for i in range(entry['width']))
            else:
                expanded.add(entry['name'])
        groups.append(expanded)
    if not groups[0] <= groups[1]:
        raise ValueError('chipset bus signals missing from CPU card pin list')
    return sorted(groups[0])


def copper_lengths(path):
    if not path.is_file():
        raise ValueError('missing routed board: ' + str(path))
    board = parse(path.read_text())
    if board[0] != 'kicad_pcb':
        raise ValueError('not a KiCad board: ' + str(path))
    id_to_name = {entry[1]: entry[2] for entry in board[1:]
                  if isinstance(entry, list) and entry[0] == 'net' and len(entry) == 3}
    general = next((entry for entry in board[1:] if isinstance(entry, list) and entry[0] == 'general'), None)
    thickness = 1.6
    if general:
        for entry in general[1:]:
            if isinstance(entry, list) and entry[0] == 'thickness':
                thickness = float(entry[1])
    lengths = {}
    for entry in board[1:]:
        if not isinstance(entry, list) or entry[0] not in ('segment', 'via'):
            continue
        fields = {item[0]: item[1:] for item in entry[1:] if isinstance(item, list)}
        net = id_to_name.get(fields['net'][0], fields['net'][0]).lstrip('/')
        if not net or net == '0':
            raise ValueError('unassigned copper in ' + str(path))
        if entry[0] == 'segment':
            a, b = ([float(x) for x in fields[name]] for name in ('start', 'end'))
            length = math.dist(a, b)
        else:
            length = thickness
        lengths[net] = lengths.get(net, 0) + length
    if not lengths:
        raise ValueError('no routed copper in ' + str(path))
    return lengths


def extract(main, cpu):
    a, b = copper_lengths(main), copper_lengths(cpu)
    missing = [name for name in bus_nets() if a.get(name, 0) <= 0 or b.get(name, 0) <= 0]
    if missing:
        raise ValueError('CPU bus lacks routed copper on both boards: ' + ', '.join(missing))
    if a.get('CLK12', 0) <= 0 or a.get('CPU_CLK', 0) <= 0 or b.get('CPU_CLK', 0) <= 0:
        raise ValueError('CLK12/CPU_CLK lacks routed copper')
    return {
        'version': 1,
        'sources': {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
                    for path in (main, cpu)},
        'bus_mm': {name: round(a[name] + b[name], 4) for name in bus_nets()},
        'clk_diff_mm': round(abs(a['CLK12'] - a['CPU_CLK'] - b['CPU_CLK']), 4),
        'conservative_method': 'sum of all trace lengths plus full board thickness per via',
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--main', type=Path, default=ROOT / 'build/hw/main/main.kicad_pcb')
    parser.add_argument('--cpu', type=Path, default=ROOT / 'build/hw/cpu/cpu.kicad_pcb')
    parser.add_argument('--output', type=Path, default=ROOT / 'build/hw/cpubus_lengths.json')
    args = parser.parse_args()
    payload = extract(args.main.resolve(), args.cpu.resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2) + '\n')
    print('BUS-005: extracted %d bus nets, maximum %.1f mm, clock difference %.1f mm' %
          (len(payload['bus_mm']), max(payload['bus_mm'].values()), payload['clk_diff_mm']))


if __name__ == '__main__':
    main()
