#!/usr/bin/env python3
"""Run a SymbiYosys proof with the ghdl-enabled yosys (soc/formal/yosys-ghdl).

    python3 tools/formal.py chipset [prove|bmc]
    python3 tools/formal.py --mutants      counterexamples: each MUTANT puts a
                                           bug back into a copy of the RTL, and
                                           the named property must then fail
"""

import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OSS = "/opt/oss-cad-suite/bin"


# (name, file under soc/, [(text in the fixed RTL, the bug)], property that must
# fail (None: simulation only), tb_chipset sections that must fail on the mutant too)
MUTANTS = [
    # the reset race BUS-004 found, exactly as it was before the fix: cycles
    # taken and completed while /CPU_RST is asserted
    ("reset-race", "chipset.vhd", [
     ("""				if cpu_rst_i = '1' then
					-- the CPU is in reset: drop any cycle it had asked for and take
					-- none, so no /RDY can reach it for a request it abandoned
					-- (BUS-004 found this: a stale /RDY could meet its first fetch)
					cyc_busy <= '0';
					rdy_r <= '1';
				elsif rdy_r = '0' then""",
      """				if rdy_r = '0' then"""),
     ("""					elsif cyc_busy = '1' and cpu_rst_i = '0' then	-- the cycle is still wanted""",
      """					else""")],
     "bus_rdy_in_cycle", ["RST-002"]),
    # the properties themselves must be able to fail: RAM and ROM both enabled
    ("both-chips", "chipset.vhd", [
     ("""							n_ce_ram_r <= rom;
							n_ce_rom_r <= not rom;""",
      """							n_ce_ram_r <= '0';
							n_ce_rom_r <= not rom;""")],
     "mmu_one_chip", []),
    # ... and /RDY held for two clocks
    ("long-rdy", "chipset.vhd", [
     ("""					rdy_r <= '1';
					cyc_busy <= '0';""",
      """					rdy_r <= '0';
					cyc_busy <= '0';""")],
     "bus_rdy_one_clock", []),
    # banked RAM (extended-ram.md): the window ignoring RAM_BANK ...
    ("ram-window-ignored", "chipset.vhd", [
     ("""							phys := unsigned(ram_bank) & a(13 downto 0);	-- the RAM window""",
      """							phys := "000" & a;""")],
     "mmu_ram_window", ["MMU-005"]),
    # ... RAM_BANK coming out of reset as 0 instead of the identity map ...
    ("ram-bank-reset-0", "chipset.vhd", [
     ("""rom_bank <= x"00"; ram_bank <= "00010";""",
      """rom_bank <= x"00"; ram_bank <= "00000";""")],
     "mmu_ram_bank_reset", ["MMU-005"]),
    # ... and the bridge's RAM_WR24/RAM_RD24 cut to 16 bits (no property:
    # the bridge's protocol is checked by simulation only)
    ("far-ram-16bit", "bridge.vhd", [
     ('cmd = x"03" or cmd = x"04" or cmd = x"09" or cmd = x"0a"\n',
      'cmd = x"03" or cmd = x"04"\n')],
     None, ["BRG-004"]),
]


def run_sby(sbydir, workdir, task, env, wrapper):
    return subprocess.run([os.path.join(OSS, "sby"), "--yosys", wrapper, "-f", "-d", workdir,
                           os.path.join(sbydir, "chipset.sby"), task], env=env, cwd=sbydir,
                          capture_output=True, text=True)


def sim_fails(base, section):
    """Run a tb_chipset section on the mutant copy; True if it fails."""
    ghdl = os.path.join(OSS, "ghdl")
    work = os.path.join(base, "ghdl")
    os.makedirs(work, exist_ok=True)
    src = [os.path.join(base, "soc", f) for f in ("spi_master.vhd", "bridge.vhd", "chipset.vhd")]
    tb = [os.path.join(ROOT, "soc", "tb", f) for f in
          ("models/sram_model.vhd", "models/sst39_model.vhd", "tb_chipset.vhd")]
    for step in (["-a", "--std=08", "-fsynopsys", *src, *tb], ["-e", "--std=08", "-fsynopsys", "tb_chipset"]):
        if subprocess.run([ghdl, *step], cwd=work, capture_output=True).returncode:
            return False                      # does not even build: not a counterexample
    r = subprocess.run([os.path.join(work, "tb_chipset"), "-gONLY=" + section, "--ieee-asserts=disable"],
                       cwd=work, capture_output=True, timeout=3600)
    return r.returncode != 0


def mutants(env, wrapper):
    bad = 0
    for name, fname, edits, prop, sims in MUTANTS:
        base = os.path.join(ROOT, "build", "formal", "mutant-" + name)
        shutil.rmtree(base, ignore_errors=True)
        shutil.copytree(os.path.join(ROOT, "soc"), os.path.join(base, "soc"),
                        ignore=shutil.ignore_patterns("tb", "*.o", "*.cf"))
        path = os.path.join(base, "soc", fname)
        text = open(path).read()
        missing = [fixed for fixed, _ in edits if fixed not in text]
        if missing:
            print("FAIL %s: the fixed code is not in %s any more (update the mutant)" % (name, fname))
            bad += 1
            continue
        for fixed, bug in edits:
            text = text.replace(fixed, bug, 1)
        with open(path, "w") as f:
            f.write(text)
        sbydir = os.path.join(base, "soc", "formal")
        if prop:
            run_sby(sbydir, os.path.join(base, "run"), "bmc", env, wrapper)
            log = open(os.path.join(base, "run", "logfile.txt")).read()
            if "failed assertion chipset.\\chipset_props.%s" % prop in log:
                print("ok   %-12s caught by %s" % (name, prop))
            else:
                print("FAIL %-12s NOT caught by %s" % (name, prop))
                bad += 1
        for section in sims:
            if sim_fails(base, section):
                print("ok   %-12s caught by tb_chipset %s" % (name, section))
            else:
                print("FAIL %-12s NOT caught by tb_chipset %s" % (name, section))
                bad += 1
    return 1 if bad else 0


def main():
    if sys.argv[1:2] == ["--mutants"]:
        bindir = os.path.join(ROOT, "build", "formal", "bin")
        os.makedirs(bindir, exist_ok=True)
        wrapper = os.path.join(bindir, "yosys")
        if not os.path.exists(wrapper):
            os.symlink(os.path.join(ROOT, "soc", "formal", "yosys-ghdl"), wrapper)
        env = dict(os.environ, PATH=bindir + ":" + OSS + ":" + os.environ["PATH"])
        return mutants(env, wrapper)
    name = sys.argv[1] if len(sys.argv) > 1 else "chipset"
    task = sys.argv[2] if len(sys.argv) > 2 else "prove"
    bindir = os.path.join(ROOT, "build", "formal", "bin")
    os.makedirs(bindir, exist_ok=True)
    wrapper = os.path.join(bindir, "yosys")
    if not os.path.exists(wrapper):
        os.symlink(os.path.join(ROOT, "soc", "formal", "yosys-ghdl"), wrapper)
    workdir = os.path.join(ROOT, "build", "formal", name)
    if os.path.exists(workdir + "_" + task):
        shutil.rmtree(workdir + "_" + task)
    env = dict(os.environ, PATH=bindir + ":" + OSS + ":" + os.environ["PATH"])
    r = subprocess.run([os.path.join(OSS, "sby"), "--yosys", wrapper, "-f", "-d", workdir + "_" + task,
                        os.path.join(ROOT, "soc", "formal", name + ".sby"), task], env=env,
                       cwd=os.path.join(ROOT, "soc", "formal"))
    return r.returncode


if __name__ == "__main__":
    sys.exit(main())
