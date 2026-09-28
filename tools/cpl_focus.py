#!/usr/bin/env python3
"""List the placements where a CPL rotation error breaks a board.

Two-terminal non-polar parts (R, C, L, F) work either way round, so the
human CPL review (fab/cpl-review.json, fabcheck.check_review) can spend its
time on ICs, diodes and LEDs, transistors, connectors, crystals, switches and
resistor networks. This narrows the review; it does not replace it.

    python3 tools/cpl_focus.py build/review-packet/cupc8-boards-checklist.csv
"""

import collections
import csv
import re
import sys

NON_POLAR = ('R', 'C', 'L', 'F')


def focus(rows):
    return [row for row in rows
            if re.match(r'[A-Z]+', row['designator']).group(0) not in NON_POLAR]


def main():
    rows = list(csv.DictReader(open(sys.argv[1])))
    picked = focus(rows)
    counts = collections.Counter(row['board'] for row in picked)
    writer = csv.writer(sys.stdout)
    writer.writerow(('board', 'designator', 'value', 'footprint', 'lcsc_part', 'rotation'))
    for row in picked:
        writer.writerow((row['board'], row['designator'], row['value'], row['footprint'],
                         row['lcsc_part'], row['rotation']))
    print('# %d of %d placements need a pin-1/polarity look: %s' % (
        len(picked), len(rows), ', '.join('%s %d' % item for item in sorted(counts.items()))),
        file=sys.stderr)


if __name__ == '__main__':
    main()
