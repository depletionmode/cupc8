#!/usr/bin/env python3
"""Build both FPGA designs for the iCE40HX4K-TQ144 and check them.

    python3 tools/fpga.py [chipset|cpucard]
    python3 tools/fpga.py --selftest     the hygiene check must fail on a latch
                                         and on a net with two drivers

SYN-003 (hygiene): after synthesis there are no latches, no multiple or
missing drivers and no combinational loops (yosys check -assert).
SYN-002 (timing): nextpnr places and routes with the real .pcf; every path
must leave at least 30% of the 12 MHz period as slack, i.e. fmax >= 17.1 MHz.
The bitstream (.bin) is what sysctl writes into each FPGA's flash.
"""

import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OSS = "/opt/oss-cad-suite/bin"
YOSYS = os.path.join(ROOT, "soc", "formal", "yosys-ghdl")
PERIOD_NS = 1000 / 12
MIN_FMAX = 12 / 0.7                      # 30% slack on the 12 MHz period
# the HX4K is an HX8K die, so nextpnr offers 7680 cells, but Lattice only
# specifies 3520: stay within those
HX4K_LC = 3520

DESIGNS = {
    "chipset": (["spi_master.vhd", "bridge.vhd", "chipset.vhd", "chipset_top.vhd"], "chipset_top", "chipset.pcf"),
    "cpucard": (["alu.vhd", "cpu.vhd", "cpucard_top.vhd"], "cpucard_top", "cpucard.pcf"),
}


# yosys checks for SYN-003, run after proc (where a latch would appear) and
# again after synthesis
HYGIENE = ("select -assert-none t:$dlatch t:$adlatch t:$dlatchsr; "
           "check -assert; ")


def build(name):
    files, top, pcf = DESIGNS[name]
    out = os.path.join(ROOT, "build", "fpga", name)
    os.makedirs(out, exist_ok=True)
    subprocess.run([sys.executable, os.path.join(ROOT, "hw", "tools", "genpins.py")],
                   check=True, capture_output=True)
    srcs = " ".join(os.path.join(ROOT, "soc", f) for f in files)
    script = ("ghdl --std=08 %s -e %s; hierarchy -top %s; proc; " % (srcs, top, top) + HYGIENE +
              "synth_ice40 -top %s -json %s/%s.json; " % (top, out, name) + HYGIENE + "stat")
    r = subprocess.run([YOSYS, "-q", "-l", os.path.join(out, "yosys.log"), "-p", script],
                       capture_output=True, text=True)
    if r.returncode:
        print(r.stdout[-3000:] + r.stderr[-3000:])
        return None, "synthesis or hygiene check failed (see %s/yosys.log)" % out
    r = subprocess.run([os.path.join(OSS, "nextpnr-ice40"), "--hx8k", "--package", "tq144:4k",
                        "--json", os.path.join(out, name + ".json"),
                        "--pcf", os.path.join(ROOT, "build", "hw", pcf),
                        "--asc", os.path.join(out, name + ".asc"), "--freq", "12", "--seed", "1"],
                       capture_output=True, text=True)
    if r.returncode:
        return None, "place and route failed:\n" + r.stderr[-3000:]
    fmax = [float(m) for m in re.findall(r"Max frequency for clock[^:]*: ([\d.]+) MHz", r.stderr)]
    util = re.findall(r"ICESTORM_LC:\s+(\d+)/\s*(\d+)", r.stderr)
    subprocess.run([os.path.join(OSS, "icepack"), os.path.join(out, name + ".asc"),
                    os.path.join(out, name + ".bin")], check=True)
    return {"fmax": min(fmax) if fmax else 0.0, "lc": util[-1] if util else None,
            "bin": os.path.getsize(os.path.join(out, name + ".bin"))}, None


# designs the hygiene check must reject: (ghdl options, VHDL, what must
# reject it). GHDL itself refuses latches and double assignments; --latches
# lets the latch through so the yosys select must catch it, and a
# combinational loop passes GHDL and is left to yosys's check.
BROKEN = {
    "two-drivers": ("", """library ieee; use ieee.std_logic_1164.all;
entity broken is port(a, b: in std_logic; q: out std_logic); end entity;
architecture rtl of broken is begin
	q <= a; q <= b;
end architecture;""", "multiple assignments"),
    "latch": ("--latches", """library ieee; use ieee.std_logic_1164.all;
entity broken is port(en, d: in std_logic; q: out std_logic); end entity;
architecture rtl of broken is begin
	process(en, d) begin if en = '1' then q <= d; end if; end process;
end architecture;""", "Assertion failed: selection is not empty"),
    "loop": ("", """library ieee; use ieee.std_logic_1164.all;
entity broken is port(a: in std_logic; q: out std_logic); end entity;
architecture rtl of broken is signal x, y: std_logic; begin
	x <= a xor y; y <= not x; q <= y;
end architecture;""", "logic loop"),
}


def selftest():
    out = os.path.join(ROOT, "build", "fpga", "selftest")
    os.makedirs(out, exist_ok=True)
    bad = 0
    for name, (opts, vhdl, why) in BROKEN.items():
        src = os.path.join(out, name + ".vhd")
        with open(src, "w") as f:
            f.write(vhdl)
        r = subprocess.run([YOSYS, "-q", "-p", "ghdl --std=08 %s %s -e broken; hierarchy -top broken; proc; %s"
                            % (opts, src, HYGIENE)], capture_output=True, text=True)
        ok = r.returncode != 0 and why in r.stdout + r.stderr
        print("%s %-12s %s" % ("ok  " if ok else "FAIL", name,
                               "rejected: " + why if ok else "NOT rejected for: " + why))
        bad += not ok
    return 1 if bad else 0


def main():
    if "--selftest" in sys.argv:
        return selftest()
    names = [a for a in sys.argv[1:] if not a.startswith("--")] or list(DESIGNS)
    bad = 0
    for name in names:
        res, why = build(name)
        if res is None:
            print("FAIL %s: %s" % (name, why))
            bad += 1
            continue
        ok = res["fmax"] >= MIN_FMAX and int(res["lc"][0]) <= HX4K_LC
        print("%s %s: fmax %.1f MHz (needs >= %.1f: 30%% slack at 12 MHz), %s/%d logic cells, bitstream %d bytes"
              % ("ok  " if ok else "FAIL", name, res["fmax"], MIN_FMAX, res["lc"][0], HX4K_LC, res["bin"]))
        bad += not ok
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
