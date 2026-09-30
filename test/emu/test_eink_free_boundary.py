"""Genuine750 firmware FREE boundary; no SRAM or firmware mutation."""
import argparse
from pathlib import Path
import re
import subprocess

r=Path(__file__).resolve().parents[2]
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--elf',required=True,type=Path)
p.add_argument('--bench',type=Path,default=r/'build/emu-machine/einkfree')
p.add_argument('--expect-loss',action='store_true')
a=p.parse_args()
cmd=['gdb','-q','-batch',str(a.elf)]
for s in ['eink.gpu.head','eink.gpu.tail','eink.gpu.errors','slotspi_errors']:
 cmd+=['-ex','p/x &'+s]
addresses=re.findall(r'\$\d+ = (0x[0-9a-f]+)',subprocess.check_output(cmd,text=True))
assert len(addresses)==4
subprocess.run([str(a.bench),str(a.elf),*addresses,'old' if a.expect_loss else 'fixed'],check=True)
