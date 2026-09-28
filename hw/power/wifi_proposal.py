#!/usr/bin/env python3
"""Diagnostic: the Wi-Fi 3V3 divider proposal (doc/hardware/wifi-droop-fix-proposal.md).

    python3 hw/power/wifi_proposal.py build/hw/wifi     (~2 min, 32 ngspice runs)

Runs POW-003's deck on the routed board for the fitted R9/R10 (1 %, 100 ppm/C)
and the proposed 0.1 %, 25 ppm/C parts of the same values, over both slot
corners, the 60 % and sourced stress capacitance, 3 and 100 mOhm ESR, and the
358 mA TX load and Espressif's 0.5 A supply requirement (+ LEDs). Each wave is
scaled to the DC corners of wifi_parts.vout_range(). Board files are read
only; nothing here changes the board or clears a gate.
"""
import argparse
import concurrent.futures
from pathlib import Path

import buck
import design as d
import wifi_board
import wifi_ground
import wifi_parts as wp

DIVIDERS = {'fitted': ('C25818', 'C25803'), 'proposed': ('C861412', 'C122538')}


def case(routes, divider, capset, esr, load, corner):
    r5, r3, rgnd, rret = routes
    r1_lcsc, r2_lcsc = DIVIDERS[divider]
    r1, r2 = wp.RESISTORS[r1_lcsc]['value'], wp.RESISTORS[r2_lcsc]['value']
    lo, hi = wp.vout_range(r1_lcsc, r2_lcsc)
    caps = None if capset == '60%' else (
        wp.stress_capacitance(wp.FITTED['C1'], d.VBUS_MAX),
        wp.stress_capacitance(wp.FITTED['C2'], hi), wp.stress_capacitance(wp.FITTED['C3'], hi))
    tag = '_prop_%s_%s_%d_%d' % (divider, 'nom' if caps is None else 'stress',
                                 round(esr * 1e3), round(load * 1e3))
    for attempt in (1, 2, 3):   # spice.run rewrites build/power/.spiceinit per deck; retry a torn read
        try:
            t, vout, _, _ = buck.run_wifi(corner, r5, r3, rgnd, esr=esr, r_board_return=rret, caps=caps,
                                          divider=(r1, r2), i_load=load, tag=tag)
            break
        except SystemExit:
            if attempt == 3:
                raise
    vnom = d.buck_vout(r1, r2)
    return (min(buck.window(t, vout, buck.T_STEP, buck.T_REL)) * lo / vnom, max(vout) * hi / vnom)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('out', type=Path, help='completed Wi-Fi build; read only')
    out = parser.parse_args().out.resolve()
    circuit = wifi_board.topology(out / 'wifi.net')
    r5, r3 = wifi_board.routes(out / 'wifi.kicad_pcb', out / 'fab/order.json', circuit)
    rgnd = wifi_ground.compare(out / 'wifi.kicad_pcb')[0]
    edge = wifi_ground.compare_card_edge(out / 'wifi.kicad_pcb')[0]
    routes = (r5, r3, rgnd, max(edge['buck_to_J1_A'], edge['buck_to_J1_B']))
    loads = (d.WIFI_I_3V3, wp.ESP32_C3['supply_current_min'] + d.WIFI_I_LEDS)
    cases = [(div, capset, esr, load, corner) for div in DIVIDERS for capset in ('60%', 'stress')
             for esr in (0.003, 0.100) for load in loads for corner in ('typical', 'worst')]
    with concurrent.futures.ThreadPoolExecutor(8) as pool:
        results = list(pool.map(lambda c: case(routes, *c), cases))
    for div in DIVIDERS:
        lo, hi = wp.vout_range(*DIVIDERS[div])
        rows = [(c, r) for c, r in zip(cases, results) if c[0] == div]
        worst_min = min(r[0] for _, r in rows)
        worst_max = max(r[1] for _, r in rows)
        print('%s R9/R10 %s/%s: DC %.3f..%.3f V; worst burst minimum %.3f V (%+.3f), '
              'worst maximum %.3f V (%+.3f)' % (div, *DIVIDERS[div], lo, hi, worst_min,
                                                  worst_min - wp.ESP32_C3['vdd_min'], worst_max,
                                                  wp.ESP32_C3['vdd_max'] - worst_max))
        for (_, capset, esr, load, corner), (vmin, vmax) in rows:
            print('  %-6s ESR %3.0f mOhm %3.0f mA %-7s min %.3f V  max %.3f V' % (
                capset, esr * 1e3, load * 1e3, corner, vmin, vmax))
    print('Diagnostic only: POW-003 F5-F8 still require guaranteed ESR, capacitance, '
          'contact and load bounds.')


if __name__ == '__main__':
    main()
