"""Timing observations and conditional envelopes for the real WiFi SPI stages.

IBIS supplies pin loading and output waveforms, not an A-to-Y transfer model.
These helpers preserve that distinction. They neither invent ESP timing limits
nor turn a fixture-anchored calculation into a datasheet-only guarantee.
"""
import math


def crossings(t, v, threshold, edge):
    """Piecewise-linear directed crossings, retaining every re-entry."""
    result = []
    for a, b, va, vb in zip(t[:-1], t[1:], v[:-1], v[1:]):
        crossed = va < threshold <= vb if edge == 'rise' else va > threshold >= vb
        if crossed:
            result.append(float(a + (b - a) * (threshold - va) / (vb - va)))
    return result


def input_observation(t, v, launch, stop, edge):
    """Local TI input-die voltage; no further ground subtraction is applied.

    Operating slew uses the complete TTL band. The published propagation
    fixture separately specifies VI=3V and tr/tf <=2.5ns (SCES223U Fig6-2).
    A 10--90% observation tests that fast fixture stimulus condition; it is
    not substituted for the recommended whole-band operating slew check.
    """
    pairs = [(float(a), float(b)) for a, b in zip(t, v) if launch <= a <= stop]
    if len(pairs) < 2:
        raise ValueError('missing TI input waveform interval')
    tt, vv = zip(*pairs)
    lower, upper = (.8, 2.) if edge == 'rise' else (2., .8)
    entry, exit_ = crossings(tt, vv, lower, edge), crossings(tt, vv, upper, edge)
    vm = crossings(tt, vv, 1.5, edge)
    first, last = crossings(tt, vv, .3 if edge == 'rise' else 2.7, edge), crossings(
        tt, vv, 2.7 if edge == 'rise' else .3, edge)
    final_valid = vv[-1] >= 2. if edge == 'rise' else vv[-1] <= .8
    complete = bool(entry and exit_ and vm and exit_[-1] >= entry[0] and final_valid)
    transit = (exit_[-1] - entry[0]) * 1e9 if complete else None
    fixture = (last[-1] - first[0]) * 1e9 if first and last else None
    return {
        'edge': edge, 'complete': complete,
        'input_vm_last_ns': (vm[-1] - launch) * 1e9 if vm else None,
        'input_vm_crossings': len(vm), 'whole_ttl_band_ns': transit,
        'recommended_rate_ok': complete and transit <= 12.,
        'fixture_10_90_ns': fixture,
        'published_fast_fixture_observed': fixture is not None and fixture <= 2.5,
        'scope': 'Local input-die waveform; VM1.5V, TTL .8..2V. Fast-slew observation alone does not verify every VI3V fixture condition.',
    }


def anchored_upper(input_ns, output_settled_ns, fixture_vm_ns, tpd_max_ns=4.7):
    """Conditional fixture-anchored upper latency; no internal transfer claim."""
    values = (input_ns, output_settled_ns, fixture_vm_ns, tpd_max_ns)
    if any(not math.isfinite(x) or x < 0 for x in values):
        raise ValueError('invalid cascade timing observation')
    return input_ns + tpd_max_ns + max(0., output_settled_ns - fixture_vm_ns)


def timing_envelope(delays, qualified_hz=3e6, held_lead_ns=1000 / 3,
                    held_hold_ns=1000 / 3):
    """Worst independent path alignment, allowing zero as lower latency.

    CS lead/hold derives from audited held ROM/kernel sequences. Automatic
    unheld CS has only half a period lead and must fail this strict test.
    MOSI setup/hold and clock width are observations with no ESP numerical
    requirement invented. ESP response/MISO timing remains a separate gap.
    """
    if set(delays) != {'SCK', 'MOSI', 'CS'}:
        raise ValueError('all three actual cascade paths are required')
    if not math.isfinite(qualified_hz) or qualified_hz <= 0:
        raise ValueError('invalid SPI clock')
    if any(not math.isfinite(x) or x < 0 for x in (held_lead_ns, held_hold_ns)):
        raise ValueError('invalid held-CS source timing')
    for bounds in delays.values():
        if len(bounds) != 2 or any(not math.isfinite(x) or x < 0 for x in bounds):
            raise ValueError('invalid path latency interval')
        if bounds[0] > bounds[1]:
            raise ValueError('reversed path latency interval')
    half = 1e9 / (2 * qualified_hz)
    sck, mosi, cs = delays['SCK'], delays['MOSI'], delays['CS']
    lead = held_lead_ns + sck[0] - cs[1]
    hold = held_hold_ns + cs[0] - sck[1]
    return {
        'qualified_hz': qualified_hz, 'half_period_ns': half,
        'received_cs_lead_lower_ns': lead, 'received_cs_hold_lower_ns': hold,
        'published_cs_requirement_ok': lead > half and hold > half,
        'received_mosi_setup_lower_ns': half + sck[0] - mosi[1],
        'received_mosi_hold_lower_ns': half + mosi[0] - sck[1],
        'received_clock_width_lower_ns': half - (sck[1] - sck[0]),
        'numeric_esp_setup_hold_response_qualified': False,
        'datasheet_only_guarantee': False,
        'scope': 'Conditional independent latency intervals; missing ESP numeric limits retained.',
    }
