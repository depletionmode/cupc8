"""Replay authentic CPU display traffic against an explicitly selected ELF.

Usage: python3 test/emu/test_eink_queue.py --elf PATH [--trace PATH]
Add --expect-loss to require the original firmware's transport counterexample.
The ELF's own debug symbols identify transport counters; no firmware patching.
"""
import argparse
import json
from pathlib import Path
import re
import subprocess
import tempfile

root = Path(__file__).resolve().parents[2]
p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--elf', required=True, type=Path)
p.add_argument('--trace', type=Path, default=root / 'test/emu/fixtures/eink750-http-display-trace.json')
p.add_argument('--bench', type=Path, default=root / 'build/emu-machine/einkqueue')
p.add_argument('--expect-loss', action='store_true')
p.add_argument('--attr-bursts', type=int, default=0,
               help='Insert this many legal ATTR frames after each captured PUTC; loss mode retains old PUTC-only flow control')
a = p.parse_args()
symbols = ['slotspi_errors', 'q_head', 'q_tail', 'q_commands',
           'eink.step', 'eink.change_seq', 'eink.shown_seq', 'eink.gpu.card.resp_ready']
cmd = ['gdb', '-q', '-batch', str(a.elf)]
for name in symbols:
    cmd += ['-ex', 'p/x &' + name]
out = subprocess.check_output(cmd, text=True)
addresses = re.findall(r'\$\d+ = (0x[0-9a-f]+)', out)
assert len(addresses) == len(symbols), out
frames = json.loads(a.trace.read_text())
assert frames and all(f['extra'] == 0 and f['bytes'] for f in frames)
assert 0 <= a.attr_bursts <= 255
if a.attr_bursts:
    stressed = []
    for f in frames:
        stressed.append(f)
        if f['bytes'][0] == 0x10:
            stressed.extend(dict(f, bytes=[0x13, 7]) for _ in range(a.attr_bursts))
    frames = stressed
mode = ('attr-loss' if a.expect_loss else 'attr-fixed') if a.attr_bursts else ('loss' if a.expect_loss else 'fixed')
with tempfile.TemporaryDirectory(prefix='cupc8-eink-queue-') as d:
    tsv = Path(d) / 'frames.tsv'
    tsv.write_text(''.join(f"{f['start']} {f['ns']} {len(f['bytes'])} " +
                           ' '.join(map(str, f['bytes'])) + '\n' for f in frames))
    subprocess.run([str(a.bench), str(a.elf), str(tsv), *addresses,
                    mode], check=True)
