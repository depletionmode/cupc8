#!/usr/bin/env python3
"""E-ink panel power/header continuity, native attachment and copper mutants."""

import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'hw/cosim'), str(ROOT / 'hw/tools')]
from gen_top import check, exported_cards  # noqa: E402
from eink_panel import routes  # noqa: E402
from netlist import read  # noqa: E402
from boardevidence import validate  # noqa: E402
from test_cosim_main_cpu_data import open_pad_tracks  # noqa: E402

PROBE = """
import { Machine } from './test/emu/machinenative.mjs';
const m = await Machine.create({slots: {1: 'eink'}, threaded: false,
  rom: Buffer.alloc(512 * 1024, 0xff)});
try { console.log(JSON.stringify({panel: Boolean(m.panel()),
  card: m.cards().some(c => c.kind === 'eink')})); }
finally { m.stop(); }
"""


def native_panel(top):
    env = dict(os.environ, CUPC8_COSIM_TOP=str(top.resolve()))
    result = subprocess.check_output(['node', '--input-type=module', '-e', PROBE],
                                     cwd=ROOT, env=env, text=True)
    return json.loads(result.strip())


def main():
    build = ROOT / 'build/hw'
    for name in ('main', 'cpu', 'gpu', 'io', 'storage', 'wifi', 'eink', 'system'):
        validate(name, build / name)
    circuit = read(build / 'eink/eink.net')
    board = build / 'eink/eink.kicad_pcb'
    main_circuit = read(build / 'main/main.net')
    with tempfile.TemporaryDirectory(prefix='cupc8-eink-panel-') as directory:
        temporary = Path(directory)
        cards = exported_cards(temporary)
        card_boards = {name: build / name / f'{name}.kicad_pcb'
                       for name in ('gpu', 'io', 'storage', 'wifi', 'eink')}
        base = check(cards, main_circuit, build / 'main/main.kicad_pcb',
                     card_boards, build / 'system/system-routed.kicad_pcb',
                     build / 'cpu/cpu.kicad_pcb')
        assert base['runtime']['routed_top'] and base['runtime']['eink_panel_link']
        connected, rows, missing = routes(circuit, board)
        assert connected and not missing and len(rows) == 27
        assert base['runtime']['eink_panel_copper_connected']
        assert base['eink_panel_copper']['paths'] == rows
        assert not base['eink_panel_copper']['missing']
        assert len(base['unmodeled_nets']) == 284
        assert 'eink:EPD_VCC' in base['runtime_nets']
        assert 'eink:EPD_VCC' not in base['unmodeled_nets']
        intact = temporary / 'intact.json'
        intact.write_text(json.dumps(base))
        assert native_panel(intact) == {'panel': True, 'card': True}

        wrong = copy.deepcopy(circuit)
        wrong.components['F1'] = ('250mA', ('Device', 'Polyfuse'))
        try:
            routes(wrong, None)
        except ValueError as error:
            assert 'supply PTC' in str(error)
        else:
            raise AssertionError('changed panel supply PTC passed source binding')

        cases = (
            ('supply', '3V3', 'F1', '1', 1, False),
            ('ptc-output', 'EPD_VCC', 'F1', '2', 2, False),
            ('panel-vcc', 'EPD_VCC', 'J2', '1', 1, False),
            ('mcu-din', 'EPD_DIN', 'U1', '14', 1, False),
            ('header-din', 'EPD_DIN_J', 'J2', '3', 1, False),
            ('tvs-din', 'EPD_DIN_J', 'U5', '2', 1, True),
        )
        for label, net, ref, pin, segments, expected_panel in cases:
            opened = temporary / f'{label}.kicad_pcb'
            open_pad_tracks(board, opened, ref, pin, '/' + net, segments)
            link, changed, gaps = routes(circuit, opened)
            assert gaps and link is expected_panel, (label, link, gaps)
            broken_cards = dict(card_boards)
            broken_cards['eink'] = opened
            altered = check(cards, main_circuit, build / 'main/main.kicad_pcb',
                            broken_cards, build / 'system/system-routed.kicad_pcb',
                            build / 'cpu/cpu.kicad_pcb')
            assert not altered['runtime']['routed_top']
            assert altered['eink_panel_copper']['missing'] == gaps
            mutant = temporary / f'{label}.json'
            mutant.write_text(json.dumps(altered))
            native = native_panel(mutant)
            assert native == {'panel': expected_panel, 'card': True}, (label, native)
            print(f'{label}: native panel={expected_panel}, routed gaps={len(gaps)}')
        print(f'e-ink panel continuity: strict unmodeled nets '
              f'{len(base["unmodeled_nets"])} (EPD_VCC bound to routed continuity); '
              'rail voltage, load, return, thermal and EMI remain unproved')


if __name__ == '__main__':
    main()
