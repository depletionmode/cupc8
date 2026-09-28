#!/usr/bin/env python3
"""Bind a current-route IBIS source audit to validated board inputs."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path

BOARDS = ('main', 'cpu', 'gpu', 'io', 'storage', 'wifi', 'eink')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def audit(source_root, board_dir, system_board, top_path, source_audit_path,
          top_generator):
    spec = importlib.util.spec_from_file_location(
        'ibis_current_boardevidence', source_root / 'hw/tools/boardevidence.py')
    validator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(validator)
    receipts = {}
    for name in BOARDS:
        build = board_dir / name
        receipt = validator.validate(name, build, root=source_root)
        receipts[name] = {
            'receipt_sha256': sha(build / 'evidence.json'),
            'board_sha256': receipt['artifacts'][f'{name}.kicad_pcb'],
            'netlist_sha256': receipt['artifacts'][f'{name}.net'],
        }
    source = json.loads(source_audit_path.read_text())
    top = json.loads(top_path.read_text())
    if (source['top_sha256'] != sha(top_path) or
        source['receipts']['main'] != receipts['main'] or
        source['receipts']['cpu'] != receipts['cpu'] or
        source['valid_for_full_bus_si'] or
        not top['runtime']['routed_top']):
        raise ValueError('source audit, top or current board receipts disagree')
    if top_generator.resolve() != (source_root / 'hw/cosim/gen_top.py').resolve():
        raise ValueError('top generator is not from validated source root')
    if not system_board.is_file():
        raise FileNotFoundError(system_board)
    return {
        'scope': 'current seven-card receipt binding for IBIS source-path audit',
        'board_receipts': receipts,
        'system_route_snapshot_sha256': sha(system_board),
        'top_generator_sha256': sha(top_generator),
        'top_sha256': sha(top_path),
        'source_audit_sha256': sha(source_audit_path),
        'routed_top': True,
        'unmodeled_nets': len(top['unmodeled_nets']),
        'valid_for_full_bus_si': False,
        'limits': [
            'system route is a saved routed snapshot, not the in-progress canonical rebuild',
            'waveform diagnostics retain assumed line lengths and loads',
            'receiver IBIS, package assignment, return paths and branch extraction remain open',
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('source-root', 'board-dir', 'system-board', 'top',
                 'source-audit', 'top-generator', 'out'):
        parser.add_argument('--' + name, required=True, type=Path)
    args = parser.parse_args()
    result = audit(*(getattr(args, name.replace('-', '_')).resolve() for name in
                     ('source-root', 'board-dir', 'system-board', 'top',
                      'source-audit', 'top-generator')))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2) + '\n')
    print('validated card receipts:', ', '.join(result['board_receipts']))


if __name__ == '__main__':
    main()
