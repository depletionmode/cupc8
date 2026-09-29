#!/usr/bin/env python3
"""Strict entry point for the netlist-driven E2E and board-level co-sim rows.

Every row first validates the eight board receipts (hw/tools/boardevidence:
stale or changed build artifacts fail), then generates its own top from
the routed boards with --require-route, and builds the firmware and the
native emulator.

E2E-001 is the coverage row: it requires that every net of all eight
netlists is executed by a model or explicitly waived (--require-coverage),
and runs every binding test with its copper and netlist mutations.
E2E-002..004 run their whole-machine scenarios on the netlist-generated top
(every path routed) and then re-run them on a top with one wiring fault,
which must fail (test/hw/test_cosim_e2e_mutants.py); their own coverage
statement is E2E-001's, so they do not repeat the net accounting.
Board rows (MB-052, CC-051, SC-051, EC-051, YC-051) run that board's routed
binding tests and functional runs on the generated top; SC/EC/YC-051 also
require every net of that card to be executed or waived.
"""
import argparse
import fcntl
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BUILD = ROOT / 'build/hw'
BOARDS = ('main', 'cpu', 'gpu', 'io', 'storage', 'wifi', 'eink', 'system')
ROWS = ('E2E-001', 'E2E-002', 'E2E-003', 'E2E-004', 'MB-052', 'CC-051', 'SC-051', 'EC-051', 'YC-051')
CARD_ROWS = {'SC-051': 'storage', 'EC-051': 'eink', 'YC-051': 'system'}


def run(args, env=None):
    print('+', ' '.join(map(str, args)), flush=True)
    subprocess.run([str(x) for x in args], cwd=ROOT, env=env, check=True)


def two_identical_runs(environment):
    """E2E-003 twice with the same port: the same run (the Wi-Fi card is in step).

    CUPC8_E2E003_PORT fixes the port the test types; CUPC8_ESP_TRACE logs every
    select and frame with the board's and QEMU's time. The traces and the
    line that ends the test (time and CPU state) must be identical.
    """
    import socket
    import tempfile
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', 0))
        port = probe.getsockname()[1]
    ends, traces = [], []
    with tempfile.TemporaryDirectory(prefix='cupc8-e2e003-') as directory:
        for index in (1, 2):
            trace = Path(directory) / f'trace{index}.txt'
            env = dict(environment, CUPC8_E2E003_PORT=str(port), CUPC8_ESP_TRACE=str(trace))
            print('+ E2E-003 run', index, 'port', port, flush=True)
            done = subprocess.run(['node', str(ROOT / 'test/emu/test_e2e.mjs'), 'E2E-003'], cwd=ROOT, env=env,
                                  stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            print(done.stdout, flush=True)
            if done.returncode:
                raise SystemExit(f'FAIL: E2E-003 run {index} exited {done.returncode}')
            ends.append(next(line[line.index('ended at'):] for line in done.stdout.splitlines() if 'ended at' in line))
            traces.append(trace.read_bytes())
    if not traces[0]:
        raise SystemExit('FAIL: E2E-003 wrote no ESP trace')
    if ends[0] != ends[1] or traces[0] != traces[1]:
        raise SystemExit(f'FAIL: E2E-003 runs differ (end {ends}, traces {len(traces[0])} / {len(traces[1])} bytes)')
    print(f'E2E-003: two runs on port {port} are the same run ({ends[0]}; {len(traces[0])}-byte traces equal)', flush=True)


def receipts():
    sys.path.insert(0, str(ROOT / 'hw/tools'))
    from boardevidence import validate
    for name in BOARDS:
        try:
            validate(name, BUILD / name, root=ROOT)
        except Exception as error:
            raise SystemExit(f'FAIL: {name} board receipt: {error}')
    print('eight board receipts validate', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('case', choices=ROWS)
    parser.add_argument('--main-netlist', type=Path, default=BUILD / 'main/main.net')
    args = parser.parse_args()
    receipts()
    # build/hw holds the receipt-bound boards (a worktree links it in): the
    # generated tops go beside it, never into it
    output = ROOT / 'build/cosim' / (args.case + '.json')
    output.parent.mkdir(parents=True, exist_ok=True)
    boards = ['--main-netlist', args.main_netlist, '--card-board-dir', BUILD,
              '--system-board', BUILD / 'system/system-routed.kicad_pcb',
              '--cpu-board', BUILD / 'cpu/cpu.kicad_pcb']
    # Each row owns its manifest. The strict generator refuses an incomplete
    # route, even though development probes may use it provisionally.
    generation = [sys.executable, ROOT / 'hw/cosim/gen_top.py', *boards, '--require-route',
                  '--output', output]
    if args.case == 'E2E-001':
        generation.insert(-2, '--require-coverage')
    run(generation)
    if args.case in CARD_ROWS:
        # the card's own nets first: a gap fails the row before the long runs
        card = CARD_ROWS[args.case]
        manifest = json.loads(output.read_text())
        gaps = [net for net in manifest['unmodeled_nets'] if net.startswith(card + ':')]
        if gaps:
            raise SystemExit(f'FAIL: {args.case}: {len(gaps)} {card} nets have no executed model '
                             f'or waiver: {", ".join(gaps)}')
        print(f'{args.case}: every {card} net is executed or waived', flush=True)
    # Firmware and the native addon are shared build products. Parallel rows
    # wait here so their build steps cannot overwrite each other.
    with (output.parent / 'build.lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        run([ROOT / 'tools/fw_rp2040.sh'])
        run([ROOT / 'tools/emu_machine_build.sh'])
        if args.case in ('E2E-003',):
            run([ROOT / 'tools/fw_esp32c3.sh', 'qemu'])
            run([ROOT / 'tools/qemu_build.sh'])
    top = ['--top', output]
    native = dict(os.environ, CUPC8_EMU='native', CUPC8_COSIM_TOP=str(output))
    test = lambda name, *extra: run([sys.executable, ROOT / 'test/hw' / name, *extra])  # noqa: E731
    e2e = lambda *cases: [run(['node', ROOT / 'test/emu/test_e2e.mjs', case], env=native)  # noqa: E731
                          for case in cases]
    if args.case == 'E2E-001':
        test('test_cosim_wiring.py', '--main-netlist', args.main_netlist,
             '--main-board', args.main_netlist.with_suffix('.kicad_pcb'), *boards[2:])
        test('test_cosim_runtime.py', *top)
        run(['node', ROOT / 'test/hw/test_cosim_pixels.mjs'], env=native)
        test('test_cosim_coverage.py', *boards)
        test('test_cosim_fpga_config.py', *boards)
        test('test_cosim_card_leds.py', *boards)
        test('test_cosim_sysctl_inputs.py', *boards)
        test('test_cosim_io_vbus.py', *boards)
        test('test_cosim_prog_port.py', *boards)
    elif args.case.startswith('E2E-'):
        if args.case == 'E2E-003':
            two_identical_runs(native)
        else:
            e2e(args.case)
        test('test_cosim_e2e_mutants.py', args.case, *boards)
    elif args.case == 'MB-052':
        test('test_cosim_main_board_subset.py')
        test('test_cosim_mb052_bridge.py', *boards, *top)
        test('test_cosim_fpga_config.py', *boards)
        test('test_cosim_sysctl_inputs.py', *boards)
        test('test_cosim_prog_port.py', *boards)
    elif args.case == 'CC-051':
        test('test_cosim_cpu_socket.py')
        for name in ('cpu_controls', 'cpu_ready', 'cpu_sync', 'cpu_status', 'cpu_irq', 'cpu_timer_exp'):
            test(f'test_cosim_{name}.py', *boards, '--main-board', args.main_netlist.with_suffix('.kicad_pcb'),
                 *top)
    else:
        card = CARD_ROWS[args.case]
        if card == 'storage':
            test('test_cosim_storage_sd.py')
            test('test_cosim_card_leds.py', *boards)
            test('test_cosim_prog_port.py', *boards)
            e2e('E2E-007')
        elif card == 'eink':
            test('test_cosim_eink_panel.py')
            test('test_cosim_card_leds.py', *boards)
            test('test_cosim_prog_port.py', *boards)
            e2e('E2E-008', 'E2E-016')
        else:
            main_board = ['--main-board', args.main_netlist.with_suffix('.kicad_pcb')]
            for name in ('system_usb', 'sysctl_vbus', 'sysctl_reset'):
                test(f'test_cosim_{name}.py', *boards, *main_board, *top)
            test('test_cosim_fpga_config.py', *boards)
            test('test_cosim_card_leds.py', *boards)
            test('test_cosim_sysctl_inputs.py', *boards)
            test('test_cosim_prog_port.py', *boards)
            e2e('E2E-002', 'E2E-020')
    print(f'{args.case} passed')


if __name__ == '__main__':
    main()
