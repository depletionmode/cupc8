#!/usr/bin/env python3
"""Counterexamples and fixture checks for the IBIS-derived bus diagnostic."""
import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'hw/si'))
from ibis_bus import evaluate


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--top', type=Path, required=True)
    args = parser.parse_args()
    t = np.array([0, 10, 20, 30, 40], dtype=float) * 1e-9
    rise = np.array([[0], [1.9], [2.01], [1.99], [3.3]])
    fall = np.array([[3.3], [0.9], [0.79], [0.81], [0]])
    assert not evaluate(t, rise, 'rise', 3.3)[0]['threshold_stable']
    assert not evaluate(t, fall, 'fall', 3.3)[0]['threshold_stable']
    with tempfile.TemporaryDirectory(prefix='cupc8-ibis-test-') as temporary:
        directory = Path(temporary)
        output = directory / 'result.json'
        subprocess.run([sys.executable, ROOT / 'hw/si/ibis_bus.py', '--top', args.top,
                        '--out', output], cwd=ROOT, check=True)
        report = json.loads(output.read_text())
        assert len(report['cases']) == 96 and report['top_routed_signals'] is False
        assert max(c['fixture_max_error_v'] for c in report['cases']) < .08
        assert any(not all(n['threshold_stable'] for n in c['receivers'])
                   for c in report['cases'] if c['topology'] == 'six_slot_sck')
        top = json.loads(args.top.read_text())
        path = next(p for p in top['paths'] if p.get('to') == 'main.J11.B13')
        path['ohms'] = 47
        broken = directory / 'wrong-termination.json'
        broken.write_text(json.dumps(top))
        bad = subprocess.run([sys.executable, ROOT / 'hw/si/ibis_bus.py', '--top', broken,
                              '--out', directory / 'bad.json'], cwd=ROOT, capture_output=True, text=True)
        assert bad.returncode and '33-ohm SCK source path' in bad.stderr
    print('IBIS fixture replay, 96 ngspice transients, threshold re-cross and wrong-series-resistor counterexamples pass')


if __name__ == '__main__':
    main()
