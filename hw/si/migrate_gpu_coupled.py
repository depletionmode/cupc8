#!/usr/bin/env python3
"""Bind saved coupled GPU fields to a rebuilt GPU receipt by field-input equality."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from compare_field_inputs import (PHYSICAL_ITEMS, board_physical_fingerprint,
                                  digest, parse, physical_item,
                                  route_fingerprint, xml_fingerprint)

RUNS = (
    ('d0', 'openems_gpu_coupled.py', ''),
    ('d1', 'openems_gpu_coupled.py', ''),
    ('d2', 'openems_gpu_coupled_d2ck.py', ''),
    ('ck', 'openems_gpu_coupled_d2ck.py', ''),
    ('d2', 'openems_gpu_coupled_d2ck_long.py', '-long'),
    ('ck', 'openems_gpu_coupled_d2ck_long.py', '-long'),
)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def receipt(build, source):
    spec = importlib.util.spec_from_file_location('gpu_migration_receipt_' +
                    hashlib.sha256(str(source).encode()).hexdigest()[:12],
                    source / 'hw/tools/boardevidence.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.validate('gpu', build, root=source)
    return {'receipt_sha256': sha(build / 'evidence.json'),
            'board_sha256': sha(build / 'gpu.kicad_pcb'),
            'netlist_sha256': sha(build / 'gpu.net')}


def model_module(path):
    spec = importlib.util.spec_from_file_location('gpu_coupled_migration_' + path.stem,
                                                   path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def normalized_physical_fingerprint(board, source):
    """Normalize only worktree-absolute 3-D model paths with verified bytes."""
    model_files = {}

    def normalize(node):
        if not isinstance(node, list):
            return node
        if node and node[0] == 'model' and len(node) > 1:
            path = Path(node[1])
            marker = '/hw/lib/'
            if not path.is_absolute():
                return [node[0], node[1], *(normalize(child) for child in node[2:])]
            if marker not in str(path):
                raise ValueError(f'unexpected footprint 3-D model path: {path}')
            relative = Path('hw/lib') / str(path).split(marker, 1)[1]
            pinned = source / relative
            if not pinned.is_file() or sha(path) != sha(pinned):
                raise ValueError(f'3-D model bytes differ from receipt source: {relative}')
            model_files[str(relative)] = sha(pinned)
            return [node[0], str(relative), *(normalize(child) for child in node[2:])]
        return [normalize(child) for child in node]

    tree = parse(board.read_text())
    items = {tag: [] for tag in PHYSICAL_ITEMS}
    for item in tree[1:]:
        if isinstance(item, list) and item and item[0] in items:
            normalized = normalize(physical_item(item))
            items[item[0]].append(json.dumps(normalized, separators=(',', ':')))
    return digest({tag: sorted(values) for tag, values in items.items()}), model_files


def compare(old_build, old_source, new_build, new_source, reports, fields):
    old, new = receipt(old_build, old_source), receipt(new_build, new_source)
    old_board, new_board = old_build / 'gpu.kicad_pcb', new_build / 'gpu.kicad_pcb'
    routes = {'saved': route_fingerprint(old_board, 'gpu'),
              'rebuilt': route_fingerprint(new_board, 'gpu')}
    physical_raw = {'saved': board_physical_fingerprint(old_board),
                    'rebuilt': board_physical_fingerprint(new_board)}
    old_physical, old_models = normalized_physical_fingerprint(old_board, old_source)
    new_physical, new_models = normalized_physical_fingerprint(new_board, new_source)
    physical = {'saved': old_physical, 'rebuilt': new_physical}
    if old_models != new_models:
        raise ValueError('rebuilt GPU referenced 3-D model bytes changed')
    if len(set(routes.values())) != 1 or len(set(physical.values())) != 1:
        raise ValueError('rebuilt GPU physical or routed copper changed')
    models = {}
    with TemporaryDirectory(prefix='cupc8-gpu-coupled-migration-') as tmp:
        for pair, source_name, suffix in RUNS:
            key = pair + suffix
            report_path = reports / f'gpu-coupled-{pair}{suffix}-fixed.json'
            if not report_path.is_file():
                raise FileNotFoundError(f'missing required coupled report: {report_path}')
            record = json.loads(report_path.read_text())
            source_path = Path(__file__).with_name(source_name)
            module = model_module(source_path)
            saved_fields = fields / f'gpu-coupled-{pair}{suffix}-openems'
            xml = saved_fields / f'gpu-coupled-{pair}.xml'
            log = saved_fields / 'run.log'
            if (record['board_sha256'] != old['board_sha256'] or
                record['gpu_receipt_sha256'] != old['receipt_sha256'] or
                record['model_source_sha256'] != sha(source_path) or
                record['xml_sha256'] != sha(xml) or
                record['run_log_sha256'] != sha(log)):
                raise ValueError(f'{key}: saved receipt/source/XML/log mismatch')
            raw = {f'port_{kind}_{index}': sha(saved_fields / f'port_{kind}_{index}')
                   for index in range(1, 5) for kind in ('ut', 'it')}
            generated = {}
            for label, build, source in (('saved', old_build, old_source),
                                         ('rebuilt', new_build, new_source)):
                directory = Path(tmp) / key / label
                geometry = module.simulate(build / 'gpu.kicad_pcb', directory, pair,
                                           record['max_steps'], record['solver_threads'],
                                           True, source)
                if (not geometry['pml_geometry_ok'] or
                    list(geometry['material_bounds_mm']) != record['material_bounds_mm'] or
                    list(geometry['port_order']) != record['port_order'] or
                    geometry['routes'] != record['routes']):
                    raise ValueError(f'{key}: regenerated modeled geometry differs')
                generated[label] = xml_fingerprint(directory / f'gpu-coupled-{pair}.xml')
            saved_fingerprint = xml_fingerprint(xml)
            if len({saved_fingerprint, *generated.values()}) != 1:
                raise ValueError(f'{key}: rebuilt solver XML differs from saved input')
            models[key] = {
                'saved_report_sha256': sha(report_path),
                'model_source_sha256': sha(source_path),
                'saved_xml_sha256': sha(xml), 'saved_run_log_sha256': sha(log),
                'raw_port_sha256': raw,
                'solver_xml_fingerprint': saved_fingerprint,
                'saved_subset_gate': record['valid_for_coupled_subset'],
                'modeled_input_equivalent': True,
            }
    if len(models) != len(RUNS):
        raise ValueError('not all six coupled field reports were audited')
    return {
        'scope': 'GPU coupled HDMI field-input migration after board rebuild',
        'saved_receipt': old, 'rebuilt_receipt': new,
        'route_fingerprints': routes,
        'raw_physical_fingerprints': physical_raw,
        'normalized_physical_fingerprints': physical,
        'normalized_3d_model_file_sha256': old_models,
        'models': models,
        'all_modeled_inputs_equivalent': True,
        'full_row_4_6_closed': False,
        'limits': ['saved field runs used earlier PCB bytes; this proves identical modeled inputs',
                   'a passing saved subset gate is required separately from migration',
                   'pads, connector, mask, losses, all-pair coupling and source/sink remain open'],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('old-build', 'old-source', 'new-build', 'new-source',
                 'reports', 'fields', 'out'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    result = compare(*(getattr(args, name.replace('-', '_')).resolve() for name in
                       ('old-build', 'old-source', 'new-build', 'new-source',
                        'reports', 'fields')))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2) + '\n')
    print('coupled GPU models migrated:', ', '.join(result['models']))


if __name__ == '__main__':
    main()
