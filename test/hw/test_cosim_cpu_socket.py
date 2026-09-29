#!/usr/bin/env python3
"""CC-051: the CPU card passes BUS-001..003 through the netlist-modelled socket.

The CPU socket (contact permutation from the main and CPU-card KiCad
netlists, routed copper links for address, data, control, clock and reset)
comes from a hw/cosim/gen_top.py manifest; tools/lockstep.py --socket puts it
between the CPU RTL and tb_cpu_trace's chipset model. Every BUS-001..003
argument set must match sim.nim through it. Swapped address or data contacts,
an open data link and a swapped CPU-card finger in the netlist must be caught.
Receipt validation of the boards is done by the caller, not here.
"""
import argparse
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
BUILD = ROOT / 'build/hw'
BOARDS = ['--main-netlist', BUILD / 'main/main.net', '--card-board-dir', BUILD,
          '--system-board', BUILD / 'system/system-routed.kicad_pcb',
          '--cpu-board', BUILD / 'cpu/cpu.kicad_pcb']

# The catalogue's BUS-001..003 argument sets. BUS-002's monitor is the
# assertion set inside tb_cpu_trace, so it runs through the socket on every
# ghdl run; its mainboard-engine run (tb_mainboard, whose CPU/chipset wiring
# is fixed in VHDL and takes no socket map) is repeated unchanged.
BUS = {
    'BUS-001': [['--waits', '3'], ['--waits', '-1', '--seed', '11']],
    'BUS-003': [['--waits', '-1', '--stall', '200', '--seed', '5'],
                ['--reset-at', '300', '--seed', '6'],
                ['--waits', '-1', '--reset-at', '1000', '--seed', '7']],
}


def lockstep(args, socket=None):
    cmd = [sys.executable, 'tools/lockstep.py', *args]
    if socket:
        cmd += ['--socket', str(socket)]
    r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    tail = r.stdout.strip().splitlines()[-1] if r.stdout.strip() else r.stderr[-500:]
    return r.returncode, tail


def passes(args, socket=None):
    code, tail = lockstep(args, socket)
    ok = code == 0 and ' 0 failed' in tail and not tail.startswith('0 ok')
    print(('ok    ' if ok else 'FAIL  ') + ' '.join(args) + (' --socket' if socket else '') + ': ' + tail,
          flush=True)
    return ok


def mutant(top, directory, name, change):
    data = copy.deepcopy(top)
    change(data['runtime'])
    path = directory / (''.join(c if c.isalnum() else '-' for c in name) + '.json')
    path.write_text(json.dumps(data))
    code, tail = lockstep(['--waits', '3'], path)
    detected = code != 0
    print(('detected ' if detected else 'MISSED   ') + name + ': ' + tail, flush=True)
    return detected


def netlist_swap(directory):
    """Swap two CPU-card address fingers in the card netlist and regenerate."""
    sys.path[:0] = [str(ROOT / 'hw/cosim'), str(ROOT / 'hw/boards'), str(ROOT / 'hw/tools')]
    import gen_top
    from netlist import read
    (directory / 'cards').mkdir()
    cards = gen_top.exported_cards(directory / 'cards')
    cpu = cards['cpu']
    fingers = {net: (ref, pin) for (ref, pin), net in cpu.pins.items() if ref == 'J1'}
    a, b = fingers['/CPU_A2'], fingers['/CPU_A3']
    cpu.pins[a], cpu.pins[b] = '/CPU_A3', '/CPU_A2'
    for net, (old, new) in (('/CPU_A2', (a, b)), ('/CPU_A3', (b, a))):
        cpu.nets[net] = tuple(new if node == old else node for node in cpu.nets[net])
    main_net = BUILD / 'main/main.net'
    try:
        manifest = gen_top.check(
            cards, read(main_net), main_net.with_suffix('.kicad_pcb'),
            {card: BUILD / card / f'{card}.kicad_pcb'
             for card in ('gpu', 'io', 'storage', 'wifi', 'eink')},
            BUILD / 'system/system-routed.kicad_pcb', BUILD / 'cpu/cpu.kicad_pcb')
    except ValueError as error:
        print('detected netlist finger swap: gen_top rejects it:', error, flush=True)
        return True
    path = directory / 'netlist-swap.json'
    path.write_text(json.dumps(manifest))
    code, tail = lockstep(['--waits', '3'], path)
    print(('detected ' if code else 'MISSED   ') + 'netlist finger swap: map ' +
          str(manifest['runtime']['cpu_address'][:4]) + ', links ' +
          str(manifest['runtime']['cpu_address_links'][:4]) + ': ' + tail, flush=True)
    return code != 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--top', type=Path, help='an already generated manifest')
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='cupc8-cc051-') as name:
        directory = Path(name)
        top_path = args.top
        if top_path is None:
            top_path = directory / 'top.json'
            subprocess.run([sys.executable, 'hw/cosim/gen_top.py', *map(str, BOARDS),
                            '--require-route', '--output', str(top_path)],
                           cwd=ROOT, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        top = json.loads(top_path.read_text())
        runtime = top['runtime']
        print('socket: address map', runtime['cpu_address'], 'data map', runtime['cpu_data'],
              flush=True)
        good = all(passes(a, top_path) for rows in BUS.values() for a in rows)
        good &= passes(['--engine', 'mainboard'])            # BUS-002 as catalogued

        def swap(key, i, j):
            def change(rt):
                rt[key][i], rt[key][j] = rt[key][j], rt[key][i]
            return change

        def open_data(rt):
            rt['cpu_data_links'][0] = False

        caught = [mutant(top, directory, 'address contacts A2/A3 swapped', swap('cpu_address', 2, 3)),
                  mutant(top, directory, 'data contacts D0/D1 swapped', swap('cpu_data', 0, 1)),
                  mutant(top, directory, 'data D0 link open', open_data),
                  netlist_swap(directory)]
    if not good:
        raise SystemExit('FAIL: BUS-001..003 through the modelled CPU socket')
    if not all(caught):
        raise SystemExit('FAIL: a socket wiring mutation was not detected')
    print('CC-051: BUS-001..003 pass through the netlist CPU socket; 4 wiring mutations detected')


if __name__ == '__main__':
    main()
