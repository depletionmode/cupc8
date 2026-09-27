#!/usr/bin/env python3
"""Track/via resistance sensitivity for the isolated main power trial.

This omits zones, pad/contact resistance and conductor-temperature coupling.
It reports scenarios; it does not qualify the PCB for fabrication.
"""

import sys

import pcbnew

import copper


def row(board, temperature, barrel):
    copper.TRACE_WIDTH_FACTOR = 0.80
    copper.RHO = 17e-6 * (1 + copper.COPPER_ALPHA_PER_C *
                          (temperature - copper.REFERENCE_C))
    copper.THICKNESS = {"outer": 0.0249, "inner": 0.0114}
    copper.VIA_PLATING = barrel / 1000
    copper.BOARD_THICKNESS = 1.76

    def r(net, a, z):
        return copper.effective_resistance(board, net, a, z)

    up = r("/5V_SYS", ("U2", "6"), ("R4", "1"))
    slots = [up + r("/+5V", ("R4", "2"), ("F%d00" % (i + 1), "1"))
             for i in range(1, 7)]
    buck = [r("/5V_SYS", ("U2", "6"), ("U3", p)) for p in ("1", "4")]
    input_a = r("/VBUS", ("J1", "A4B9"), ("F1", "1"))
    input_b = r("/VBUS_F", ("F1", "2"), ("U2", "5"))
    return up, slots, buck, input_a, input_b


def main():
    board = pcbnew.LoadBoard(sys.argv[1] if len(sys.argv) > 1 else
                             "build/hw/main/main.kicad_pcb")
    for temp, barrel in ((70, 20), (100, 20), (100, 15), (115, 20), (115, 15)):
        up, slots, buck, input_a, input_b = row(board, temp, barrel)
        print("%3d C, %2d um via: U2-R4 %.3f; far slot %.3f; "
              "U3 VIN %.3f/%.3f; J1-F1 %.3f; F1-U2 %.3f; "
              "input positive sum %.3f mOhm" %
              (temp, barrel, up, max(slots), *buck, input_a, input_b,
               input_a + input_b))
    print("SENSITIVITY ONLY: no zone, pad/contact, copper-minimum or thermal qualification")


if __name__ == "__main__":
    main()
