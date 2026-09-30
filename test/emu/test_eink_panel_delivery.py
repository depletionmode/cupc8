"""Reject an actual5.83-inch ELF delivered as7.5-inch firmware.

Uses the unchanged native firmware/panel bench. No ELF bytes, expected
responses, firmware or golden pictures are changed.
"""
from pathlib import Path
import argparse
import hashlib
import shutil
import subprocess
import tempfile

p = argparse.ArgumentParser()
p.add_argument('--root', type=Path, default=Path('.'))
a = p.parse_args()
root = a.root.resolve()
h = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
bench = root / 'build/emu-machine/einkcard'
wrong = root / 'build/rp2040/eink.elf'
right = root / 'build/rp2040/eink750.elf'
assert h(wrong) != h(right), 'distinct genuine panel firmware required'
protected = [bench, wrong, right, *sorted((root / 'test/eink/golden').glob('*750*'))]
before = {str(path): h(path) for path in protected}
with tempfile.TemporaryDirectory(prefix='cupc8-wrong-eink-panel-') as work:
    candidate = Path(work)
    (candidate / 'build/rp2040').mkdir(parents=True)
    (candidate / 'test/eink').mkdir(parents=True)
    shutil.copy2(wrong, candidate / 'build/rp2040/eink750.elf')
    (candidate / 'test/eink/golden').symlink_to(root / 'test/eink/golden', target_is_directory=True)
    run = subprocess.run([str(bench), '--root', str(candidate), '--panel', '750'],
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    print(run.stdout, end='')
    assert run.returncode == 1, f'wrong panel must fail existing bench, got {run.returncode}'
    assert any('FAIL ' in line and line.endswith(': INFO') for line in run.stdout.splitlines())
    assert 'card_boot_750: the glass differs' in run.stdout
    assert 'card_grey_750: the glass differs' in run.stdout
assert before == {str(path): h(path) for path in protected}
print('PASS wrong648x480 ELF rejected by real800x480 INFO and glass assertions; sources/assets unchanged')
