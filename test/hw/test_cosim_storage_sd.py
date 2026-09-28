#!/usr/bin/env python3
"""Receipt-bound storage microSD socket copper and native digital probe.

This is a focused card interface check, not the complete SC-051/3.1 gate.
"""

import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'hw/cosim'), str(ROOT / 'hw/si'), str(ROOT / 'hw/tools')]
from netlist import read  # noqa: E402
from storage_sd import SIGNALS, routes  # noqa: E402
from ibis_route_receipts import audit  # noqa: E402
from test_cosim_main_cpu_data import open_pad_tracks  # noqa: E402

PROBE = """
import { Machine } from './test/emu/machinenative.mjs';
const m = await Machine.create({slots: {1: 'storage'}, threaded: false,
  rom: Buffer.alloc(512 * 1024, 0xff)});
try {
  console.log(JSON.stringify({socket: Boolean(m.sd),
    storageCard: m.cards().some(c => c.kind === 'storage')}));
} finally { m.stop(); }
"""


def native_socket(top):
    env = dict(os.environ, CUPC8_COSIM_TOP=str(top.resolve()))
    result = subprocess.check_output(['node', '--input-type=module', '-e', PROBE],
                                     cwd=ROOT, env=env, text=True)
    return json.loads(result.strip())


def derived_top(original, connected, rows, missing):
    top = copy.deepcopy(original)
    top['runtime']['storage_sd_socket'] = connected
    top['storage_sd_copper'] = {'scope': 'digital socket, pull and ESD branches',
                                'paths': rows, 'missing': missing}
    if missing:
        top['runtime']['routed_top'] = False
        top['runtime']['missing_routes'].extend('storage:' + item for item in missing)
        for signal in SIGNALS:
            name = 'storage:' + signal
            if name in top['runtime_nets']:
                top['runtime_nets'].remove(name)
            if name not in top['unmodeled_nets']:
                top['unmodeled_nets'].append(name)
        top['unmodeled_nets'].sort()
    return top


def main():
    build = ROOT / 'build/hw'
    evidence = ROOT / 'doc/hardware/si-evidence'
    source_top = evidence / 'ibis-final-top.json'
    source_audit = evidence / 'ibis-final-source-audit.json'
    expected = json.loads((evidence / 'ibis-final-receipts.json').read_text())
    actual = audit(ROOT, build, build / 'system/system-routed.kicad_pcb',
                   source_top, source_audit, ROOT / 'hw/cosim/gen_top.py')
    if actual != expected:
        raise AssertionError('storage co-sim source or canonical board receipts changed')
    original = json.loads(source_top.read_text())
    board = build / 'storage/storage.kicad_pcb'
    circuit = read(build / 'storage/storage.net')
    good, rows, missing = routes(circuit, board)
    assert good and not missing and len(rows) == 20
    assert original['runtime']['storage_sd_socket'] is True

    wrong = copy.deepcopy(circuit)
    wrong.pins[('U1', '17')] = '/SD_MOSI'
    try:
        routes(wrong, None)
    except ValueError as error:
        assert 'SD_SCK' in str(error)
    else:
        raise AssertionError('swapped SD clock MCU pad passed source binding')

    with tempfile.TemporaryDirectory(prefix='cupc8-storage-sd-') as directory:
        temporary = Path(directory)
        intact = temporary / 'intact.json'
        intact.write_text(json.dumps(derived_top(original, good, rows, missing)))
        assert native_socket(intact) == {'socket': True, 'storageCard': True}
        for signal, (gpio, contact, pull, esd) in SIGNALS.items():
            pins = [('U1', gpio), ('J2', contact), esd]
            if pull:
                pins.append(pull)
            for ref, pin in pins:
                opened = temporary / f'open-{signal}-{ref}-{pin}.kicad_pcb'
                count = 2 if (signal, ref, pin) in ((
                    'SD_DAT1', 'U6', '1'), ('SD_nDETECT', 'J2', '9')) else 1
                open_pad_tracks(board, opened, ref, pin, '/' + signal, count)
                connected, changed, gaps = routes(circuit, opened)
                socket_open = any(row['function'] == 'socket' and
                                  row['route_mm'] is None for row in changed)
                assert connected is not socket_open and gaps, (signal, ref, pin)
                if ref in ('U1', 'J2'):
                    assert socket_open, (signal, ref, pin)
                assert any(x['route_mm'] is None for x in changed)
                if (ref, pin) == ('J2', contact):
                    mutant = temporary / f'open-{signal}-top.json'
                    mutant.write_text(json.dumps(derived_top(original, connected,
                                                              changed, gaps)))
                    assert native_socket(mutant) == {'socket': False,
                                                      'storageCard': True}
        print('storage SD: 20/20 routed branch opens detected; '
              '7/7 socket opens disable native SD attachment')
        print(f'storage SD: {len(original["unmodeled_nets"])} whole-system '
              'nets remain unmodeled; analog and power gates remain open')


if __name__ == '__main__':
    main()
