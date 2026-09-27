#!/usr/bin/env python3
"""Routed main-board 5 V copper sensitivity at the stated fabrication corner.

The 80% width is JLC's published trace-width tolerance. The 90% finished
copper thickness is an engineering allowance, not a vendor minimum. The
20 um via barrel is a Class 2 minimum and 1.76 mm is the high-side board
thickness. Pad copper is idealized and pours are omitted by copper.py; these
estimates alone do not certify either electrical or thermal compliance.
"""

import sys

import pcbnew

import copper


def evaluate(board, temperature_c):
    copper.TRACE_WIDTH_FACTOR = 0.80
    copper.RHO = 17e-6 * (1 + copper.COPPER_ALPHA_PER_C *
                          (temperature_c - copper.REFERENCE_C))
    copper.THICKNESS = {"outer": 0.0348 * 0.90, "inner": 0.0174 * 0.90}
    copper.VIA_PLATING = 0.020
    copper.BOARD_THICKNESS = 1.76
    up = copper.effective_resistance(board, "/5V_SYS", ("U2", "6"), ("R4", "1"))
    slots = [up + copper.effective_resistance(
        board, "/+5V", ("R4", "2"), ("F%d00" % (i + 1), "1"))
        for i in range(1, 7)]
    buck = [copper.effective_resistance(board, "/5V_SYS", ("U2", "6"), ("U3", pin))
            for pin in ("1", "4")]
    return up, slots, buck


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else "build/hw/main/main.kicad_pcb"
    board = pcbnew.LoadBoard(path)
    for temperature_c in (70.0, 100.0):
        up, slots, buck = evaluate(board, temperature_c)
        print("%.0f C, 80%% width, 90%% copper, 20 um barrel, 1.76 mm board:" % temperature_c)
        print("  U2:6 to R4:1 %.3f mOhm; slot max %.3f mOhm; buck max %.3f mOhm" %
              (up, max(slots), max(buck)))
        if max(slots + buck) > 20.0:
            raise SystemExit("FAIL modeled 5V_SYS copper exceeds 20 mOhm")
    print("MODEL PASS to 100 C; thermal and fabricated-copper validation remain open")


if __name__ == "__main__":
    main()
