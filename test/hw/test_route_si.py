#!/usr/bin/env python3
"""Focused checks for the GC/IC/YC-007 routed-copper SI tools.

    python3 test/hw/test_route_si.py --gpu build/hw/gpu --io build/hw/io --system build/hw/system

The builds are only read; mutated copies go to a temporary directory.
1. The cross-section solver is a lower bound that converges from below to
   Cohn's exact stripline impedance.
2. The impedance gate can pass: an edge-coupled pair drawn for 100 ohm on
   the JLC04161H-7628 stack lands inside 100 ohm +-10 %, while the GPU's
   routed D0 trace is proven above 110 ohm by its lower bound alone.
3. Mutations that must fail: an opened TMDS P track, TMDS resistors of
   different values, a wrong USB series resistor, an opened USB D- track.
4. The IO card's resistor-to-connector USB paths match the independently
   measured 9.407 / 20.101 mm in doc/hardware/si-models.md.
"""
import argparse
import math
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'hw/si'))
sys.path.insert(0, str(ROOT / 'hw/tools'))
from kicadgen import dump, find1, parse  # noqa: E402
import route_si  # noqa: E402
import tmds_si  # noqa: E402
import usb_fs_si  # noqa: E402
import xsection  # noqa: E402

# Edge-coupled F.Cu pair over the In1 plane with mask, width/gap in mm.
PAIR_100 = (.2, .2)


def opened(board_path, net, out):
    tree = parse(board_path.read_text())
    tracks = [item for item in tree[1:] if isinstance(item, list) and item and
              item[0] == 'segment' and find1(item, 'net') and find1(item, 'net')[1] == net]
    tree.remove(max(tracks, key=lambda t: math.dist(*(tuple(map(float, find1(t, k)[1:3]))
                                                       for k in ('start', 'end')))))
    out.write_text(dump(tree) + '\n')
    return out


def expect_error(text, call):
    try:
        call()
    except ValueError as error:
        assert text in str(error), str(error)
        return
    raise AssertionError(f'expected an error containing {text!r}')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--gpu', type=Path, required=True)
    parser.add_argument('--io', type=Path, required=True)
    parser.add_argument('--system', type=Path, required=True)
    args = parser.parse_args()

    # 1. lower bound, converging from below
    w, b = .2, .5
    exact = xsection.stripline_exact(w, b, 1.0)
    zs = [xsection.line_parameters(xsection.Section(
        [(-w / 2, w / 2, b / 2, b / 2, 1)], [], (-3, 3, 0, b), fine=.01, coarse=.1, refine=r))['z_se']
        for r in (1, 2, 4)]
    assert zs[0] < zs[1] < zs[2] < exact, (zs, exact)
    assert exact - zs[2] < .01 * exact, (zs, exact)

    # 2. the gate discriminates
    width, gap = PAIR_100
    good = route_si.solve_key((2.5, (('F.Cu', -gap / 2 - width, -gap / 2, 1),
                               ('F.Cu', gap / 2, gap / 2 + width, 2), ('In1.Cu', -2.5, 2.5, 0))))
    assert 90 <= good['z_lower'] and good['z_upper'] <= 110, good
    gpu = route_si.Board(args.gpu / 'gpu.kicad_pcb')
    route = gpu.path('/HD_D0P', ('RN2', '8'), ('J2', '7'))
    samples = route_si.sample_path(gpu, route, ('/HD_D0P', '/HD_D0N'), 1)
    trace = [s for s in samples if s['kind'] == 'trace']
    assert trace, 'no trace samples on D0P'
    routed = route_si.solve_key(trace[len(trace) // 2]['key'])
    assert routed['kind'] == 'z_diff' and routed['z_lower'] > 110, routed
    print(f'100-ohm reference pair {good["z_lower"]:.1f}-{good["z_upper"]:.1f} ohm; '
          f'routed GPU D0 >= {routed["z_lower"]:.1f} ohm')

    with tempfile.TemporaryDirectory(prefix='cupc8-route-si-') as tmp:
        tmp = Path(tmp)
        # 3a. opened TMDS P
        broken = route_si.Board(opened(args.gpu / 'gpu.kicad_pcb', '/HD_D0P', tmp / 'gpu-open.kicad_pcb'))
        expect_error('not connected', lambda: broken.path('/HD_D0P', ('RN2', '8'), ('J2', '7')))
        # 3b. TMDS resistors of different values
        text = (args.gpu / 'gpu.net').read_text()
        wiring, ohms = tmds_si.lanes(args.gpu / 'gpu.net', 'U1', 'J2')
        assert len(wiring) == 8 and ohms > 0
        ref = wiring[('d0', 'p')]['resistor'].split('.')[0]
        start = text.index(f'(ref "{ref}")')
        value_at = text.index('(value "', start)
        end = text.index('")', value_at)
        mixed = tmp / 'gpu-mixed.net'
        mixed.write_text(text[:value_at] + '(value "1k' + text[end:])
        expect_error('resistors differ', lambda: tmds_si.lanes(mixed, 'U1', 'J2'))
        # 3c. wrong USB series resistor
        text = (args.io / 'io.net').read_text()
        start = text.index('(ref "R15")')
        value_at = text.index('(value "', start)
        end = text.index('")', value_at)
        wrong = tmp / 'io-wrong.net'
        wrong.write_text(text[:value_at] + '(value "33R' + text[end:])
        wires = usb_fs_si.wiring(wrong, usb_fs_si.BOARDS['io'])
        rs = {'p': wires['dp']['ohms'], 'n': wires['dm']['ohms']}
        assert usb_fs_si.series_failures(rs), rs
        good_wires = usb_fs_si.wiring(args.io / 'io.net', usb_fs_si.BOARDS['io'])
        assert not usb_fs_si.series_failures({'p': good_wires['dp']['ohms'], 'n': good_wires['dm']['ohms']})
        # 3d. opened USB D-
        io_open = route_si.Board(opened(args.io / 'io.kicad_pcb', '/USB_CONN_DM', tmp / 'io-open.kicad_pcb'))
        expect_error('not connected', lambda: io_open.path('/USB_CONN_DM', ('R14', '2'), ('J2', '2')))

    # 4. independent length cross-check
    io = route_si.Board(args.io / 'io.kicad_pcb')
    dp = io.path('/USB_CONN_DP', ('R15', '2'), ('J2', '3'))['length_mm']
    dm = io.path('/USB_CONN_DM', ('R14', '2'), ('J2', '2'))['length_mm']
    assert abs(dp - 9.407) < .01 and abs(dm - 20.101) < .01, (dp, dm)
    system = route_si.Board(args.system / 'system.kicad_pcb')
    for contact in ('A6', 'B6'):
        system.path('/USB_DP', ('R2', '2'), ('J1', contact))
    print(f'IO USB R-to-J2 paths {dp:.3f}/{dm:.3f} mm; all route-SI checks pass')


if __name__ == '__main__':
    main()
