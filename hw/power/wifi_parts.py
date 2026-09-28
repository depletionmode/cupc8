"""Manufacturer data for the Wi-Fi card's fitted power parts (POW-003, WC-005, WC-010).

Every number here is copied from a cited manufacturer document or
distributor listing (retrieved 2026-09-28), keyed by the LCSC part the
netlist fits. `binding_errors()` fails POW-003 if the netlist's LCSC fields
drift from the parts this data describes.

What the sources guarantee and what they only show as typical is kept
apart: a `None` guarantee means the manufacturer publishes no bound, and the
gate that needs it stays red. Typical curves feed the stress corner only.
See doc/hardware/wifi-droop-fix-proposal.md for the audit.
"""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from kicadgen import parse

SOURCES = {
    'samsung-cl21a226maqnnn': (
        'Samsung Electro-Mechanics CL21A226MAQNNN# product page, embedded characteristic data '
        '(DC bias, TCC, |Z|/R; "Precise" model, 25 C, typical)',
        'https://product.samsungsem.com/mlcc/CL21A226MAQNNN.do'),
    'samsung-cl21a226maqnnn-spec': (
        'Samsung Electro-Mechanics SpecSheet_CL21A226MAQNNN, issued MAY.09.2024 '
        '(POST /part/download.do, type=specsheet)',
        'https://product.samsungsem.com/mlcc/CL21A226MAQNNN.do'),
    'yageo-cc0603krx7r9bb104': (
        'YAGEO CC0603KRX7R9BB104 part specsheet (ESR plots are simulation, '
        '"unspecified variations of ESR")',
        'https://yageogroup.com/download/specsheet/CC0603KRX7R9BB104'),
    'ti-tlv62569': (
        'TI TLV62569 datasheet SLVSDG1C (Dec 2016, rev. Oct 2017): 6.3, 6.4, 6.5, '
        'Fig. 3, Fig. 10, Table 4, 8.2.2.5',
        'https://www.ti.com/lit/ds/symlink/tlv62569.pdf'),
    'espressif-esp32-c3-mini-1': (
        'Espressif ESP32-C3-MINI-1 & MINI-1U Datasheet v2.2: Tables 6-1, 6-2, 6-4',
        'https://documentation.espressif.com/esp32-c3-mini-1_datasheet_en.pdf'),
    'espressif-esp32-c3': (
        'Espressif ESP32-C3 Series Datasheet v2.4: Tables 5-1, 5-2 (note 2: eFuse writes)',
        'https://www.espressif.com/sites/default/files/documentation/esp32-c3_datasheet_en.pdf'),
    'jlc-parts': (
        'JLCPCB/LCSC parts library listing (selectSmtComponentList API), '
        'resistance tolerance and TCR per LCSC number',
        'https://jlcpcb.com/parts'),
}

# ref -> LCSC number this data describes (hw/boards/wifi.py LCSC fields)
FITTED = {'U1': 'C2911374', 'U2': 'C141836', 'L1': 'C167747', 'C1': 'C45783',
          'C2': 'C45783', 'C3': 'C14663', 'R9': 'C25818', 'R10': 'C25803'}

CAPACITORS = {
    'C45783': dict(
        mpn='CL21A226MAQNNNE', source='samsung-cl21a226maqnnn-spec', nominal=22e-6,
        # guaranteed by the spec sheet
        tolerance=0.20, tcc=0.15,             # X5R, -55..85 C, no bias
        df_max_120hz=0.10,                    # 120 Hz, 0.5 Vrms
        life_c_change=0.125, life_df_max=0.20,  # high-temperature resistance test
        status='NRND; replacement CL21A226MAYNNN#',
        # no maximum ESR at the 1.5 MHz switching band and no minimum
        # capacitance under DC bias are published: both only as typical curves
        esr_max=None, min_effective_c=None,
        # typical curves from the product page data (volts: fractional change)
        dcbias_typ={3.0: -0.2812, 3.3: -0.3229, 3.44: -0.3417, 3.6: -0.3625,
                    4.0: -0.4105, 5.0: -0.5130, 5.25: -0.5345, 5.5: -0.5549},
        esr_typ={1e4: 0.0222, 1e5: 0.00434, 5e5: 0.00268, 1.5e6: 0.00388,
                 1e7: 0.0119, 1e8: 0.0446},
        acv_small_signal_typ=-0.2301),        # at 10 mVrms vs the 0.5 Vrms test level
    'C14663': dict(
        mpn='CC0603KRX7R9BB104', source='yageo-cc0603krx7r9bb104', nominal=100e-9,
        tolerance=0.10, tcc=0.15, df_max=0.035,
        esr_max=None, min_effective_c=None, dcbias_typ={}),
}

RESISTORS = {  # tolerance and TCR (ppm/C) per the LCSC listing
    'C25818': dict(mpn='0603WAF4533T5E', value=453e3, tolerance=0.01, tcr=100e-6),
    'C25803': dict(mpn='0603WAF1003T5E', value=100e3, tolerance=0.01, tcr=100e-6),
    # proposed (doc/hardware/wifi-droop-fix-proposal.md), not fitted
    'C861412': dict(mpn='RT0603BRD07453KL', value=453e3, tolerance=0.001, tcr=25e-6),
    'C122538': dict(mpn='RT0603BRD07100KL', value=100e3, tolerance=0.001, tcr=25e-6),
}
RESISTOR_T_REF, RESISTOR_T_MAX = 25.0, 100.0   # tolerance at 25 C; card copper <= Tj limit

TLV62569 = dict(
    source='ti-tlv62569', vfb_min=0.588, vfb_max=0.612,   # 6.5: VIN 5 V, TJ = 25 C only
    vfb_temp_typ=0.003,        # Fig. 3: typical FB accuracy -40..125 C within +-0.3 %; no guarantee
    cout_min=10e-6, cout_max=47e-6,   # 8.2.2.5 and Table 4 (2.2 uH, VOUT >= 1.8 V)
    ti_ceff_range=(-0.50, 0.20))      # Table 4 note 2: capacitance TI anticipates

ESP32_C3 = dict(
    source='espressif-esp32-c3-mini-1', vdd_min=3.0, vdd_max=3.6, vdd_abs_max=3.6,
    supply_current_min=0.5,     # Table 6-2: current the external supply must deliver
    tx_peak_typ_25c=0.350,      # Table 6-4: 802.11b 20.5 dBm, 100 % duty, 3.3 V, 25 C
    efuse_write_vdd_max=3.3,    # chip datasheet Table 5-2 note 2
    i_max=None)                 # no maximum current over temperature/process published


def netlist_lcsc(path):
    """{ref: LCSC field} for every component in a KiCad netlist."""
    out = {}

    def walk(node):
        if not isinstance(node, list) or not node:
            return
        if node[0] == 'comp':
            ref = lcsc = None
            for item in node:
                if isinstance(item, list) and item[:1] == ['ref']:
                    ref = item[1]
                if isinstance(item, list) and item[:1] == ['fields']:
                    for field in item[1:]:
                        if isinstance(field, list) and ['name', 'LCSC'] in field:
                            lcsc = field[-1]
            if ref:
                out[ref.strip('"')] = lcsc.strip('"') if isinstance(lcsc, str) else lcsc
            return
        for item in node:
            walk(item)

    walk(parse(Path(path).read_text()))
    return out


def binding_errors(path):
    """[(ref, expected LCSC, netlist LCSC)] where the data here no longer applies."""
    fitted = netlist_lcsc(path)
    return [(ref, want, fitted.get(ref)) for ref, want in sorted(FITTED.items())
            if fitted.get(ref) != want]


def resistor_drift(lcsc):
    """Worst fractional error at any board temperature: tolerance + TCR x dT."""
    r = RESISTORS[lcsc]
    return r['tolerance'] + r['tcr'] * (RESISTOR_T_MAX - RESISTOR_T_REF)


def vout_range(r1_lcsc=None, r2_lcsc=None):
    """Wi-Fi 3V3 DC extremes (lo, hi): VFB 25 C limits widened by TI's typical
    temperature span, and each divider resistor at its tolerance plus TCR
    drift in the direction that hurts."""
    r1 = RESISTORS[r1_lcsc or FITTED['R9']]
    r2 = RESISTORS[r2_lcsc or FITTED['R10']]
    t1, t2 = resistor_drift(r1_lcsc or FITTED['R9']), resistor_drift(r2_lcsc or FITTED['R10'])
    k = TLV62569['vfb_temp_typ']
    lo = TLV62569['vfb_min'] * (1 - k) * (1 + r1['value'] * (1 - t1) / (r2['value'] * (1 + t2)))
    hi = TLV62569['vfb_max'] * (1 + k) * (1 + r1['value'] * (1 + t1) / (r2['value'] * (1 - t2)))
    return lo, hi


def stress_capacitance(lcsc, v_bias):
    """Effective capacitance at the sourced stress corner: minimum tolerance,
    the manufacturer's *typical* DC-bias loss at v_bias (next higher tabulated
    voltage), full TCC and the life-test drift. Not a guarantee."""
    c = CAPACITORS[lcsc]
    bias = 0.0
    if c['dcbias_typ']:
        above = [v for v in sorted(c['dcbias_typ']) if v >= v_bias]
        bias = c['dcbias_typ'][above[0] if above else max(c['dcbias_typ'])]
    return (c['nominal'] * (1 - c['tolerance']) * (1 + bias) * (1 - c['tcc']) *
            (1 - c.get('life_c_change', 0.0)))


def guaranteed(field, refs=('C1', 'C2', 'C3')):
    """True only if every fitted part's manufacturer data guarantees `field`."""
    return all(CAPACITORS[FITTED[ref]].get(field) is not None for ref in refs)


def load_envelope_bounded():
    return ESP32_C3['i_max'] is not None


def citations():
    return ['%s: %s <%s>' % (key, title, url) for key, (title, url) in sorted(SOURCES.items())]
