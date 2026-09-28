"""Receipt-bound main-board memory bus continuity for the digital co-sim subset."""

from pathlib import Path
import copy
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'hw/si'), str(ROOT / 'hw/tools')]
from ibis_bus import routed_distances  # noqa: E402


def unique_pad(circuit, ref, net):
    pads = [(r, p) for (r, p), name in circuit.pins.items()
            if r == ref and name == '/' + net]
    if len(pads) != 1:
        raise ValueError(f'{ref} {net}: expected one connected package pad, got {pads}')
    return pads[0]


def audit(circuit, board):
    """Check source pads and planar copper to both fitted memory packages."""
    rows = []
    signals = [(f'MEM_A{i}', ('U9', 'U10')) for i in range(19)]
    signals += [(f'MEM_D{i}', ('U9', 'U10')) for i in range(8)]
    signals += [('MEM_nOE', ('U9', 'U10')),
                ('MEM_nWE', ('U9', 'U10')),
                ('MEM_nCE_RAM', ('U9',)), ('MEM_nCE_ROM', ('U10',))]
    for net, chips in signals:
        source = unique_pad(circuit, 'U7', net)
        targets = [unique_pad(circuit, chip, net) for chip in chips]
        lengths = routed_distances(board, '/' + net, source, targets)
        for ref, pin in targets:
            rows.append({'net': net, 'from': f'{source[0]}.{source[1]}',
                         'to': f'{ref}.{pin}', 'route_mm': lengths[f'{ref}.{pin}']})
    missing = [f'{r["net"]}:{r["from"]}->{r["to"]}' for r in rows
               if r['route_mm'] is None]
    return rows, missing


def bound_top(source, rows, missing):
    """Feed measured memory branches into the existing native memory inputs."""
    top = copy.deepcopy(source)
    by_target = {(row['net'], row['to']): row['route_mm'] is not None
                 for row in rows}
    top['runtime']['memory_write_links'] = {
        'ram': by_target['MEM_nWE', 'U9.5'],
        'rom': by_target['MEM_nWE', 'U10.31']}
    top['runtime']['rom_read_d0_connected'] = by_target['MEM_D0', 'U10.13']
    top['runtime']['routed_top'] &= not missing
    top['runtime']['routed_timing'] &= not missing
    top['runtime']['missing_routes'].extend('main-memory:' + gap for gap in missing)
    top['main_memory_copper'] = {'scope': 'digital package-pad continuity',
                                 'paths': rows, 'missing': missing}
    return top
