#!/usr/bin/env python3
"""MB-052: BRG-001/002 and the CPU-card boot on the netlist-generated board.

Builds the kernel ROM, generates the top from the routed boards (or takes
--top), and runs test/hw/bridge_probe.mjs: the native RTL chipset, SRAM and
SST39 models and the real sysctl firmware, wired from the netlists, pass
the bridge RAM and ROM checks (test/hw/bridge_exercise.py), and the CPU
card model boots from the ROM the bridge wrote. Three copper faults on the
routed main board, each regenerated through gen_top.check(), must fail it: an
open SRAM /WE branch (the RAM checks read back wrong), an open ROM /WE branch
(programming never lands) and an open ROM A1 launch (the JEDEC unlock and
every program address are wrong).
"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'test/hw'))
from cosim_mutate import board_args, card_boards, open_pad  # noqa: E402
sys.path.insert(0, str(ROOT / 'hw/cosim'))
from gen_top import check, exported_cards  # noqa: E402
from netlist import read  # noqa: E402

BOOT_PC, BOOT_GPO = 0xE2B9, 0x02


def build_rom(directory):
    quiet = dict(cwd=ROOT, check=True, stdout=subprocess.DEVNULL)
    subprocess.run(['bash', 'kernel/assemble.sh', directory], **quiet)
    subprocess.run([sys.executable, 'tools/as.py', 'rom/boot.s', directory / 'boot.bin',
                    '0xe000,0xe600,0x0f00'], **quiet)
    subprocess.run(['bash', 'basic/build.sh', directory], **quiet)
    subprocess.run([sys.executable, 'tools/mkrom.py', directory / 'boot.bin', directory / 'kernel.o',
                    '--basic', directory / 'BASIC.PRG', '-o', directory / 'kernel.rom'], **quiet)
    return directory / 'kernel.rom'


def probe(top, rom):
    env = dict(os.environ, CUPC8_COSIM_TOP=str(top), CUPC8_SUBSET_ROM=str(rom))
    result = subprocess.run(['node', 'test/hw/bridge_probe.mjs'], cwd=ROOT, env=env,
                            stdout=subprocess.PIPE, text=True)
    return json.loads(result.stdout.strip().splitlines()[-1])


def main():
    args = board_args(__doc__).parse_args()
    with tempfile.TemporaryDirectory(prefix='cupc8-mb052-') as directory:
        temporary = Path(directory)
        rom = build_rom(temporary)
        top = args.top
        if top is None:
            top = temporary / 'top.json'
            subprocess.run([sys.executable, 'hw/cosim/gen_top.py', '--main-netlist', args.main_netlist,
                            '--card-board-dir', args.card_board_dir, '--system-board', args.system_board,
                            '--cpu-board', args.cpu_board, '--require-route', '--output', top],
                           cwd=ROOT, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        manifest = json.loads(Path(top).read_text())
        assert manifest['runtime']['routed_top'] and manifest['runtime']['routed_timing']

        good = probe(top, rom)
        print(good['output'])
        assert good['boot'] == {'pc': BOOT_PC, 'gpo': BOOT_GPO, 'nrst': 1, 'halted': False}, good['boot']
        assert good['code'] == 0 and good['output'].endswith('BRIDGE OK'), good
        assert good['after']['nrst'] == 1 and good['after']['gpo'] == BOOT_GPO, good['after']
        print(f'MB-052: BRG-001/002 pass on the netlist-generated board; the CPU card model boots '
              f'(PC ${good["boot"]["pc"]:04X}, GPO ${good["boot"]["gpo"]:02X}) and boots again from '
              f'the ROM the bridge wrote (GPO ${good["after"]["gpo"]:02X})')

        main_circuit = read(args.main_netlist)
        rom_a1 = next(pin for (ref, pin), name in main_circuit.pin_names.items()
                      if ref == 'U10' and name == 'A1')
        (temporary / 'cards').mkdir()
        cards = exported_cards(temporary / 'cards')
        boards = card_boards(args)
        for label, ref, pin, net in (('SRAM /WE branch open (U9.5)', 'U9', '5', '/MEM_nWE'),
                                     ('ROM /WE branch open (U10.31)', 'U10', '31', '/MEM_nWE'),
                                     (f'ROM A1 launch open (U10.{rom_a1})', 'U10', rom_a1, main_circuit.pins[('U10', rom_a1)])):
            opened = temporary / f'open-{ref}-{pin}.kicad_pcb'
            open_pad(args.main_board, opened, ref, pin, net)
            mutant = check(cards, main_circuit, opened, boards, args.system_board, args.cpu_board)
            assert not mutant['runtime']['routed_top'], label
            bad_top = temporary / 'mutant.json'
            bad_top.write_text(json.dumps(mutant))
            bad = probe(bad_top, rom)
            failure = next((l for l in bad['output'].splitlines() if 'FAIL' in l), None)
            if bad['code'] == 0 or failure is None:
                raise AssertionError(f'{label}: the bridge checks passed on a board with this fault')
            print(f'{label}: detected ({failure})')
    print('MB-052 bridge and boot checks passed; wiring mutations detected')


if __name__ == '__main__':
    main()
