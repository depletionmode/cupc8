#!/usr/bin/env python3
"""Live 2x shared-part stock gate for the receipt-bound sixteen-board M1 order.

Per-board stock checks cannot establish combined demand. No offline/replayed
supplier answers can pass this gate. This is a dated stock snapshot, never a
reservation or manufacturing approval.
"""
import argparse
import collections
import csv
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'hw/tools'))
import boardevidence
import jlcparts

BOARDS = ('main', 'cpu', 'gpu', 'io', 'wifi', 'storage', 'eink', 'system')
QUANTITY = 2
MARGIN = 2


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def demand(board_root):
    """Validate every receipt and count every fitted reference exactly once."""
    base = Path(board_root).resolve()
    counts = collections.Counter()
    binding = {}
    for board in BOARDS:
        directory = base / board
        evidence = boardevidence.validate(board, directory)
        if type(evidence['boards']) is not int or evidence['boards'] != QUANTITY:
            raise ValueError(f'{board}: M1 requires exactly {QUANTITY} assembled boards')
        bom = directory / 'fab/bom.csv'
        seen = set()
        per_board = collections.Counter()
        with bom.open(newline='') as source:
            for row in csv.DictReader(source):
                code = row['LCSC Part #']
                refs = [r.strip() for r in row['Designator'].split(',')]
                if not re.fullmatch(r'C[0-9]+', code) or not all(refs):
                    raise ValueError(f'{board}: invalid BOM part/designator')
                for ref in refs:
                    if ref in seen:
                        raise ValueError(f'{board}: repeated BOM designator {ref}')
                    seen.add(ref)
                per_board[code] += len(refs)
        if not per_board:
            raise ValueError(f'{board}: empty BOM')
        for code, fitted in per_board.items():
            counts[code] += fitted * QUANTITY
        binding[board] = {'directory': str(directory), 'quantity': QUANTITY,
                          'evidence_sha256': sha(directory / 'evidence.json'),
                          'bom_sha256': sha(bom), 'fitted_per_board': dict(per_board)}
    return dict(sorted(counts.items())), binding


def check(board_root, report):
    """Write partial evidence on failure; only genuine live complete scope passes."""
    report.update(scope='Live aggregate M1 stock snapshot; not reservation or manufacturing approval',
                  time_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                  status='blocked', margin=MARGIN, manufacturing_release_approved=False,
                  supplier_query='live', parts={})
    counts, binding = demand(board_root)
    report['boards'] = binding
    report['combined_fitted_demand'] = counts
    if os.environ.get('CUPC8_OFFLINE') or os.environ.get('JLCPARTS_RECORDED'):
        raise ValueError('live aggregate stock gate rejects offline or replayed supplier answers')
    failures = []
    for code, fitted in counts.items():
        hits = [p for p in jlcparts.query(code, 5) if p.get('componentCode') == code]
        if len(hits) != 1:
            report['parts'][code] = {'fitted': fitted, 'required_stock': MARGIN * fitted,
                                     'status': 'missing-or-ambiguous'}
            failures.append(f'{code}: missing or ambiguous exact supplier identity')
            continue
        stock = hits[0].get('stockCount')
        if type(stock) is not int or stock < 0:
            raise ValueError(f'{code}: invalid supplier stock count')
        enough = stock >= MARGIN * fitted
        report['parts'][code] = {'fitted': fitted, 'required_stock': MARGIN * fitted,
                                 'stock': stock, 'status': 'passed' if enough else 'short'}
        if not enough:
            failures.append(f'{code}: stock {stock} < {MARGIN}x combined demand {fitted}')
    after_counts, after_binding = demand(board_root)
    if (after_counts, after_binding) != (counts, binding):
        raise ValueError('board/BOM/receipt changed during aggregate stock check')
    report['input_validation_after_queries'] = 'passed'
    report['failures'] = failures
    report['status'] = 'failed' if failures else 'passed'
    if failures:
        raise ValueError('\n'.join(failures))
    return f'{len(counts)} parts: live stock >=2x SUM demand for all 16 assembled boards'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--board-root', type=Path, default=ROOT / 'build/hw')
    parser.add_argument('--output', type=Path, default=ROOT / 'build/release/aggregate-stock.json')
    args = parser.parse_args()
    report = {}
    try:
        print(check(args.board_root, report))
        result = 0
    except (OSError, ValueError, KeyError, TypeError) as error:
        report['error'] = str(error)
        print('aggregate stock gate BLOCKED/FAILED:', error, file=sys.stderr)
        result = 1
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    return result


if __name__ == '__main__':
    sys.exit(main())
