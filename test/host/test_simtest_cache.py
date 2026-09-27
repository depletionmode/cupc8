#!/usr/bin/env python3
"""Each worktree's simtest compiler must use a private cache directory."""
import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
with tempfile.TemporaryDirectory() as directory:
    root = Path(directory)
    fake = root / 'bin'
    fake.mkdir()
    nim = fake / 'nim'
    nim.write_text('''#!/usr/bin/env python3
import pathlib, sys
cache = [a.split('=', 1)[1] for a in sys.argv if a.startswith('--nimcache=')]
pathlib.Path('cache.txt').write_text(cache[0] if cache else 'SHARED DEFAULT')
pathlib.Path('simtest').write_text('#!/bin/sh\\nexit 0\\n')
pathlib.Path('simtest').chmod(0o755)
''')
    nim.chmod(0o755)
    jobs = []
    for name in ('one', 'two'):
        tools = root / name / 'tools'
        tools.mkdir(parents=True)
        script = tools / 'run_tests.sh'
        script.write_bytes((ROOT / 'tools/run_tests.sh').read_bytes())
        jobs.append(subprocess.Popen(['bash', str(script)], env={**os.environ, 'HOME': str(root), 'PATH': str(fake) + ':' + os.environ['PATH']}))
    assert all(job.wait() == 0 for job in jobs)
    caches = [(root / name / 'tools/cache.txt').read_text() for name in ('one', 'two')]
    assert caches[0] != caches[1] and all(c != 'SHARED DEFAULT' for c in caches), 'FAIL simtest builds share Nim cache'
    print('ok simtest builds use separate Nim caches')
