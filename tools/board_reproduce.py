#!/usr/bin/env python3
"""Rebuild a board into a scratch directory and prove it matches build/hw.

The board builders run the whole pipeline (Freerouting included). Building in
place would rewrite the canonical receipt that other tests pin, so the build
goes to a temporary directory and only the routed geometry is compared:
pcbnew gives every item a fresh UUID and reorders items on save, so raw bytes
differ between identical builds (sesreplay.preroute_digest normalizes both).

    python3 tools/board_reproduce.py wifi
"""

from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'hw/tools'))
from sesreplay import preroute_digest  # noqa: E402


def main():
    name = sys.argv[1]
    canonical = ROOT / 'build/hw' / name
    with tempfile.TemporaryDirectory(prefix=f'cupc8-{name}-rebuild-') as directory:
        out = Path(directory) / name
        subprocess.run([sys.executable, str(ROOT / 'hw/boards' / f'{name}.py'), str(out)],
                       cwd=ROOT, check=True)
        for file in (f'{name}.kicad_pcb', f'{name}-routed.kicad_pcb'):
            if preroute_digest(out / file) != preroute_digest(canonical / file):
                raise SystemExit(f'{name}: rebuilt {file} differs from build/hw/{name}')
        if (out / 'route.ses').read_bytes() != (canonical / 'route.ses').read_bytes():
            raise SystemExit(f'{name}: rebuilt route.ses differs from build/hw/{name}')
    print(f'{name}: scratch rebuild matches build/hw/{name} (boards and route.ses)')


if __name__ == '__main__':
    main()
