#!/usr/bin/env python3
"""Prove the native RTL machine consumes the netlist-generated pin map."""
import argparse
import copy
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PROBE = """
import { Machine } from './test/emu/machinenative.mjs';
const m = await Machine.create({slots: {}, threaded: false});
m.powerOn();
m.runFor(20e6);
console.log(JSON.stringify(m.state()));
m.stop();
"""
SLOT_PROBE = """
import { Machine } from './test/emu/machinenative.mjs';
const m = await Machine.create({slots: {1: 'hdmi'}, spiLog: true, threaded: false});
m.powerOn(); m.runFor(1e9);
console.log(JSON.stringify({frames: m.spiLog(1).filter(x => x.bytes.length).length}));
m.stop();
"""
BRIDGE_PROBE = """
import { Machine } from './test/emu/machinenative.mjs';
import { spawn } from 'node:child_process';
const m = await Machine.create({slots: {}, sysctl: true, threaded: false});
m.powerOn();
m.runFor(20e6);
const p = spawn('python3', ['tools/cupc8.py', '--port', `tcp:127.0.0.1:${m.sysctlPort}`, 'status'],
  {env: {...process.env, CUPC8_TIMEOUT_SCALE: '300'}});
let out = '', code = null;
p.stdout.on('data', d => out += d); p.stderr.on('data', d => out += d);
p.on('exit', c => code = c);
await m.runUntil(() => code !== null, 1e9);
console.log(JSON.stringify({code, bridge: /bridge status \\$([0-9a-f]+)/i.exec(out)?.[1] ?? null}));
m.stop();
"""


def run(top, probe=PROBE):
    env = dict(os.environ, CUPC8_COSIM_TOP=str(top))
    output = subprocess.check_output(['node', '--input-type=module', '-e', probe],
                                     cwd=ROOT, env=env, text=True)
    return json.loads(output.strip())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--top', type=Path, required=True)
    args = parser.parse_args()
    manifest = json.loads(args.top.read_text())
    good = run(args.top)
    with tempfile.TemporaryDirectory(prefix='cupc8-cosim-runtime-') as directory:
        for name, key in (('ROM', 'rom_address'), ('CPU', 'cpu_address')):
            changed = copy.deepcopy(manifest)
            bits = changed['runtime'][key]
            bits[0], bits[1] = bits[1], bits[0]
            mutant = Path(directory) / f'swapped-{name.lower()}.json'
            mutant.write_text(json.dumps(changed))
            bad = run(mutant)
            if good == bad or not bad['halted']:
                raise AssertionError(f'{name} A0/A1 mutation did not break execution: {good} / {bad}')
            print(f"{name} A0/A1 swap halts the native machine at ${bad['pc']:04x}")
        changed = copy.deepcopy(manifest)
        slot = changed['runtime']['slots'][0]
        slot['sck'], slot['mosi'] = slot['mosi'], slot['sck']
        mutant = Path(directory) / 'swapped-slot.json'
        mutant.write_text(json.dumps(changed))
        normal_frames, bad_frames = run(args.top, SLOT_PROBE)['frames'], run(mutant, SLOT_PROBE)['frames']
        if normal_frames < 1 or bad_frames >= normal_frames:
            raise AssertionError(f'slot SCK/MOSI swap did not break SPI: {normal_frames} / {bad_frames}')
        print(f'slot SCK/MOSI swap: {normal_frames} valid frames became {bad_frames}')

        changed = copy.deepcopy(manifest)
        bridge = changed['runtime']['bridge']
        bridge['sck'], bridge['mosi'] = bridge['mosi'], bridge['sck']
        mutant = Path(directory) / 'swapped-bridge.json'
        mutant.write_text(json.dumps(changed))
        normal_status, bad_status = run(args.top, BRIDGE_PROBE), run(mutant, BRIDGE_PROBE)
        if normal_status['code'] != 0 or normal_status['bridge'] is None or \
                normal_status['bridge'] == bad_status['bridge']:
            raise AssertionError(f'bridge SCK/MOSI swap did not change status: {normal_status} / {bad_status}')
        print(f"bridge SCK/MOSI swap: status ${normal_status['bridge']} became ${bad_status['bridge']}")
    print(f"valid netlist wiring runs normally to PC ${good['pc']:04x}")


if __name__ == '__main__':
    main()
