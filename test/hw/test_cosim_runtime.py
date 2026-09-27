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
USB_PROBE = """
import { Machine } from './test/emu/machinenative.mjs';
const m = await Machine.create({slots: {1: 'io', 2: 'storage'}, threaded: false});
console.log(JSON.stringify({keyboard: Boolean(m.keyboard), sd: Boolean(m.sd)}));
m.stop();
"""
DISPLAY_PROBE = """
import { Machine } from './test/emu/machinenative.mjs';
const m = await Machine.create({slots: {1: 'hdmi', 2: 'eink'}, threaded: false});
const panel = Boolean(m.panel());
const videoError = m.frame().error ?? null;
console.log(JSON.stringify({panel, videoError}));
m.stop();
"""
PANEL_PROBE = """
import { Machine } from './test/emu/machinenative.mjs';
const m = await Machine.create({slots: {1: 'eink'}, threaded: false});
console.log(JSON.stringify({panel: Boolean(m.panel())}));
m.stop();
"""
ROM_WRITE_PROBE = """
import { Machine } from './test/emu/machinenative.mjs';
import { kernelRom } from './test/emu/romimage.mjs';
import { spawn } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'cupc8-we-rom-'));
const image = path.join(directory, 'first-4k.bin');
fs.writeFileSync(image, kernelRom().subarray(0, 4096));
const m = await Machine.create({slots: {}, rom: Buffer.alloc(512*1024, 0xff), sysctl: true, threaded: false});
try {
  m.powerOn();
  const p = spawn('python3', ['tools/cupc8.py', '--port', `tcp:127.0.0.1:${m.sysctlPort}`,
                              'rom', 'write', image],
                  {env: {...process.env, CUPC8_TIMEOUT_SCALE: '300'}});
  let out = '', code = null;
  p.stdout.on('data', d => out += d); p.stderr.on('data', d => out += d);
  p.on('exit', c => code = c);
  await m.runUntil(() => code !== null, 60e9);
  console.log(JSON.stringify({code, verified: /wrote and verified 4096 bytes/.test(out),
                              failed: /verify failed/.test(out)}));
} finally {
  m.stop(); fs.rmSync(directory, {recursive: true, force: true});
}
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
        if 'main:nPOR' not in manifest['runtime_nets'] or not manifest['runtime']['por_connected']:
            raise AssertionError('supervisor reset requires executed, routed nPOR copper')
        changed = copy.deepcopy(manifest)
        changed['runtime']['por_connected'] = False
        mutant = Path(directory) / 'open-supervisor-reset.json'
        mutant.write_text(json.dumps(changed))
        por_bad = run(mutant)
        if good['nrst'] != 1 or por_bad['nrst'] != 0 or por_bad['pc'] == good['pc']:
            raise AssertionError(f'open nPOR path did not hold the native machine in reset: {good} / {por_bad}')
        print(f"open routed nPOR holds CPU at ${por_bad['pc']:04x} rather than ${good['pc']:04x}")
        if manifest['runtime']['memory_write_links'] != {'ram': True, 'rom': True} or \
                'main:MEM_nWE' not in manifest['runtime_nets']:
            raise AssertionError('memory writes require both executed, routed /WE branches')
        changed = copy.deepcopy(manifest)
        changed['runtime']['memory_write_links']['ram'] = False
        mutant = Path(directory) / 'open-sram-we.json'
        mutant.write_text(json.dumps(changed))
        ram_bad = run(mutant)
        if (ram_bad['pc'], ram_bad['sp']) == (good['pc'], good['sp']):
            raise AssertionError(f'open SRAM /WE did not alter CPU execution: {good} / {ram_bad}')
        print(f"open SRAM /WE moves CPU from ${good['pc']:04x} to ${ram_bad['pc']:04x}")
        changed = copy.deepcopy(manifest)
        changed['runtime']['memory_write_links']['rom'] = False
        mutant = Path(directory) / 'open-rom-we.json'
        mutant.write_text(json.dumps(changed))
        rom_good, rom_bad = run(args.top, ROM_WRITE_PROBE), run(mutant, ROM_WRITE_PROBE)
        if rom_good != {'code': 0, 'verified': True, 'failed': False} or \
                rom_bad != {'code': 1, 'verified': False, 'failed': True}:
            raise AssertionError(f'open ROM /WE did not break programming verification: {rom_good} / {rom_bad}')
        print('open ROM /WE makes sysctl flash-program verify fail')
        if not manifest['runtime']['rom_read_d0_connected']:
            raise AssertionError('ROM DQ0 requires an executed, routed read-data path')
        changed = copy.deepcopy(manifest)
        changed['runtime']['rom_read_d0_connected'] = False
        mutant = Path(directory) / 'open-rom-dq0.json'
        mutant.write_text(json.dumps(changed))
        rom_read_bad = run(mutant)
        if (rom_read_bad['pc'], rom_read_bad['gpo']) == (good['pc'], good['gpo']):
            raise AssertionError(f'open ROM DQ0 did not change CPU execution: {good} / {rom_read_bad}')
        print(f"open ROM DQ0 moves CPU from ${good['pc']:04x} to ${rom_read_bad['pc']:04x}")
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
        for name, key in (('ROM', 'rom_data'), ('CPU', 'cpu_data')):
            changed = copy.deepcopy(manifest)
            bits = changed['runtime'][key]
            bits[0], bits[1] = bits[1], bits[0]
            mutant = Path(directory) / f'swapped-{name.lower()}-data.json'
            mutant.write_text(json.dumps(changed))
            bad = run(mutant)
            if good == bad:
                raise AssertionError(f'{name} D0/D1 mutation did not change execution')
            print(f"{name} D0/D1 swap changes PC/GPO to ${bad['pc']:04x}/${bad['gpo']:02x}")
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
        changed = copy.deepcopy(manifest)
        changed['runtime']['io_usb_host'] = False
        mutant = Path(directory) / 'open-io-usb.json'
        mutant.write_text(json.dumps(changed))
        usb_good, usb_bad = run(args.top, USB_PROBE), run(mutant, USB_PROBE)
        if usb_good != {'keyboard': True, 'sd': True} or usb_bad != {'keyboard': False, 'sd': True}:
            raise AssertionError(f'IO USB data path does not control keyboard attachment: {usb_good} / {usb_bad}')
        print('open IO USB D+/D- path detaches the keyboard')
        changed = copy.deepcopy(manifest)
        changed['runtime']['storage_sd_socket'] = False
        mutant = Path(directory) / 'open-storage-sd.json'
        mutant.write_text(json.dumps(changed))
        sd_bad = run(mutant, USB_PROBE)
        if sd_bad != {'keyboard': True, 'sd': False}:
            raise AssertionError(f'storage SD path does not control socket attachment: {sd_bad}')
        print('open storage SD contact detaches the microSD socket')
        changed = copy.deepcopy(manifest)
        changed['runtime']['gpu_hdmi_link'] = False
        mutant = Path(directory) / 'open-hdmi-pair.json'
        mutant.write_text(json.dumps(changed))
        hdmi_bad = run(mutant, DISPLAY_PROBE)
        if hdmi_bad['videoError'] != 'no graphics card' or not hdmi_bad['panel']:
            raise AssertionError(f'HDMI pair does not control the capture endpoint: {hdmi_bad}')
        print('open HDMI pair detaches video capture')
        changed = copy.deepcopy(manifest)
        changed['runtime']['eink_panel_link'] = False
        mutant = Path(directory) / 'open-epd-signal.json'
        mutant.write_text(json.dumps(changed))
        epd_bad = run(mutant, PANEL_PROBE)
        if epd_bad != {'panel': False} or run(args.top, PANEL_PROBE) != {'panel': True}:
            raise AssertionError(f'e-paper signal does not control panel attachment: {epd_bad}')
        print('open e-paper signal detaches the panel')
    print(f"valid netlist wiring runs normally to PC ${good['pc']:04x}")


if __name__ == '__main__':
    main()
