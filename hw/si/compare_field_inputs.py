#!/usr/bin/env python3
"""Bind archived openEMS fields to rebuilt boards by modeled-input equality.

The XML fingerprint preserves grid, materials, properties, ports, excitation,
and all primitive attributes/vertices. It ignores CSXCAD's random display
colors. Only consecutive, same-priority copper polygons within one Primitives
block are sorted: their insertion order cannot change any field cell material.
"""
import argparse
import hashlib
import json
from decimal import Decimal
from pathlib import Path
import re
import sys
from tempfile import TemporaryDirectory
import xml.etree.ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import boardevidence
from kicadgen import parse
from openems_gpu_d0 import routed_pair as gpu_routes, simulate as gpu_simulate
from openems_usb_io import (routed_pair as usb_routes, simulate as usb_simulate,
                            validate_series)

PAIRS = ('d0', 'd1', 'd2', 'ck')
PHYSICAL_ITEMS = ('segment', 'via', 'arc', 'zone', 'footprint', 'layers',
                  'gr_line', 'gr_arc', 'gr_poly', 'gr_rect', 'gr_circle')
RUNS = {
    'gpu-d0': ('gpu', 'gpu-d0-pml-fixed.json', 'gpu-d0-openems-pml-clear-1mm-fixed-window/gpu-d0.xml'),
    'gpu-d1': ('gpu', 'gpu-d1-pml-fixed.json', 'gpu-d1-openems-pml-clear-1mm-fixed-window/gpu-d1.xml'),
    'gpu-d2': ('gpu', 'gpu-d2-pml-fixed.json', 'gpu-d2-openems-pml-clear-1mm-fixed-window/gpu-d2.xml'),
    'gpu-ck': ('gpu', 'gpu-ck-pml-fixed.json', 'gpu-ck-openems-pml-clear-1mm-fixed-window/gpu-ck.xml'),
    'usb-075': ('io', 'usb-io-pml-fixed.json', 'usb-io-openems-pml-clear-1mm-fixed-window/usb-io.xml'),
    'usb-090': ('io', 'usb-io-pml-mesh-090-fixed.json',
                'usb-io-openems-pml-clear-1mm-mesh-0p090mm-fixed-window/usb-io.xml'),
}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def xml_node(element, parent=None):
    """Strict field tree; ignore display colors, whitespace, and polygon order."""
    children = [xml_node(child, element.tag) for child in element
                if child.tag not in ('FillColor', 'EdgeColor')]
    if element.tag == 'Primitives' and parent == 'Metal':
        ordered = []
        index = 0
        while index < len(children):
            child = children[index]
            if child[0] != 'Polygon':
                ordered.append(child)
                index += 1
                continue
            priority = dict(child[1]).get('Priority')
            end = index + 1
            while (end < len(children) and children[end][0] == 'Polygon' and
                   dict(children[end][1]).get('Priority') == priority):
                end += 1
            ordered.extend(sorted(children[index:end]))
            index = end
        children = ordered
    return (element.tag, tuple(sorted(element.attrib.items())),
            (element.text or '').strip(), tuple(children))


def xml_fingerprint(path):
    return digest(xml_node(ET.parse(path).getroot()))


def route_fingerprint(board, kind):
    if kind == 'gpu':
        return digest({pair: {net: sorted(segments) for net, segments in gpu_routes(board, pair).items()}
                       for pair in PAIRS})
    routes, endpoints = usb_routes(board)
    return digest({'routes': {net: sorted(segments) for net, segments in routes.items()},
                   'endpoints': endpoints})


def collinear_between(a, b, c):
    ax, ay = (Decimal(value) for value in a[1:])
    bx, by = (Decimal(value) for value in b[1:])
    cx, cy = (Decimal(value) for value in c[1:])
    return ((bx - ax) * (cy - ay) == (by - ay) * (cx - ax) and
            min(ax, cx) <= bx <= max(ax, cx) and
            min(ay, cy) <= by <= max(ay, cy))


def physical_item(item, parent=None):
    """Drop regenerated UUIDs and redundant collinear zone-fill vertices."""
    if not isinstance(item, list):
        return item
    if item[0] == 'pts' and parent == 'filled_polygon':
        points = [child for child in item[1:] if isinstance(child, list) and child[0] == 'xy']
        if len(points) != len(item) - 1:
            raise ValueError('unexpected filled-polygon point encoding')
        changed = True
        while changed and len(points) > 3:
            changed = False
            for index in range(len(points)):
                if collinear_between(points[index - 1], points[index],
                                     points[(index + 1) % len(points)]):
                    points.pop(index)
                    changed = True
                    break
        return ['pts', *points]
    result = [item[0]]
    for child in item[1:]:
        if isinstance(child, list) and child and child[0] in ('uuid', 'tstamp'):
            continue
        result.append(physical_item(child, item[0] if item[0] == 'filled_polygon' else None))
    return result


def board_physical_fingerprint(board):
    tree = parse(board.read_text())
    if tree[0] != 'kicad_pcb':
        raise ValueError('not a KiCad PCB')
    items = {tag: [] for tag in PHYSICAL_ITEMS}
    for item in tree[1:]:
        if isinstance(item, list) and item and item[0] in items:
            normalized = physical_item(item)
            items[item[0]].append(json.dumps(normalized, separators=(',', ':')))
    return digest({tag: sorted(values) for tag, values in items.items()})


def generate(board, netlist, model, report, directory):
    if model.startswith('gpu-'):
        pair = model.removeprefix('gpu-')
        result = gpu_simulate(board, directory, report['max_steps'], pair=pair,
                              pml_clearance_mm=report['pml_clearance_mm'],
                              geometry_only=True, fixed_window=report['fixed_window'],
                              threads=report['solver_threads'])
        xml = directory / f'gpu-{pair}.xml'
    else:
        result = usb_simulate(board, directory, mesh_mm=report['mesh_mm'],
                              max_steps=report['max_steps'], port_ohms=report['declared_port_ohms'],
                              netlist=netlist, pml_clearance_mm=report['pml_clearance_mm'],
                              geometry_only=True, fixed_window=report['fixed_window'],
                              threads=report['solver_threads'])
        xml = directory / 'usb-io.xml'
    if not result['pml_geometry_ok']:
        raise ValueError(f'{model}: generated geometry enters PML')
    for key in ('fixed_window', 'max_steps', 'solver_threads', 'pml_clearance_mm',
                'air_bounds_mm', 'material_bounds_mm', 'pml_inner_bounds_mm'):
        if json.dumps(result[key]) != json.dumps(report[key]):
            raise ValueError(f'{model}: generated {key} differs from archived run')
    if model.startswith('usb-') and result['mesh_mm'] != report['mesh_mm']:
        raise ValueError(f'{model}: generated mesh differs from archived run')
    return xml


def compare(old_build, new_build, old_source, new_source, fields, reports):
    receipts = {}
    routes = {}
    physical = {}
    board_hashes = {}
    for board in ('gpu', 'io'):
        receipts[board] = {}
        board_hashes[board] = {}
        for label, build, source in (('archived', old_build, old_source),
                                     ('current', new_build, new_source)):
            directory = build / board
            receipt = boardevidence.validate(board, directory, root=source)
            pcb = directory / f'{board}.kicad_pcb'
            routes.setdefault(board, {})[label] = route_fingerprint(pcb, board)
            physical.setdefault(board, {})[label] = board_physical_fingerprint(pcb)
            board_hashes[board][label] = sha(pcb)
            receipts[board][label] = {
                'receipt_sha256': sha(directory / 'evidence.json'),
                'input_fingerprint': digest(receipt['inputs']),
                'board_sha256': board_hashes[board][label],
                'netlist_sha256': sha(directory / f'{board}.net'),
            }
        if routes[board]['archived'] != routes[board]['current']:
            raise ValueError(f'{board}: modeled routed copper/endpoint geometry changed')
        if physical[board]['archived'] != physical[board]['current']:
            raise ValueError(f'{board}: normalized board physical geometry changed')
    # The USB netlist can differ outside this model. Guard its series path on both boards.
    for build in (old_build, new_build):
        validate_series(build / 'io' / 'io.net')
    models = {}
    with TemporaryDirectory(prefix='cupc8-si-inputs-') as temp:
        temp = Path(temp)
        for model, (board, report_name, relative_xml) in RUNS.items():
            report_path = reports / report_name
            report = json.loads(report_path.read_text())
            if report['board_sha256'] != board_hashes[board]['archived']:
                raise ValueError(f'{model}: saved report does not name archived board')
            if not report['fixed_window'] or report['pml_clearance_mm'] != 1:
                raise ValueError(f'{model}: saved run lacks fixed PML-safe window')
            if not report.get('valid_for_si_evidence', report.get('valid_for_diagnostic_sparams')):
                raise ValueError(f'{model}: saved field validation failed')
            saved_xml = fields / relative_xml
            if sha(saved_xml) != report['xml_sha256']:
                raise ValueError(f'{model}: saved XML hash differs from report')
            saved_log = saved_xml.parent / 'run.log'
            if sha(saved_log) != report['run_log_sha256']:
                raise ValueError(f'{model}: saved log hash differs from report')
            log = saved_log.read_text()
            if (f"openEMS - fixed number of threads: {report['solver_threads']}" not in log or
                f"Max. number of timesteps: {report['max_steps']}" not in log or
                'end-criteria of -150dB' not in log or
                not re.search(r'openEMS 64bit -- version (\S+)', log) or
                re.search(r'openEMS 64bit -- version (\S+)', log)[1] != report['solver_version']):
                raise ValueError(f'{model}: saved runtime log differs from reported solver config')
            generated = {}
            for label, build in (('archived', old_build), ('current', new_build)):
                directory = temp / model / label
                generated[label] = generate(build / board / f'{board}.kicad_pcb',
                                            build / board / f'{board}.net',
                                            model, report, directory)
            if xml_fingerprint(generated['archived']) != xml_fingerprint(saved_xml):
                raise ValueError(f'{model}: archived board no longer regenerates saved field input')
            fingerprints = {label: xml_fingerprint(path) for label, path in generated.items()}
            if fingerprints['archived'] != fingerprints['current']:
                raise ValueError(f'{model}: solver XML semantic fingerprint changed: {fingerprints}; '
                                 f'raw={[(label, sha(path)) for label, path in generated.items()]}')
            models[model] = {
                'report_sha256': sha(report_path),
                'saved_xml_sha256': sha(saved_xml),
                'saved_run_log_sha256': sha(saved_log),
                'solver_xml_fingerprint': fingerprints['current'],
                'model_source_sha256': sha(Path(__file__).with_name(
                    'openems_gpu_d0.py' if model.startswith('gpu-') else 'openems_usb_io.py')),
                'solver_config': {key: report[key] for key in
                                  ('fixed_window', 'max_steps', 'solver_threads',
                                   'pml_clearance_mm', 'solver_version')},
                'saved_subset_gate': True,
            }
            if model.startswith('usb-'):
                models[model]['solver_config'].update(mesh_mm=report['mesh_mm'],
                                                      declared_port_ohms=report['declared_port_ohms'],
                                                      reference_ohms=report['reference_ohms'])
            else:
                models[model]['solver_config'].update(mesh_mm=0.05, declared_port_ohms=100,
                                                      reference_ohms=100)
            models[model]['solver_config'].update(gaussian_center_hz=3000000000,
                                                  gaussian_width_hz=3000000000,
                                                  end_criteria_db=-150,
                                                  boundary='PML_8 on six sides')
    return {
        'scope': 'modeled GPU HDMI D0/D1/D2/CK and IO USB routed-copper field-input migration',
        'method': 'validated receipts; identical full-board track/via/zone/footprint/layer/outline '
                  'geometry after UUID removal and collinear filled-zone vertex normalization; '
                  'identical routed segments/endpoints; regenerated saved XML; '
                  'strict solver-relevant XML tree equality except random display colors and '
                  'same-priority copper Polygon ordering',
        'receipts': receipts, 'route_fingerprints': routes,
        'board_physical_fingerprints': physical, 'models': models,
        'current_board_modeled_subset_equivalent': True,
        'full_row_4_6_closed': False,
        'limits': ['saved field runs were made on archived PCB bytes; this report proves equality of modeled inputs',
                   'board solder-mask setup changed and is intentionally outside the copper-geometry fingerprint',
                   'USB copper polygon order differs in raw XML; the same-priority primitive set is identical',
                   'field models omit pads, finite copper/dielectric losses, solder mask, connectors and source/sink',
                   'USB impedance mesh convergence and full HDMI physical coupling remain open'],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('old-build', 'new-build', 'old-source', 'new-source', 'fields', 'reports', 'out'):
        parser.add_argument('--' + name, required=True, type=Path)
    args = parser.parse_args()
    result = compare(args.old_build.resolve(), args.new_build.resolve(),
                     args.old_source.resolve(), args.new_source.resolve(),
                     args.fields.resolve(), args.reports.resolve())
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2) + '\n')
    print(f"matched {len(result['models'])} field models across validated GPU/IO receipts")


if __name__ == '__main__':
    main()
