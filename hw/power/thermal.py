#!/usr/bin/env python3
"""THM-001: regulator junction temperatures at 40 C ambient (Tj <= 100 C).

    python3 hw/power/thermal.py

Tj = 40 C + P x theta_JA, with the datasheet theta_JA (JEDEC boards; our
copper will usually do better, but nothing checks that yet). Each regulator
at the corner that heats it most:

  TLV62569 (3V3)  loss from the datasheet RDS(on) (hot, see design.py),
                  a switching-loss estimate and the control current, at both
                  5V_SYS corners; two loads: the M1 maximum (four cards),
                  and that plus slots 5-6 each drawing their 300 mA of +3V3
  TLV62569 (Wi-Fi card)  the same loss model at Espressif's TX current,
                  rated at 100 % duty (a long transfer or an RF test), from
                  the slot's +5V at both of its corners
  RT9013 (1V2)    (3V3 max - 1V2 min) x 40 mA, main board and CPU card
  TPS61023 (IO card keyboard boost)  the same kind of loss model, at 500 mA
                  and the highest set point, from the worst-case card input
  TPS63802 (GPU card HDMI buck-boost)  all it loses at its budget
                  efficiency (design.GPUB_ETA), at 55 mA and its highest output
  input eFuse     I^2 x RON max at the most current it passes without
                  limiting (its minimum limit)
  TPS2553-1       the IO card's keyboard port at 500 mA, RDS(on) hot
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))

import budget
import design as d
from spice import Checks


def wifi_thermal_terms(r5, r3, rgnd, r_input_return=0.0):
    """Modeled watts and total junction-rise budget for routed TX heat.

    External copper and contact heat need their own board-to-junction transfer
    coefficients; a JEDEC buck self-heating theta_JA is not one of those.
    I²R uses constant TX current, not a bound on switching or RF ripple RMS.
    """
    if min(r5, r3, rgnd, r_input_return) < 0:
        raise ValueError('routed resistances must be nonnegative')
    vin = budget.chain('worst')['wifi_in']
    iout = d.WIFI_I_3V3
    internal_w = buck_loss(vin, iout)
    ibuck = (iout * d.wifi_vout_range()[1] + internal_w) / vin
    copper_w = iout ** 2 * (r3 + rgnd) + ibuck ** 2 * (r5 + r_input_return)
    # Espressif's 350 mA TX entry is measured at 25 C. It is a diagnostic
    # operating point, not a guaranteed current maximum at this 40 C corner.
    esp_w = d.ESP32_VDD_MAX * d.ESP32_I_TX
    rise_budget_c = d.TJ_LIMIT_C - d.AMBIENT_C
    # The unresolved mated J1 GND contact is upstream of the buck and
    # carries its input current, not the full ESP output current.
    return internal_w, copper_w, esp_w, ibuck ** 2, rise_budget_c


def wifi_external_allowance(terms, r_contact, theta_buck, theta_copper, theta_contact):
    """Conditional maximum ESP-to-buck C/W, for all stated thermal paths."""
    if min(r_contact, theta_buck, theta_copper, theta_contact) < 0:
        raise ValueError('resistance and thermal transfers must be nonnegative')
    internal_w, copper_w, esp_w, contact_w_per_ohm, rise_budget_c = terms
    return (rise_budget_c - internal_w * theta_buck - copper_w * theta_copper -
            r_contact * contact_w_per_ohm * theta_contact) / esp_w


def wifi_coupling_budget(r5, r3, rgnd, r_input_return=0.0):
    """Legacy conditional scenario: external copper transfers as buck theta_JA.

    The ESP's 25 C TX electrical input is counted as local heat. All estimated
    copper I²R loss is assigned the buck's JEDEC self-heating coefficient.
    This is a sensitivity point, not a board thermal upper bound.
    """
    terms = wifi_thermal_terms(r5, r3, rgnd, r_input_return)
    internal_w, copper_w, esp_w, _, _ = terms
    theta = d.BUCK_THETA_JA[d.WIFI_BUCK_PACKAGE]
    allowance = wifi_external_allowance(terms, 0, theta, theta, theta)
    return internal_w + copper_w, copper_w, esp_w, allowance


def wifi_card(out):
    import wifi_board
    import wifi_ground
    import json
    import boardevidence
    from boardcheck import check_report
    out = Path(out)
    boardevidence.validate('wifi', out)
    check_report(json.loads((out / 'drc.json').read_text()), 'drc')
    circuit = wifi_board.topology(out / 'wifi.net')
    r5, r3 = wifi_board.routes(out / 'wifi.kicad_pcb', out / 'fab/order.json', circuit)
    rgnd, coarse, fine, discrepancy = wifi_ground.compare(out / 'wifi.kicad_pcb')
    edge, _, _, edge_errors = wifi_ground.compare_card_edge(
        out / 'wifi.kicad_pcb')
    r_input_return = max(edge['buck_to_J1_A'], edge['buck_to_J1_B'])
    buck_w, copper_w, esp_w, allowance = wifi_coupling_budget(
        r5, r3, rgnd, r_input_return)
    terms = wifi_thermal_terms(r5, r3, rgnd, r_input_return)
    internal_w, _, _, contact_w_per_ohm, rise_budget_c = terms
    c = Checks('WC-010 Wi-Fi board local thermal coupling at %.0f C ambient' % d.AMBIENT_C)
    c.info('routed copper', '%.1f mOhm +5V, %.1f mOhm 3V3, %.1f mOhm local GND, '
           '%.1f mOhm buck-to-J1 GND; %d GND vias' %
           (1e3 * r5, 1e3 * r3, 1e3 * rgnd, 1e3 * r_input_return, coarse[1]))
    c.info('GND mesh', '0.25/0.125 mm %.1f/%.1f mOhm; discrepancy %.0f%%' %
           (1e3 * coarse[0], 1e3 * fine[0], 100 * discrepancy))
    c.info('J1 GND return', 'U1.1 to J1 A/B %.1f/%.1f mOhm; U2.2 to J1 A/B '
           '%.1f/%.1f mOhm fixed-width path scenarios; maximum mesh difference %.1f%%' %
           (1e3 * edge['esp_to_J1_A'], 1e3 * edge['esp_to_J1_B'],
            1e3 * edge['buck_to_J1_A'], 1e3 * edge['buck_to_J1_B'],
            100 * max(edge_errors.values())))
    ibuck = (d.WIFI_I_3V3 * d.wifi_vout_range()[1] + internal_w) / \
        budget.chain('worst')['wifi_in']
    c.info('separate J1 return heat scenarios', '%.1f/%.1f mW at %.1f mA '
           'ESP output on A/B; %.1f/%.1f mW at %.1f mA buck input on A/B. '
           'The worst buck-input case is included above; ESP full-return '
           'paths share copper with it, so their powers are not additive. '
           'Shared-plane cross terms and mated contacts remain unbounded' %
           (1e3 * d.WIFI_I_3V3 ** 2 * edge['esp_to_J1_A'],
            1e3 * d.WIFI_I_3V3 ** 2 * edge['esp_to_J1_B'],
            1e3 * d.WIFI_I_3V3,
            1e3 * ibuck ** 2 * edge['buck_to_J1_A'],
            1e3 * ibuck ** 2 * edge['buck_to_J1_B'], 1e3 * ibuck))
    c.info('coupling budget', 'buck + allocated copper %.0f mW (of which copper %.0f mW); '
           'ESP TX heat scenario %.0f mW; conditional ESP-to-buck transfer <= %.1f C/W '
           'if external copper uses buck theta_JA' %
           (1e3 * buck_w, 1e3 * copper_w, 1e3 * esp_w, allowance))
    c.info('thermal balance', '%.1f mW x theta_buck + %.1f mW x theta_copper '
           '+ (%.1f mW/ohm x R_contact) x theta_contact '
           '+ %.0f mW x theta_ESP <= %.1f C' %
           (1e3 * internal_w, 1e3 * copper_w,
            1e3 * contact_w_per_ohm, 1e3 * esp_w, rise_budget_c))
    c.info('heat scope', 'route I²R uses constant %.1f mA TX load; return-current RMS ripple, '
           'capacitor ESR heat and board thermal transfers are not bounded' %
           (1e3 * d.WIFI_I_3V3))
    theta = d.BUCK_THETA_JA[d.WIFI_BUCK_PACKAGE]
    for r_contact in (0.0, 0.2, 0.33, 0.4):
        c.info('contact %.2f ohm scenario' % r_contact,
               'extra return heat %.1f mW; conditional theta_ESP <= %.2f C/W '
               'if theta_buck = theta_copper = theta_contact = %.1f C/W' %
               (1e3 * contact_w_per_ohm * r_contact,
                wifi_external_allowance(terms, r_contact, theta, theta, theta), theta))
    c.check('T4b', 'conditional buck junction if copper uses JEDEC theta_JA, no ESP transfer',
            tj(buck_w, d.BUCK_THETA_JA[d.WIFI_BUCK_PACKAGE]),
            d.TJ_LIMIT_C, '<=', 'C', fmt='%.1f')
    c.check('T4m', 'GND thermal copper path mesh discrepancy <= 10%', discrepancy, 0.10, '<=', '', fmt='%.3f')
    c.check('T4e', 'J1 GND return path mesh discrepancy <= 10%',
            max(edge_errors.values()), 0.10, '<=', '', fmt='%.3f')
    # The layout's board and air path cannot be inferred from JEDEC theta_JA.
    # A validated thermal solver or measurement must bound cross-coupling.
    c.check('T4r', 'extra return resistance and buck/copper/contact thermal transfers bounded',
            0, 1, '>=', '', fmt='%d')
    c.check('T4c', 'measured or calibrated ESP-to-buck thermal transfer bound supplied', 0, 1, '>=', '', fmt='%d')
    import wifi_parts   # Espressif publishes only a 25 C typical TX peak (wifi_parts.ESP32_C3)
    c.check('T4p', 'ESP and other 3V3 load power bounded at the 40 C full-TX corner',
            int(wifi_parts.load_envelope_bounded()), 1, '>=', '', fmt='%d')
    return c.done()


def buck_loss(vin, iout, vout=3.3):
    dcy = vout / vin
    cond = iout ** 2 * d.BUCK_RDS_HOT * (dcy * d.BUCK_RHS + (1 - dcy) * d.BUCK_RLS)
    sw = vin * iout * 2 * d.BUCK_T_EDGE * d.BUCK_FSW
    return cond + sw + d.BUCK_IQ_LOSS


def boost_loss(vin, iout):
    """A TPS61023's IC loss at its highest set point: RDS(on) hot
    (x BUCK_RDS_HOT, as the buck), switching edges at 1 MHz, the control. The
    low side carries the inductor current for D, the high side for 1 - D."""
    vout = d.iob_vout_range()[2]
    dcy = 1 - vin / vout
    il = vout * iout / (d.IOB_ETA * vin)
    cond = il ** 2 * d.BUCK_RDS_HOT * (dcy * d.IOB_RLS + (1 - dcy) * d.IOB_RHS)
    sw = vout * il * 2 * d.BUCK_T_EDGE * 1.0e6
    return cond + sw + d.BUCK_IQ_LOSS


def tj(p, theta):
    return d.AMBIENT_C + p * theta


def main():
    c = Checks("THM-001 regulator junction temperatures at %.0f C ambient (hw/power/thermal.py)" % d.AMBIENT_C)
    lim = d.TJ_LIMIT_C
    theta_buck = d.BUCK_THETA_JA[d.BUCK_PACKAGE]
    v5s = (budget.chain("worst")["v5"], d.VBUS_MAX)
    m1 = budget.i_3v3()
    full = m1 + d.FUTURE_SLOTS * d.SLOT_3V3_MAX
    for ident, what, i in (("T1", "M1 maximum (4 cards)", m1),
                           ("T2", "M1 + slots 5-6 at 300 mA +3V3 each", full)):
        p = max(buck_loss(v, i) for v in v5s)
        c.check(ident, "TLV62569%s 3V3 buck, %s (%.0f mA): %.0f mW x %.0f C/W" % (
            d.BUCK_PACKAGE, what, 1e3 * i, 1e3 * p, theta_buck), tj(p, theta_buck), lim, "<=", "C", fmt="%.1f",
            fix="TLV62569PDDCR (design.BUCK_PACKAGE = 'DDC'), or cap slots 5-6's +3V3")
    # what the 3V3 can carry on this package, and on the others
    for pkg, th in sorted(d.BUCK_THETA_JA.items()):
        imax = 0.0
        while tj(max(buck_loss(v, imax + 0.01) for v in v5s), th) <= lim and imax < 2.0:
            imax += 0.01
        c.info("TLV62569%s" % pkg, "theta_JA %.0f C/W: Tj <= %.0f C up to %.2f A of 3V3" % (th, lim, imax))

    v3_hi = d.buck_vout_range()[1]
    p = (v3_hi - 1.2 * (1 - d.RT9013_TOL)) * d.I_1V2_MAX + v3_hi * d.RT9013["IQ"]
    c.check("T3", "RT9013 1V2 LDO (main board; the CPU card's is the same): %.0f mW x %.0f C/W" % (
        1e3 * p, d.RT9013_THETA_JA), tj(p, d.RT9013_THETA_JA), lim, "<=", "C", fmt="%.1f")

    bad = d.wifi_board_mismatches()
    for ref, want, got in bad:
        c.info(ref, "hw/boards/wifi.py has %s, these checks model %s (design.WIFI_BOARD)" % (got, want))
    c.check("T0", "Wi-Fi card regulator parts in hw/boards/wifi.py that differ from the model", len(bad), 0, "<=",
            "", fmt="%d")
    v_card = (budget.chain("worst")["wifi_in"], d.VBUS_MAX)
    p = max(buck_loss(v, d.WIFI_I_3V3) for v in v_card)
    theta_wifi = d.BUCK_THETA_JA[d.WIFI_BUCK_PACKAGE]
    c.check("T4", "TLV62569%s Wi-Fi card buck (hw/boards/wifi.py), %.0f mA: %.0f mW x %.0f C/W" % (
        d.WIFI_BUCK_PACKAGE, 1e3 * d.WIFI_I_3V3, 1e3 * p, theta_wifi), tj(p, theta_wifi), lim, "<=", "C",
        fmt="%.1f")

    v_io = budget.chain("worst")["io_in"]
    p = boost_loss(v_io, d.I_KEYBOARD)
    c.check("T5", "TPS61023 IO card keyboard boost, 500 mA at %.2f V from %.2f V in: %.0f mW x %.0f C/W" % (
        d.iob_vout_range()[2], v_io, 1e3 * p, d.IOB_THETA_JA), tj(p, d.IOB_THETA_JA), lim, "<=", "C",
        fmt="%.1f")

    # the GPU card's buck-boost: everything its efficiency loses, all in the IC
    bad = d.gpu_board_mismatches()
    for ref, want, got in bad:
        c.info(ref, "hw/boards/gpu.py has %s, these checks model %s (design.GPU_BOARD)" % (got, want))
    c.check("T0g", "GPU card HDMI +5V parts in hw/boards/gpu.py that differ from the model", len(bad), 0, "<=",
            "", fmt="%d")
    vout = d.gpub_vout_range()[2]
    p = vout * d.I_HDMI_PIN * (1 / d.GPUB_ETA - 1)
    c.check("T6", "TPS63802 GPU card HDMI buck-boost, 55 mA at %.2f V, %.0f %% efficient: %.0f mW x %.0f C/W" % (
        vout, 100 * d.GPUB_ETA, 1e3 * p, d.GPUB_THETA_JA), tj(p, d.GPUB_THETA_JA), lim, "<=", "C", fmt="%.1f")

    _, _, hi = d.insw_ilim()
    p = hi ** 2 * d.INSW_RON_MAX
    c.check("T8", "%s input eFuse at its maximum limit %.2f A before limiting: "
            "%.0f mW x %.1f C/W" % (d.INSW_PART, hi, 1e3 * p, d.INSW_THETA_JA), tj(p, d.INSW_THETA_JA), lim,
            "<=", "C", fmt="%.1f")
    p = d.I_KEYBOARD ** 2 * d.IOSW_RON_MAX
    c.check("T9", "TPS2553-1 IO card keyboard port, 500 mA: %.0f mW x %.0f C/W" % (1e3 * p, d.IOSW_THETA_JA),
            tj(p, d.IOSW_THETA_JA), lim, "<=", "C", fmt="%.1f")
    return c.done()


if __name__ == "__main__":
    if sys.argv[1:2] == ['wifi-card']:
        if len(sys.argv) != 3:
            sys.exit('usage: thermal.py wifi-card board-build-directory')
        sys.exit(wifi_card(sys.argv[2]))
    if sys.argv[1:2] == ['bind']:
        import thermal_bind
        sys.exit(thermal_bind.main(sys.argv[2:]))
    if sys.argv[1:2] == ['rp2040']:
        # a card's whole thermal row: THM-001, then its RP2040 package bound
        import rp2040_thermal
        global_rc = main()
        sys.exit(rp2040_thermal.main(sys.argv[2:]) or global_rc)
    if sys.argv[1:2] == ['board']:
        # the main board's or CPU card's whole thermal row: THM-001, then the
        # iCE40 1V2 and (main) HT7533 standby rows
        import board_thermal
        global_rc = main()
        sys.exit(board_thermal.main(sys.argv[2:]) or global_rc)
    if len(sys.argv) != 1:
        sys.exit('usage: thermal.py [wifi-card DIR | bind BOARD DIR [--binding-only] | rp2040 BOARD DIR'
                 ' | board main|cpu DIR]')
    sys.exit(main())
