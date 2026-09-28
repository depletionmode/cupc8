#!/usr/bin/env python3
"""Make an unsigned, printable visual review packet from verified board builds."""

import argparse
import csv
import hashlib
import importlib.util
import io
from pathlib import Path
import sys

from PIL import Image, ImageDraw, ImageFont, ImageOps


BOARDS = ('main', 'cpu', 'gpu', 'eink', 'io', 'storage', 'wifi', 'system')
PAGE = (1654, 2339)  # A4 portrait, 200 dpi
MARGIN = 95
CHECKLIST_FIELDS = ('board', 'designator', 'value', 'footprint', 'lcsc_part',
                    'side', 'mid_x', 'mid_y', 'rotation', 'receipt_sha256',
                    'bom_sha256', 'cpl_sha256', 'pin_1_review',
                    'polarity_review', 'rotation_review')


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def checklist_rows(board, board_dir):
    """Join one BOM component per CPL placement, with exact designator coverage."""
    bom = board_dir / 'fab/bom.csv'
    cpl = board_dir / 'fab/cpl.csv'
    with bom.open(newline='') as stream:
        bom_rows = list(csv.DictReader(stream))
    with cpl.open(newline='') as stream:
        cpl_rows = list(csv.DictReader(stream))
    if not bom_rows or not cpl_rows:
        raise ValueError(f'{board}: empty BOM or CPL')
    if not {'Comment', 'Designator', 'Footprint', 'LCSC Part #'} <= bom_rows[0].keys():
        raise ValueError(f'{board}: unexpected BOM columns')
    if not {'Designator', 'Mid X', 'Mid Y', 'Layer', 'Rotation'} <= cpl_rows[0].keys():
        raise ValueError(f'{board}: unexpected CPL columns')

    bom_by_ref = {}
    for item in bom_rows:
        for ref in (part.strip() for part in item['Designator'].split(',')):
            if not ref or ref in bom_by_ref:
                raise ValueError(f'{board}: empty or duplicate BOM designator: {ref!r}')
            bom_by_ref[ref] = item
    cpl_by_ref = {}
    for item in cpl_rows:
        ref = item['Designator'].strip()
        if not ref or ref in cpl_by_ref:
            raise ValueError(f'{board}: empty or duplicate CPL designator: {ref!r}')
        cpl_by_ref[ref] = item
    if bom_by_ref.keys() != cpl_by_ref.keys():
        missing_cpl = sorted(bom_by_ref.keys() - cpl_by_ref.keys())
        missing_bom = sorted(cpl_by_ref.keys() - bom_by_ref.keys())
        raise ValueError(f'{board}: BOM/CPL coverage differs; missing CPL={missing_cpl}, '
                         f'missing BOM={missing_bom}')

    receipt_hash = sha256(board_dir / 'evidence.json')
    bom_hash, cpl_hash = sha256(bom), sha256(cpl)
    rows = []
    for ref, placement in cpl_by_ref.items():
        part = bom_by_ref[ref]
        rows.append(dict(board=board, designator=ref, value=part['Comment'],
                         footprint=part['Footprint'], lcsc_part=part['LCSC Part #'],
                         side=placement['Layer'], mid_x=placement['Mid X'],
                         mid_y=placement['Mid Y'], rotation=placement['Rotation'],
                         receipt_sha256=receipt_hash, bom_sha256=bom_hash,
                         cpl_sha256=cpl_hash, pin_1_review='', polarity_review='',
                         rotation_review=''))
    return rows


def write_checklist(path, rows):
    buffer = io.StringIO(newline='')
    writer = csv.DictWriter(buffer, fieldnames=CHECKLIST_FIELDS)
    writer.writeheader()
    writer.writerows(rows)
    path.write_text(buffer.getvalue())


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def font(size):
    for path in ('/usr/share/fonts/noto/NotoSans-Regular.ttf',
                 '/usr/share/fonts/liberation/LiberationSans-Regular.ttf'):
        if Path(path).is_file():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default(size=size)


def line(draw, y, label, value):
    draw.text((MARGIN, y), label + '  ' + value, fill='#273442', font=font(20))


def base_page(board, heading, number, total, receipt):
    page = Image.new('RGB', PAGE, 'white')
    draw = ImageDraw.Draw(page)
    draw.text((MARGIN, 51), board.upper() + '  /  ' + heading,
              fill='#122438', font=font(48))
    draw.text((MARGIN, 112), 'Unsigned visual review copy · review pending',
              fill='#a02e23', font=font(25))
    draw.line((MARGIN, 153, PAGE[0]-MARGIN, 153), fill='#8b99a8', width=2)
    draw.line((MARGIN, 2130, PAGE[0]-MARGIN, 2130), fill='#8b99a8', width=2)
    line(draw, 2150, 'Board receipt SHA-256:', receipt)
    draw.text((MARGIN, 2240), 'Generated from receipt-valid board artifacts. This packet is not a CPL approval.',
              fill='#5b6470', font=font(19))
    draw.text((PAGE[0]-MARGIN-130, 2240), f'{number}/{total}',
              fill='#5b6470', font=font(19))
    return page, draw


def place_image(page, path, box):
    with Image.open(path) as source:
        image = ImageOps.contain(source.convert('RGB'), (box[2], box[3]),
                                 Image.Resampling.LANCZOS)
    x = box[0] + (box[2]-image.width)//2
    y = box[1] + (box[3]-image.height)//2
    page.paste(image, (x, y))


def render_pages(board, board_dir, overlay, receipt, number, total):
    top = board_dir / (board + '-top.png')
    bottom = board_dir / (board + '-bottom.png')
    renders, draw = base_page(board, 'PCB RENDERS', number, total, receipt)
    boxes = ((MARGIN, 235, PAGE[0]-2*MARGIN, 760),
             (MARGIN, 1145, PAGE[0]-2*MARGIN, 760))
    for side, path, box in zip(('TOP', 'BOTTOM'), (top, bottom), boxes):
        draw.text((box[0], 181 if side == 'TOP' else 1091),
                  side + ' SIDE', fill='#122438', font=font(29))
        place_image(renders, path, box)
        line(draw, 1015 if side == 'TOP' else 1930,
             side.title() + ' PNG SHA-256:', sha256(path))

    placement, draw = base_page(board, 'TOP CPL OVERLAY', number+1, total, receipt)
    draw.text((MARGIN, 179), 'Blue circles: CPL centres    Red arrows: numeric CPL rotation',
              fill='#273442', font=font(24))
    place_image(placement, overlay, (MARGIN, 245, PAGE[0]-2*MARGIN, 1790))
    line(draw, 2070, 'Overlay PNG SHA-256:', sha256(overlay))
    return renders, placement


def create(repo_root, build_root, output, boards):
    if output.is_relative_to(build_root / 'hw'):
        raise ValueError('packet output must be outside receipt-bound build/hw')
    if len(set(boards)) != len(boards):
        raise ValueError('duplicate board in requested list')
    boardevidence = load_module('boardevidence', repo_root / 'hw/tools/boardevidence.py')
    # Validate every requested board before creating any output. This includes all
    # receipt input and artifact hashes and the mandatory render and fab files.
    def validate(board):
        try:
            boardevidence.validate(board, build_root / 'hw' / board, root=repo_root)
        except (OSError, ValueError) as exc:
            raise ValueError(f'{board}: invalid board receipt: {exc}') from exc

    for board in boards:
        validate(board)
    rows = [row for board in boards
            for row in checklist_rows(board, build_root / 'hw' / board)]

    sys.path.insert(0, str(repo_root / 'hw/tools'))
    cploverlay = load_module('cploverlay', repo_root / 'hw/tools/cploverlay.py')
    output.parent.mkdir(parents=True, exist_ok=True)
    overlay_root = output.parent / (output.stem + '-overlays')
    pages = []
    for index, board in enumerate(boards):
        board_dir = build_root / 'hw' / board
        overlay = cploverlay.render(board_dir, overlay_root)
        receipt = sha256(board_dir / 'evidence.json')
        pages.extend(render_pages(board, board_dir, overlay, receipt,
                                  2*index+1, 2*len(boards)))
    # Detect a concurrent board rebuild before publishing the packet.
    for board in boards:
        validate(board)
    first, *rest = pages
    temp_pdf = output.with_name(output.stem + '.tmp.pdf')
    checklist = output.with_name(output.stem + '-checklist.csv')
    temp_csv = checklist.with_name(checklist.stem + '.tmp.csv')
    first.save(temp_pdf, 'PDF', save_all=True, append_images=rest,
               resolution=200.0, title='CUPC8 board visual review packet',
               author='CUPC8 build tooling')
    write_checklist(temp_csv, rows)
    temp_pdf.replace(output)
    temp_csv.replace(checklist)
    print(f'{output} ({len(pages)} pages; review pending)')
    print(f'{checklist} ({len(rows)} unsigned review rows)')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo-root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--build-root', type=Path, help='Directory containing hw/<board> builds')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--boards', nargs='+', choices=BOARDS, default=list(BOARDS),
                        help='Subset for work in progress; default is all eight boards')
    args = parser.parse_args()
    repo_root = args.repo_root.resolve()
    build_root = (args.build_root or repo_root / 'build').resolve()
    try:
        create(repo_root, build_root, args.output.resolve(), args.boards)
    except (OSError, ValueError) as exc:
        parser.exit(1, f'board review packet: {exc}\n')


if __name__ == '__main__':
    main()
