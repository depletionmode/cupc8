# Print a per-instruction trace of a program run on sim.nim, the reference
# model. soc/tb/tb_cpu_trace.vhd prints the same format for the VHDL CPU, and
# tools/lockstep.py diffs the two.
#
#   S pppp r0 r1 f ssss   state at an instruction boundary (f = I<<1 | Z)
#   W aaaa dd             memory write made by the instruction that follows
#                         the previous S line
#
# Usage: simtrace <image.o> [maxSteps]

import os
import strutils
import sim

proc stateLine(): string =
  let f = (if ZF: 1 else: 0) or (if IF: 2 else: 0)
  "S $1 $2 $3 $4 $5" % [toHex(PC, 4).toLowerAscii, toHex(R0, 2).toLowerAscii,
                        toHex(R1, 2).toLowerAscii, $f, toHex(SP, 4).toLowerAscii]

proc main() =
  if paramCount() < 1:
    quit("usage: simtrace <image.o> [maxSteps]", 2)
  let maxSteps = if paramCount() >= 2: parseInt(paramStr(2)) else: 100_000
  log_mask = 0            # the simulator's coloured GPO logging would corrupt the trace
  cpuReset()
  cpuLoadFile(paramStr(1))
  memHook = proc(kind: MemAccessKind; address, value, oldValue: int) =
    if kind == maWrite:
      echo "W $1 $2" % [toHex(address, 4).toLowerAscii, toHex(value, 2).toLowerAscii]
  echo stateLine()
  var steps = 0
  while steps < maxSteps:
    let r = cpuStep()
    inc steps
    if r != sOk or HF:
      break
    # A parked WAI is not an instruction boundary; the VHDL CPU does not fetch.
    if not waiting:
      echo stateLine()
    if PC >= imageEnd:
      break
  echo "E ", (if HF: "halt" elif PC >= imageEnd: "end" else: "limit")

main()
