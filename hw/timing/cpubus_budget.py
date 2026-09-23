#!/usr/bin/env python3
"""BUS-005: the CPU bus timing budget across the CPU card connector.

    python3 hw/timing/cpubus_budget.py

Both FPGAs are clocked by the main board's 12 MHz oscillator, which drives
CLK12 (chipset) and CPU_CLK (socket) through its own 33 ohm resistor each, so
the two clocks differ only by trace length and by device mismatch. Every bus
signal is launched by a flip-flop on one FPGA and captured on the other.

Setup, for each direction:  launch clock + clock-to-out + board
                             + capture setup + clock skew  <=  70% of 83.3 ns
Hold:  the fastest data path must still arrive after the capture clock edge
       plus the skew.

The FPGA numbers come from nextpnr's place and route of the real designs on
their real pins (tools/fpga.py); they are the worst over all I/O pins, so they
bound the bus pins. The rest are allowances, listed below with their source.
Board lengths come from build/hw/cpubus_lengths.json once the boards are laid
out (hw/tools/kicadgen.py writes it); until then the layout limits below are
used, and the layout check must keep every CPU bus net within them.
"""

import json
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OSS = "/opt/oss-cad-suite/bin"
PERIOD = 1000 / 12
MARGIN = 0.30

# allowances (ns) for what nextpnr does not model
ALLOW = {
    # iCE40 HX global buffer, pad to flip-flop clock; icetime's database
    # puts it at 2.0-2.5 ns on the HX8K die
    "clk_insertion": 3.0,
    # the two FPGAs' insertion delays differ by process, voltage and temperature
    "clk_mismatch": 1.0,
    # output pad driving LVCMOS33 into ~15 pF (pin, connector, trace, other pin)
    "out_pad": 4.0,
    # input pad to fabric (icetime: 0.24 ns)
    "in_pad": 0.5,
    # flip-flop setup inside the fabric; nextpnr's input path ends at the D pin
    "setup": 0.4,
    # fastest possible data path, for hold: clk-to-q + one route to the pad +
    # the output pad + one route from the input pad (datasheet minimums)
    "min_data": 3.0,
}

# layout limits: every CPU bus net, main board + card, and the difference
# between the two clock traces from the oscillator
LIMITS = {"bus_trace_mm": 150.0, "clk_trace_diff_mm": 50.0}
PS_PER_MM = 7.0                 # FR4 stripline, the slow case (microstrip is ~6)
CONNECTOR_NS = 0.1              # PCIe CEM edge connector, ~15 mm of contact
RC_NS = 2.2 * 33 * 15e-12 * 1e9 # 33 ohm series resistor into 15 pF, 10-90%


def io_delays(name):
    """(input pin to flip-flop, flip-flop to output pin) from nextpnr, in ns."""
    d = os.path.join(ROOT, "build", "fpga", name)
    pcf = os.path.join(ROOT, "build", "hw", name + ".pcf")
    if not os.path.exists(os.path.join(d, name + ".json")):
        subprocess.run([sys.executable, os.path.join(ROOT, "tools", "fpga.py"), name], check=True)
    r = subprocess.run([os.path.join(OSS, "nextpnr-ice40"), "--hx8k", "--package", "tq144:4k",
                        "--json", os.path.join(d, name + ".json"), "--pcf", pcf, "--freq", "12",
                        "--seed", "1"], capture_output=True, text=True, check=True)
    # nextpnr prints the table twice (after placement and after routing): use the last
    ins = re.findall(r"Max delay <async>\s+-> posedge [^:]+: ([\d.]+) ns", r.stderr)
    outs = re.findall(r"Max delay posedge [^:]+-> <async>\s*: ([\d.]+) ns", r.stderr)
    return float(ins[-1]), float(outs[-1])


def lengths():
    path = os.path.join(ROOT, "build", "hw", "cpubus_lengths.json")
    if os.path.exists(path):
        with open(path) as f:
            got = json.load(f)
        return max(got["bus_mm"].values()), got["clk_diff_mm"], "extracted from the layout"
    return LIMITS["bus_trace_mm"], LIMITS["clk_trace_diff_mm"], "layout limits (no layout yet)"


def budget(launch, capture, bus_mm, clk_diff_mm):
    """Setup and hold for a signal launched on one FPGA and captured on the other."""
    skew = ALLOW["clk_mismatch"] + clk_diff_mm * PS_PER_MM / 1000
    board = bus_mm * PS_PER_MM / 1000 + CONNECTOR_NS + RC_NS
    items = [
        ("launch clock insertion", ALLOW["clk_insertion"]),
        ("launch flip-flop to pin (nextpnr)", launch[1]),
        ("output pad", ALLOW["out_pad"]),
        ("board: %.0f mm, connector, 33 ohm" % bus_mm, board),
        ("input pad", ALLOW["in_pad"]),
        ("capture pin to flip-flop (nextpnr)", capture[0]),
        ("capture setup", ALLOW["setup"]),
        ("clock skew", skew),
    ]
    # the capture clock is also delayed by its insertion, which only helps;
    # it is left out, so setup is pessimistic by ~2 ns
    total = sum(v for _, v in items)
    hold = ALLOW["min_data"] + CONNECTOR_NS - skew
    return items, total, hold


def main():
    fpga = {"chipset": io_delays("chipset"), "cpucard": io_delays("cpucard")}
    bus_mm, clk_diff_mm, source = lengths()
    limit = PERIOD * (1 - MARGIN)
    bad = 0
    print("CPU bus at 12 MHz (%.1f ns): paths must fit in %.1f ns (%d%% slack); lengths: %s"
          % (PERIOD, limit, MARGIN * 100, source))
    for src, dst in (("cpucard", "chipset"), ("chipset", "cpucard")):
        items, total, hold = budget(fpga[src], fpga[dst], bus_mm, clk_diff_mm)
        print("\n%s -> %s" % (src, dst))
        for what, ns in items:
            print("  %-40s %6.2f ns" % (what, ns))
        ok = total <= limit and hold > 0
        print("  %-40s %6.2f ns -> %.1f ns slack (%.0f%%); hold margin %.2f ns   %s"
              % ("total", total, PERIOD - total, 100 * (PERIOD - total) / PERIOD, hold,
                 "ok" if ok else "FAIL"))
        bad += not ok
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
