# In-repo tests that drive the shipped CUPC/8 CPU in sim.nim
# plus the in-tree assembler (tools/as.py).

import os
import osproc
import net
import selectors
import nativesockets
import strutils
import sequtils
import tables
import sim
import simdisplay
import simcards
import disasm
import symbols
import tui

let
  toolsDir = currentSourcePath().parentDir
  rootDir = toolsDir.parentDir
  asPy = toolsDir / "as.py"
  testdata = toolsDir / "testdata"
  testDir = rootDir / "test"
  kernelDir = rootDir / "kernel"

var failures = 0

proc fail(msg: string) =
  echo "FAIL: ", msg
  inc failures

proc ok(msg: string) =
  echo "ok: ", msg

# `simtest [name ...]` runs only the named tests; no arguments runs them all.
let onlyTests = commandLineParams()

template run(test: untyped) =
  if onlyTests.len == 0 or astToStr(test) in onlyTests:
    test()

proc expect(name: string, got, want: int, width = 2) =
  if got != want:
    fail("$1: got $#$2 want $#$3" % [name, toHex(got, width), toHex(want, width)])
  else:
    ok(name)

proc expectTrue(name: string, cond: bool) =
  if cond: ok(name)
  else: fail(name)

proc assemble(src, dest: string; echoOut = false) =
  if fileExists(dest):
    removeFile(dest)
  let cmd = "python3 " & quoteShell(asPy) & " " & quoteShell(src) & " " &
            quoteShell(dest)
  let r = execCmdEx(cmd)
  if echoOut:
    echo r.output.strip
  if r.exitCode != 0 or not fileExists(dest) or getFileSize(dest) < 4:
    raise newException(IOError, "assembler failed for " & src & ":\n" & r.output)

proc loadProgram(src: string; boot = true) =
  let dest = testdata / src.extractFilename.changeFileExt("o")
  assemble(src, dest)
  cpuReset()
  cpuLoadFile(dest)
  if boot:
    doAssert cpuStep() == sOk

proc runToHalt(maxSteps = 20000): int =
  var n = 0
  while n < maxSteps:
    if cpuStep() != sOk:
      break
    inc n
  if not HF:
    fail("did not halt after $1 steps pc=$#" % [$n, toHex(PC, 4)])
  n

proc runFile(src: string): int =
  loadProgram(src)
  runToHalt()

# ---------------------------------------------------------------------------
# original smoke tests
# ---------------------------------------------------------------------------

proc testTinyProgram() =
  echo "== tiny assembled program =="
  let src = testdata / "movst.s"
  let dest = testdata / "movst.o"
  assemble(src, dest, echoOut = true)
  let blob = readFile(dest)
  doAssert blob.len > 3
  doAssert blob[0].ord == 0xb0
  let entry = blob[1].ord or (blob[2].ord shl 8)
  doAssert entry >= 0x1000 and entry <= 0xefff

  cpuReset()
  cpuLoadFile(dest)
  doAssert PC == 0x1000
  doAssert mem[0x1000] == 0xb0

  doAssert cpuStep() == sOk
  if PC != entry:
    fail("after boot B, pc=$# expected $#" % [toHex(PC, 4), toHex(entry, 4)])
  else:
    ok("boot B landed at main $" & toHex(PC, 4))

  doAssert cpuStep() == sOk  # mov r0, #0x42
  if R0 != 0x42:
    fail("after mov, r0=$# expected 42" % [toHex(R0, 2)])
  else:
    ok("mov r0, #0x42")

  doAssert cpuStep() == sOk  # st $2000, r0
  if mem[0x2000] != 0x42:
    fail("after st, mem[2000]=$# expected 42" % [toHex(mem[0x2000], 2)])
  else:
    ok("st $2000, r0 wrote 0x42")

  discard cpuStep()  # halt
  if not HF:
    fail("halt did not set HF")
  else:
    ok("halt retired")
  echo cpuStatusLine()

proc testKernelBoot() =
  echo "== kernel.o boot =="
  let assembled = execCmdEx("bash assemble.sh", options = {poUsePath},
                            workingDir = kernelDir)
  echo assembled.output.splitLines()[^1]
  let kpath = kernelDir / "kernel.o"
  if not fileExists(kpath):
    fail("kernel.o missing after assemble.sh")
    return
  if getFileSize(kpath) <= 3:
    fail("kernel.o too small")
    return

  cpuReset()
  cpuLoadFile(kpath)
  let bootOp = mem[0x1000]
  let mainAddr = mem[0x1001] or (mem[0x1002] shl 8)
  if bootOp != 0xb0:
    fail("kernel[0] is $# not B (0xb0)" % [toHex(bootOp, 2)])
    return
  if mainAddr < 0x1000 or mainAddr > 0xefff:
    fail("boot target $" & toHex(mainAddr, 4) & " not in program region")
    return
  ok("kernel image B $" & toHex(mainAddr, 4))

  doAssert cpuStep() == sOk
  if PC != mainAddr:
    fail("pc stayed at $# after boot B (wanted main $" & toHex(mainAddr, 4) & ")" %
         [toHex(PC, 4)])
    return
  if PC == 0x1003:
    fail("pc fell through empty/NOP path")
    return
  ok("pc followed boot B into main $" & toHex(PC, 4))

  # main: mov r0,#1 / st $f203,r0 (ROM off) then push pch; push pcl; b gpu_init
  if (mem[PC] and 0xfc) != 0x8c:        # MOV Ra, #imm
    fail("main does not start with mov #imm (op=$#)" % [toHex(mem[PC], 2)])
  if (mem[PC+2] and 0xf8) != 0xa8:
    fail("second main insn is not st (op=$#)" % [toHex(mem[PC+2], 2)])
  let sysctlAddr = mem[PC+3] or (mem[PC+4] shl 8)
  expect("main writes SYSCTL", sysctlAddr, 0xf203, 4)
  if (mem[PC+5] and 0xf8) != 0x90 or (mem[PC+6] and 0xf8) != 0x90:
    fail("main does not call a driver with push pch/push pcl")
  if (mem[PC+7] and 0xf8) != 0xb0:
    fail("main's first call is not a B")
    return
  let initAddr = mem[PC+8] or (mem[PC+9] shl 8)
  for _ in 1..5:
    doAssert cpuStep() == sOk
  if PC != initAddr:
    fail("after main's first calls, pc=$# expected gpu_init $#" %
         [toHex(PC, 4), toHex(initAddr, 4)])
  else:
    ok("kernel switched the ROM off and called gpu_init $" & toHex(PC, 4))
  expect("SYSCTL ROM_OFF written", mem[0xf203], 1)

  echo cpuStatusLine()


# ---------------------------------------------------------------------------
# assembler
# ---------------------------------------------------------------------------

proc testAssemblerEncodings() =
  echo "== assembler encodings =="
  loadProgram(testdata / "encode.s", boot = false)
  expect("image[1000] is B", mem[0x1000], 0xb0)
  let entry = mem[0x1001] or (mem[0x1002] shl 8)
  expect("entry is $1003", entry, 0x1003, 4)

  # main is first, so body starts at $1003
  expect("nop", mem[0x1003], 0x80)
  expect("mov r0, #imm", mem[0x1004], 0x8c)
  expect("mov imm 0x42", mem[0x1005], 0x42)
  expect("mov r1, r0", mem[0x1006], 0x89)
  expect("push r0", mem[0x1007], 0x90)
  expect("pop r1", mem[0x1008], 0x99)
  expect("eq r0, #imm", mem[0x1009], 0x04)
  expect("eq imm 1", mem[0x100a], 0x01)
  expect("add r0, #imm", mem[0x100b], 0x44)
  expect("add imm 1", mem[0x100c], 0x01)
  expect("ld r0, $addr", mem[0x100d], 0xa0)
  expect("ld addr lo", mem[0x100e], 0x00)
  expect("ld addr hi", mem[0x100f], 0x20)
  expect("st $addr, r1", mem[0x1010], 0xaa)
  expect("st addr lo", mem[0x1011], 0x00)
  expect("st addr hi", mem[0x1012], 0x20)
  expect("b", mem[0x1013], 0xb0)
  expect("b dest lo", mem[0x1014], 0x03)
  expect("b dest hi", mem[0x1015], 0x10)
  expect("bzf", mem[0x1016], 0xb8)
  expect("halt", mem[0x1019], 0xf8)

proc testAssemblerMap() =
  echo "== assembler map =="
  let
    src = testdata / "movst.s"
    dest = testdata / "movst.o"
    mapPath = testdata / "movst.map"
  if fileExists(dest): removeFile(dest)
  if fileExists(mapPath): removeFile(mapPath)
  let command = "python3 " & quoteShell(asPy) & " " & quoteShell(src) &
                " " & quoteShell(dest) & " --map"
  let assembled = execCmdEx(command)
  if assembled.exitCode != 0 or not fileExists(mapPath):
    fail("assembler did not emit default map: " & assembled.output)
    return
  let
    blob = readFile(dest)
    expectedEntry = blob[1].ord or (blob[2].ord shl 8)
    lines = readFile(mapPath).splitLines()
  expectTrue("map version header", lines.len > 0 and lines[0] == "CUPC8MAP 1")
  var
    mappedEntry = -1
    sawMain = false
    firstLineAddress = -1
  for line in lines:
    let fields = line.splitWhitespace()
    if fields.len >= 3 and fields[0] == "entry":
      mappedEntry = parseHexInt(fields[1])
    elif fields.len >= 3 and fields[0] == "sym" and fields[2] == "main":
      sawMain = true
    elif fields.len >= 4 and fields[0] == "line" and firstLineAddress < 0:
      firstLineAddress = parseHexInt(fields[1])
  expect("map entry matches image", mappedEntry, expectedEntry, 4)
  expectTrue("map contains main symbol", sawMain)
  expect("first mapped instruction", firstLineAddress, 0x1003, 4)
  let explicitMap = testdata / "movst.explicit.map"
  if fileExists(explicitMap): removeFile(explicitMap)
  let explicit = execCmdEx(command.replace("--map", "--map=" & quoteShell(explicitMap)))
  expectTrue("explicit map path", explicit.exitCode == 0 and fileExists(explicitMap))

proc testDisassembler() =
  echo "== disassembler =="
  loadProgram(testdata / "encode.s", boot = false)
  let expected = [
    (0x1003, 1, "nop"),
    (0x1004, 2, "mov r0, #0x42"),
    (0x1006, 1, "mov r1, r0"),
    (0x1007, 1, "push r0"),
    (0x1008, 1, "pop r1"),
    (0x1009, 2, "eq r0, #0x01"),
    (0x100b, 2, "add r0, #0x01"),
    (0x100d, 3, "ld r0, $2000"),
    (0x1010, 3, "st $2000, r1"),
    (0x1013, 3, "b $1003"),
    (0x1016, 3, "bzf $1003"),
    (0x1019, 1, "halt")]
  for (address, length, text) in expected:
    let decoded = disasm(mem, address)
    expectTrue("decode " & text,
               decoded.valid and decoded.len == length and decoded.text == text)

  let callBytes = [0x96, 0x97, 0xb0, 0x34, 0x12]
  let call = disasm(callBytes, 0)
  expectTrue("collapse call idiom",
             call.valid and call.isCall and call.isBranch and call.len == 5 and
             call.target == 0x1234 and call.text == "call $1234")
  let invalid = disasm([0xd8], 0)
  expectTrue("unknown opcode is data",
             not invalid.valid and invalid.len == 1 and invalid.text == "db 0xD8")

proc testSymbolsAndKernelDecode() =
  echo "== symbols and kernel instruction boundaries =="
  let assembled = execCmdEx("bash assemble.sh", options = {poUsePath},
                            workingDir = kernelDir)
  if assembled.exitCode != 0:
    fail("kernel assembly for symbol test failed: " & assembled.output)
    return
  var table = loadMap(kernelDir / "kernel.map")
  expectTrue("kernel map loaded", table.loaded)
  let termAddress = table.resolve("term_do")
  expectTrue("resolve term_do", termAddress >= 0x1000)
  expectTrue("resolve data symbol", table.resolve("term_s_info") >= 0x3000)
  expectTrue("resolve bss symbol", table.resolve("term_line_buf") >= 0x5000)
  expectTrue("data symbols retained", table.dataSyms.len > 0)
  expectTrue("exact symbolization", table.symbolize(termAddress) == "term_do")
  expectTrue("symbol plus offset",
             table.symbolize(termAddress + 2).startsWith("term_do+0x"))
  expectTrue("source address mapping",
             table.lineFor.hasKey(termAddress) and
             table.lineFor[termAddress].file == "term.s")
  let source = table.sourceLines("term.s")
  expectTrue("source loader", source.len > 8 and source[6].strip == "term_do:")
  # the instruction after term_do's first, whatever that one's length
  var nextIns = -1
  for a in table.insAddrs:
    if a > termAddress:
      nextIns = a
      break
  expectTrue("previous instruction anchor",
             nextIns > termAddress and table.prevInsAddr(nextIns, 1) == termAddress)

  cpuReset()
  cpuLoadFile(kernelDir / "kernel.o")
  var mismatch = ""
  for i in 0..<(table.insAddrs.len - 1):
    let
      address = table.insAddrs[i]
      nextAddress = table.insAddrs[i + 1]
      decoded = disasm(mem, address, collapseCalls = false)
    if not decoded.valid or decoded.len != nextAddress - address:
      mismatch = "$1: '$2' len $3, next delta $4" % [
        toHex(address, 4), decoded.text, $decoded.len, $(nextAddress - address)]
      break
  expectTrue("kernel map boundaries match decoder", mismatch.len == 0)
  if mismatch.len > 0: echo "  ", mismatch

proc testTuiDiff() =
  echo "== TUI diff renderer =="
  var output = ""
  let sink: SinkProc = proc(data: string) = output.add(data)
  tuiInit(sink, width = 4, height = 2)
  defer: tuiShutdown()
  discard present()
  output.setLen(0)
  discard present()
  expectTrue("identical frame emits nothing", output.len == 0)
  putStr(2, 1, "X", 0x01112233'u32)
  discard present()
  expectTrue("single cell emits one compact run",
             output == "\e[2;3H\e[0;38;2;17;34;51;49mX")
  output.setLen(0)
  discard present()
  expectTrue("settled changed frame emits nothing", output.len == 0)

proc testAssemblerRejects() =
  echo "== assembler rejects bad input =="
  for src in [testdata / "no_main.s", testdata / "bad_ins.s"]:
    let dest = testdata / src.extractFilename.changeFileExt("o")
    if fileExists(dest):
      removeFile(dest)
    try:
      assemble(src, dest)
      fail("assembler accepted " & src.extractFilename)
    except IOError:
      ok("assembler rejected " & src.extractFilename)

# ---------------------------------------------------------------------------
# ISA programs
# ---------------------------------------------------------------------------

proc testAluImm() =
  echo "== ALU immediate / overflow =="
  discard runFile(testdata / "alu.s")
  expect("add imm", mem[0x2000], 15)
  expect("add reg after imm", mem[0x2001], 22)
  expect("add overflow", mem[0x2002], 1)
  expect("sub imm", mem[0x2003], 7)
  expect("sub underflow", mem[0x2004], 255)
  expect("and", mem[0x2005], 0x30)
  expect("or", mem[0x2006], 0xff)
  expect("xor", mem[0x2007], 0xf0)
  expect("nor 0,0", mem[0x2008], 0xff)
  expect("nor 0f,f0", mem[0x2009], 0)
  expect("shl 1,4", mem[0x200a], 16)
  expect("shl 80,1", mem[0x200b], 0)
  expect("shr 80,4", mem[0x200c], 8)
  expect("shr 1,1", mem[0x200d], 0)
  expect("mov r1,r0 + nop", mem[0x200e], 0x55)

proc testAluReg() =
  echo "== ALU register-register =="
  discard runFile(testdata / "alu_reg.s")
  expect("xor 20,30", mem[0x2000], 10)
  expect("and aa,0f", mem[0x2001], 0x0a)
  expect("or a0,0b", mem[0x2002], 0xab)
  expect("sub 50,8", mem[0x2003], 42)
  expect("add 3,5", mem[0x2004], 8)
  expect("shl 1,3", mem[0x2005], 8)
  expect("shr 40,2", mem[0x2006], 0x10)
  expect("nor 0f,f0", mem[0x2007], 0)
  expect("xor same", mem[0x2008], 0)

proc testCmp() =
  echo "== compare + BZF =="
  discard runFile(testdata / "cmp.s")
  expect("cmp suite", mem[0x2000], 0xaa)

proc testStack() =
  echo "== stack push/pop =="
  discard runFile(testdata / "stack.s")
  expect("pop r0 (was r1)", mem[0x2000], 0x22)
  expect("pop r1 (was r0)", mem[0x2001], 0x11)
  expect("push #imm", mem[0x2002], 0xaa)
  expect("push order lo", mem[0x2003], 10)
  expect("push order hi", mem[0x2004], 20)
  expect("SP restored", SP, 0x0100, 4)

  discard runFile(testdata / "stack_depth.s")
  expect("SP after two pushes", SP, 0x0102, 4)
  # SP points to the next free byte (manual 3.2), so the pushes land at $0100/$0101
  expect("stack[0100]", mem[0x0100], 1)
  expect("stack[0101]", mem[0x0101], 2)

proc testCallRet() =
  echo "== call/return via pch/pcl =="
  discard runFile(testdata / "callret.s")
  expect("func r0", mem[0x2000], 0x77)
  expect("func r1", mem[0x2001], 0x88)
  expect("nested r0+1", mem[0x2002], 0x78)
  expect("SP restored after returns", SP, 0x0100, 4)

proc testMem() =
  echo "== load/store =="
  discard runFile(testdata / "memops.s")
  expect("ld/st direct", mem[0x2000], 0xab)
  expect("ld/st indexed", mem[0x2001], 0xcd)
  expect("raw $2105", mem[0x2002], 0xcd)
  expect("page-end store", mem[0x2003], 0x12)
  expect("raw $2100", mem[0x2100], 0xab)
  expect("raw $2105 mem", mem[0x2105], 0xcd)

proc testIndirect() =
  echo "== ldd/std =="
  discard runFile(testdata / "indirect.s")
  expect("std/ldd", mem[0x2000], 0xcd)
  expect("pointee $2100", mem[0x2001], 0xcd)
  expect("indexed std/ldd", mem[0x2002], 0x5a)
  expect("pointee after indexed", mem[0x2100], 0x5a)

proc testFlow() =
  echo "== branches =="
  discard runFile(testdata / "flow.s")
  expect("B skipped fail path", mem[0x2000], 0xaa)
  expect("BZF not taken", mem[0x2001], 0x11)

proc testGpo() =
  echo "== GPO $f000 =="
  discard runFile(testdata / "gpo.s")
  expect("mem[f000]", mem[0xf000], 0xa5)
  expect("ld back GPO", mem[0x2000], 0xa5)
  expectTrue("last_gpo mentions A5", last_gpo.contains("A5"))

proc testSpiStatus() =
  echo "== SPI status registers =="
  discard runFile(testdata / "spi_status.s")
  expect("display SPI ready", mem[0x2000], 1)
  expect("keyboard empty", mem[0x2001], 0)

proc testMulDiv() =
  echo "== software mul/div =="
  discard runFile(testdata / "muldiv.s")
  expect("3*7", mem[0x2000], 21)
  expect("20/6 quot", mem[0x2001], 3)
  expect("20/6 rem", mem[0x2002], 2)
  expect("0*9", mem[0x2003], 0)

proc testZfSurvive() =
  echo "== ZF survives ALU =="
  discard runFile(testdata / "zf_survive.s")
  expect("ZF still set after add", mem[0x2000], 0xaa)

proc testAddrSplit() =
  echo "== #< / #> address split =="
  discard runFile(testdata / "addr_split.s")
  expect("std via split ptr", mem[0x2000], 0x99)
  expect("ldd via split ptr", mem[0x2001], 0x99)
  expect("pointee $2300", mem[0x2300], 0x99)
  expect("ptr lo", mem[0x2200], 0x00)
  expect("ptr hi", mem[0x2201], 0x23)

proc testBssData() =
  echo "== .bss / .data =="
  discard runFile(testdata / "bss_data.s")
  expect("bss scalar", mem[0x2000], 0x42)
  expect("bss pair+0", mem[0x2001], 0x11)
  expect("bss pair+1", mem[0x2002], 0x22)
  expect("data 'A'", mem[0x2003], 65)
  expect("data 'B'", mem[0x2004], 66)
  expect("data 'C'", mem[0x2005], 67)
  expect("data image 'A'", mem[0x3000], 65)
  expect("data image 'C'", mem[0x3002], 67)

proc testDefine() =
  echo "== %define =="
  discard runFile(testdata / "define.s")
  expect("define MAGIC", mem[0x2000], 0x33)

# ---------------------------------------------------------------------------
# debugger-facing simulator API
# ---------------------------------------------------------------------------

proc testStepResult() =
  echo "== cpuStep result states =="
  let dest = testdata / "nohalt.o"
  assemble(testdata / "nohalt.s", dest)
  cpuReset()
  cpuLoadFile(dest)
  var result = sOk
  var steps = 0
  while result == sOk and steps < 10000:
    result = cpuStep()
    inc steps
  expectTrue("non-halting image reaches end", result == sPastImage)
  expect("PC at image end", PC, imageEnd, 4)

  cpuReset()
  cpuLoadImage($char(0xf8))
  expectTrue("halt instruction returns sHalted", cpuStep() == sHalted)
  expectTrue("already halted returns sHalted", cpuStep() == sHalted)

proc testMemHook() =
  echo "== memory access hook =="
  type Access = tuple[kind: MemAccessKind; address, value, oldValue: int]
  var accesses: seq[Access]
  memHook = proc(kind: MemAccessKind; address, value, oldValue: int) =
    accesses.add((kind, address, value, oldValue))
  defer: memHook = nil

  discard runFile(testdata / "memops.s")
  var sawWrite = false
  for access in accesses:
    if access == (maWrite, 0x2100, 0xab, 0):
      sawWrite = true
  expectTrue("hook records write value and old value", sawWrite)

  accesses.setLen(0)
  discard runFile(testdata / "spi_status.s")
  var sawDeliveredRead = false
  for access in accesses:
    if access == (maRead, 0xf103, 1, 0):
      sawDeliveredRead = true
  expectTrue("hook records delivered SPI status", sawDeliveredRead)

proc testCpuRunBreak() =
  echo "== batched run and breakpoint =="
  let dest = testdata / "callret.o"
  assemble(testdata / "callret.s", dest)
  cpuReset()
  clearAllBreaks()
  cpuLoadFile(dest)
  doAssert cpuStep() == sOk
  let
    mainAddr = PC
    funcAddr = mem[mainAddr + 7] or (mem[mainAddr + 8] shl 8)
  setBreak(mainAddr)
  let retiredBeforeBreak = ins_retired
  expectTrue("current-PC breakpoint stops before execution",
             cpuRun(100_000) == reBreak)
  expect("current-PC breakpoint leaves PC parked", PC, mainAddr, 4)
  expect("current-PC breakpoint retires nothing", ins_retired,
         retiredBeforeBreak)
  expectTrue("continue bypasses hit breakpoint once", cpuRun(1) == reCount)
  expect("continue executed marked instruction", PC, mainAddr + 2, 4)
  clearBreak(mainAddr)
  setBreak(funcAddr)
  expectTrue("cpuRun stops at breakpoint", cpuRun(100_000) == reBreak)
  expect("PC parked at breakpoint", PC, funcAddr, 4)
  clearBreak(funcAddr)
  expectTrue("cpuRun reaches halt after clear", cpuRun(100_000) == reHalted)
  clearAllBreaks()

proc testStepOut() =
  echo "== step out =="
  let dest = testdata / "callret.o"
  assemble(testdata / "callret.s", dest)
  cpuReset()
  clearAllBreaks()
  cpuLoadFile(dest)
  doAssert cpuStep() == sOk
  let
    mainAddr = PC
    funcAddr = mem[mainAddr + 7] or (mem[mainAddr + 8] shl 8)
  setBreak(funcAddr)
  doAssert cpuRun(100_000) == reBreak
  clearBreak(funcAddr)
  stepOutSP = SP
  stepOutArmed = true
  expectTrue("return requests stop", cpuRun(100_000) == reStop)
  expect("step out return PC", PC, mainAddr + 9, 4)
  expect("step out restores SP", SP, 0x0100, 4)
  expectTrue("step out disarmed", not stepOutArmed)
  clearAllBreaks()

# ---------------------------------------------------------------------------
# older programs under test/
# ---------------------------------------------------------------------------

proc testLegacyAlu() =
  echo "== test/alu-test.s =="
  discard runFile(testDir / "alu-test.s")
  expect("legacy alu r0", R0, 255)
  expect("legacy alu r1", R1, 255)

proc testLegacyStack() =
  echo "== test/stack-test.s =="
  discard runFile(testDir / "stack-test.s")
  expect("legacy stack r0", R0, 15)
  expect("legacy stack r1", R1, 96)

proc testLegacyGpo() =
  echo "== test/gpo-test.s =="
  discard runFile(testDir / "gpo-test.s")
  expect("legacy gpo", mem[0xf000], 170)
  expectTrue("legacy last_gpo AA", last_gpo.contains("AA"))

proc testLegacyMem() =
  echo "== test/mem-test.s =="
  discard runFile(testDir / "mem-test.s")
  expect("legacy mem last GPO", mem[0xf000], 129)
  expect("legacy mem r0", R0, 129)

proc testLegacyMath() =
  echo "== test/math-test.s (3*3) =="
  loadProgram(testDir / "math-test.s")
  var n = 0
  while n < 2000 and last_gpo.len == 0:
    if cpuStep() != sOk:
      break
    inc n
  expect("legacy math 3*3", R0, 9)
  expect("legacy math GPO", mem[0xf000], 9)

proc testResetState() =
  echo "== cpuReset =="
  mem[0x1234] = 0xff
  R0 = 1
  R1 = 2
  PC = 0x2000
  SP = 0x0200
  ZF = true
  HF = true
  last_gpo = "stale"
  cpuReset()
  expect("reset PC", PC, 0x1000, 4)
  expect("reset SP", SP, 0x0100, 4)
  expect("reset R0", R0, 0)
  expect("reset R1", R1, 0)
  expectTrue("reset ZF", not ZF)
  expectTrue("reset HF", not HF)
  expectTrue("reset IF", not IF)
  expectTrue("reset waiting", not waiting)
  expect("reset irq pending", irqPending, 0)
  expect("reset mem", mem[0x1234], 0)
  expectTrue("reset last_gpo", last_gpo.len == 0)

# ---------------------------------------------------------------------------

run testTinyProgram
run testAssemblerEncodings
run testAssemblerMap
run testDisassembler
run testSymbolsAndKernelDecode
run testTuiDiff
run testAssemblerRejects
run testAluImm
run testAluReg
run testCmp
run testStack
run testCallRet
run testMem
run testIndirect
run testFlow
run testGpo
run testSpiStatus
run testMulDiv
run testZfSurvive
run testAddrSplit
run testBssData
run testDefine
run testStepResult
run testMemHook
run testCpuRunBreak
run testStepOut
run testLegacyAlu
run testLegacyStack
run testLegacyGpo
run testLegacyMem
run testLegacyMath
run testResetState
run testKernelBoot

proc testIrqOps() =
  echo "== irq opcodes =="
  loadProgram(testdata / "irq_ops.s", boot = false)
  expect("cli", mem[0x1003], 0xc0)
  expect("sti", mem[0x1004], 0xc8)
  expect("pop f", mem[0x1005], 0x9c)
  expect("wai", mem[0x1006], 0xf0)
  expect("tmr0 #imm", mem[0x1007], 0xe4)
  expect("tmr0 imm 3", mem[0x1008], 0x03)
  expect("tmr1 r0", mem[0x1009], 0xe8)
  expect("halt after tmr", mem[0x100a], 0xf8)
  let
    cliDec = disasm(mem, 0x1003)
    stiDec = disasm(mem, 0x1004)
    popfDec = disasm(mem, 0x1005)
    waiDec = disasm(mem, 0x1006)
  expectTrue("disasm cli", cliDec.valid and cliDec.text == "cli")
  expectTrue("disasm sti", stiDec.valid and stiDec.text == "sti")
  expectTrue("disasm pop f", popfDec.valid and popfDec.text == "pop f")
  expectTrue("disasm wai", waiDec.valid and waiDec.text == "wai")

proc testIrqTimer() =
  echo "== timer interrupt =="
  discard runFile(testdata / "irq_timer.s")
  expect("timer handler wrote $aa", mem[0x2000], 0xaa)

proc testIrqPopPcl() =
  ## CPU-005 (sim.nim): an IRQ is not taken between POP pcl and POP pch
  echo "== no IRQ between pop pcl and pop pch =="
  discard runFile(testdata / "irq_popret.s")
  expect("the timer handler ran", mem[0x2001], 0x11)
  expect("the call returned where it should", mem[0x2000], 0x55)
  expect("SP back at the bottom", SP, 0x0100, 4)

proc testIrqFlags() =
  echo "== pop f restores Z =="
  discard runFile(testdata / "irq_flags.s")
  expect("Z survived handler", mem[0x2000], 0xaa)
  expectTrue("I set after pop f", IF)

proc testIrqCli() =
  echo "== cli blocks take =="
  discard runFile(testdata / "irq_cli.s")
  expect("pending latched under cli", mem[0x2000], 2)
  expectTrue("did not enter handler", mem[0x2000] != 0xee)

proc testIrqKeyb() =
  echo "== keyboard wai =="
  loadProgram(testdata / "irq_keyb.s")
  var n = 0
  while n < 200 and not waiting and not HF:
    if cpuStep() != sOk:
      break
    inc n
  expectTrue("parked in wai", waiting)
  pushKey(0x41)
  discard runToHalt()
  expect("read key after irq", mem[0x2000], 0x41)

proc testIrqMaskMmio() =
  echo "== irq mmio =="
  cpuReset()
  cpuLoadImage($char(0x8c) & $char(0x05) & $char(0xa8) & $char(0x01) &
               $char(0xf2) & $char(0xf8))
  # mov r0, #5 / st $f201, r0 / halt  — image at $1000
  discard runToHalt()
  expect("mask register", irqMask, 5)
  expect("mask readable", mem[0xf201], 5)

run testIrqOps
run testIrqTimer
run testIrqPopPcl
run testIrqFlags
run testIrqCli
run testIrqKeyb
run testIrqMaskMmio

proc testKernelKeybWaits() =
  echo "== kernel keyb parks on wai =="
  let assembled = execCmdEx("bash assemble.sh", options = {poUsePath},
                            workingDir = kernelDir)
  if assembled.exitCode != 0:
    fail("kernel assemble failed: " & assembled.output)
    return
  cpuReset()
  cpuLoadFile(kernelDir / "kernel.o")
  var n = 0
  while n < 2_000_000 and not waiting and not HF:
    if cpuStep() != sOk:
      break
    inc n
  expectTrue("kernel waiting for key", waiting)
  expectTrue("I enabled while waiting", IF)
  expect("slot, timer 0 and SPI IRQs unmasked", irqMask, 11)

run testKernelKeybWaits

proc testDisplayRect() =
  echo "== display framebuffer via shipped CPU SPI =="
  if DispWidth != 320 or DispHeight != 240:
    fail("display size " & $DispWidth & "x" & $DispHeight & ", expected 320x240")
  elif DispScaleDefault < 3:
    fail("default scale is " & $DispScaleDefault & "; window would stay tiny")
  else:
    ok("window " & $DispWidth & "x" & $DispHeight & " at " & $DispScaleDefault & "x")

  let dest = testdata / "fillrect.o"
  assemble(testdata / "fillrect.s", dest)
  cpuReset()
  cpuLoadFile(dest)
  var n = 0
  while n < 400 and cpuStep() == sOk:
    inc n
  if not HF:
    fail("fillrect program did not halt")
  let on = display_pixel(10, 20)
  let on2 = display_pixel(11, 20)
  let left = display_pixel(9, 20)
  let up = display_pixel(10, 19)
  if on != 0xFFFFFFFF'u32 and on != 0x00FFFFFF'u32:
    fail("pixel (10,20)=" & toHex(on, 8) & " expected white")
  elif on2 != 0xFFFFFFFF'u32 and on2 != 0x00FFFFFF'u32:
    fail("pixel (11,20)=" & toHex(on2, 8) & " expected white")
  elif left != 0:
    fail("pixel (9,20) should stay black, got " & toHex(left, 8))
  elif up != 0:
    fail("pixel (10,19) should stay black, got " & toHex(up, 8))
  else:
    ok("CASET/PASET/RAMWR painted 2x1 white at (10,20)")

run testDisplayRect

proc testCardsMode() =
  ## SIM-004: the Milestone 1 machine model: ROM windows, the new registers,
  ## and slot cards running the real firmware cores.
  echo "== cards mode (M1 machine) =="
  machineCards([CardGpu, CardIo])
  cpuReset()

  # the ROM chip through its windows
  for i in 0..rom.high:
    rom[i] = uint8((i * 7 + i div 2048) and 0xff)
  expect("fixed window $e000", cardsLoadTest(0xe000), int(rom[0]))
  expect("fixed window $e7ff", cardsLoadTest(0xe7ff), int(rom[0x7ff]))
  romBank = 3
  expect("banked window $e800", cardsLoadTest(0xe800), int(rom[3 * 2048]))
  expect("banked window $efff", cardsLoadTest(0xefff), int(rom[3 * 2048 + 0x7ff]))
  romBank = 0
  romOff = true
  mem[0xe000] = 0x5a
  expect("ROM_OFF gives RAM", cardsLoadTest(0xe000), 0x5a)
  romOff = false

  # a guest program drives both cards
  let dest = testdata / "cards_gpu.o"
  assemble(testdata / "cards_gpu.s", dest)
  cpuReset()
  cpuLoadFile(dest)
  expect("slot table from the boot ROM", mem[0x0002], CardGpu)
  expect("slot table slot 2", mem[0x0003], CardIo)
  pushKey(ord('A'))
  var n = 0
  while n < 4000 and cpuStep() == sOk:
    inc n
  expectTrue("cards program halted", HF)
  let g = gpuCard()
  expectTrue("graphics card present", not g.isNil)
  expect("GPU cell 0,0", int(simcard_gpu_cell(g, 0, 0)) and 0xff, ord('H'))
  expect("GPU cell 1,0", int(simcard_gpu_cell(g, 1, 0)) and 0xff, ord('i'))
  expect("IO card RESP_LEN", mem[0x2000], 1)
  expect("key read through the IO card", mem[0x2001], ord('A'))

  # the rendered picture reaches the display
  gpuPresent()
  expectTrue("display resized for the GPU card", DispWidth == 640 and DispHeight == 480)
  var lit = 0
  for y in 0..15:
    for x in 0..7:
      if display_pixel(x, y) != 0xFF000000'u32:
        inc lit
  expectTrue("the H glyph is rendered", lit > 10)

  ioModel = imLegacy
  display_setSize(320, 240)

run testCardsMode

proc buildRom(kernelSrc: string): string =
  ## Assemble the boot ROM and a kernel, then build a ROM image.
  let outDir = rootDir / "build" / "rom"
  createDir(outDir)
  let boot = outDir / "boot.bin"
  let kernel = outDir / "kernel.o"
  let rom = outDir / "test.rom"
  var r = execCmdEx("python3 " & quoteShell(rootDir / "tools" / "as.py") & " " &
                    quoteShell(rootDir / "rom" / "boot.s") & " " & quoteShell(boot) &
                    " 0xe000,0xe600,0x0f00")
  if r.exitCode != 0: raise newException(IOError, "boot ROM: " & r.output)
  assemble(kernelSrc, kernel)
  r = execCmdEx("python3 " & quoteShell(rootDir / "tools" / "mkrom.py") & " " &
                quoteShell(boot) & " " & quoteShell(kernel) & " -o " & quoteShell(rom))
  if r.exitCode != 0: raise newException(IOError, "mkrom: " & r.output)
  rom

proc testBootChain() =
  ## BOOT-001: reset into the boot ROM, POST, banner, kernel copy, and go.
  echo "== boot ROM chain =="
  let rom = buildRom(testdata / "cards_gpu.s")
  machineCards([CardGpu, CardIo])
  cpuReset()
  cpuLoadRom(rom)
  cpuBootRom()
  pushKey(ord('A'))
  var n = 0
  var sawPost: set[uint8] = {}
  while n < 3_000_000 and cpuStep() == sOk:
    sawPost.incl(uint8(mem[0xf000] and 0xff))
    inc n
  expectTrue("boot chain halted (kernel ran)", HF)
  for code in [0x01u8, 0x02u8, 0x04u8, 0x08u8, 0x10u8, 0x20u8, 0x40u8, 0x80u8]:
    expectTrue("POST code $" & toHex(int(code), 2), code in sawPost)
  expect("slot table from the real boot ROM", mem[0x0002], CardGpu)
  expect("slot table slot 2", mem[0x0003], CardIo)
  let g = gpuCard()
  expect("banner on the console", int(simcard_gpu_cell(g, 0, 0)) and 0xff, ord('C'))
  expect("banner 'U'", int(simcard_gpu_cell(g, 1, 0)) and 0xff, ord('U'))
  expect("kernel output after the banner", int(simcard_gpu_cell(g, 0, 1)) and 0xff, ord('H'))
  expect("kernel read a key", mem[0x2001], ord('A'))
  ioModel = imLegacy

run testBootChain

proc runBootWithRom(path: string; maxSteps = 3_000_000): int =
  ## Boot from the given ROM image; returns the final GPO value.
  machineCards([CardGpu, CardIo])
  cpuReset()
  cpuLoadRom(path)
  cpuBootRom()
  var n = 0
  while n < maxSteps and cpuStep() == sOk:
    inc n
  result = mem[0xf000] and 0xff
  ioModel = imLegacy

proc corruptRom(src, dest: string; offset: int; value: uint8; fixHeaderSum = false) =
  ## Patch one ROM byte. With fixHeaderSum the header checksum is recomputed,
  ## so the boot ROM reaches the check the test is actually aiming at.
  var data = readFile(src)
  data[offset] = char(value)
  if fixHeaderSum:
    var sum = 0
    for i in 0x800..0x80c:
      sum += int(uint8(data[i]))
    data[0x80d] = char(uint8((-sum) and 0xff))
  writeFile(dest, data)

proc testBootFailures() =
  ## BOOT-002: each failure path halts with its specified LED code.
  echo "== boot ROM failure paths =="
  let good = rootDir / "build" / "rom" / "test.rom"
  let bad = rootDir / "build" / "rom" / "bad.rom"

  corruptRom(good, bad, 0x800, uint8(ord('X')))          # magic
  expect("bad magic halts with $90", runBootWithRom(bad), 0x90)

  corruptRom(good, bad, 0x804, 9)                        # header version
  expect("bad version halts with $90", runBootWithRom(bad), 0x90)

  corruptRom(good, bad, 0x80d, 0x00)                     # header checksum
  expect("bad header checksum halts with $90", runBootWithRom(bad), 0x90)

  corruptRom(good, bad, 0x809, 0xd0, fixHeaderSum = true)   # length high byte: too big
  expect("oversized kernel halts with $91", runBootWithRom(bad), 0x91)

  corruptRom(good, bad, 0x80c, 0x01, fixHeaderSum = true)   # body checksum
  expect("bad body checksum halts with $a0", runBootWithRom(bad), 0xa0)

  # a card-less machine still boots (no console, no banner)
  machineCards([])
  cpuReset()
  cpuLoadRom(good)
  cpuBootRom()
  var n = 0
  while n < 3_000_000 and cpuStep() == sOk:
    inc n
  expectTrue("boots with no cards fitted", HF)
  expect("slot table empty", mem[0x0002], 0)
  ioModel = imLegacy

run testBootFailures

proc gpuLine(g: SimCard; row: int; len = 80): string =
  ## Read one row of text off the graphics card.
  for col in 0..<len:
    let cell = int(simcard_gpu_cell(g, cint(col), cint(row)))
    result.add(char(cell and 0xff))
  result = result.strip(leading = false)

proc gpuFind(g: SimCard; want: string): int =
  ## Row showing `want`, or -1.
  for row in 0..29:
    if gpuLine(g, row).contains(want):
      return row
  -1

proc buildKernelRom(): string =
  ## Assemble the real kernel and the boot ROM into build/rom/kernel.rom.
  let outDir = rootDir / "build" / "rom"
  createDir(outDir)
  var r = execCmdEx("cd " & quoteShell(kernelDir) & " && bash assemble.sh")
  if r.exitCode != 0: raise newException(IOError, "kernel build: " & r.output)
  r = execCmdEx("python3 " & quoteShell(rootDir / "tools" / "as.py") & " " &
                quoteShell(rootDir / "rom" / "boot.s") & " " & quoteShell(outDir / "boot.bin") &
                " 0xe000,0xe600,0x0f00")
  if r.exitCode != 0: raise newException(IOError, "boot ROM: " & r.output)
  r = execCmdEx("python3 " & quoteShell(rootDir / "tools" / "mkrom.py") & " " &
                quoteShell(outDir / "boot.bin") & " " & quoteShell(kernelDir / "kernel.o") &
                " -o " & quoteShell(outDir / "kernel.rom"))
  if r.exitCode != 0: raise newException(IOError, "mkrom: " & r.output)
  outDir / "kernel.rom"

proc testKernelOnCards() =
  ## KRN-001: the real kernel, booted from ROM, reaches the BASIC prompt on
  ## the graphics card and answers a typed command from the IO card.
  echo "== kernel on the M1 machine =="
  let rom = buildKernelRom()
  machineCards([CardGpu, CardIo])
  cpuReset()
  cpuLoadRom(rom)
  cpuBootRom()
  let g = gpuCard()

  # run until the kernel is waiting for a key
  var n = 0
  while n < 6_000_000 and not waiting:
    if cpuStep() != sOk: break
    inc n
  expectTrue("kernel reached the keyboard wait", waiting)
  expectTrue("BASIC banner on screen", gpuFind(g, "CUPC/8 BASIC") >= 0)
  expectTrue("prompt on screen", gpuFind(g, ">>") >= 0)

  # type "help" and Enter, then let the kernel answer
  for ch in "help" & "\r":
    pushKey(ord(ch))
    var m = 0
    while m < 400_000 and not waiting:
      if cpuStep() != sOk: break
      inc m
    if waiting:
      discard cpuStep()          # let WAI see the IRQ
  n = 0
  while n < 2_000_000 and not waiting:
    if cpuStep() != sOk: break
    inc n
  expectTrue("typed command echoed", gpuFind(g, "help") >= 0)
  expectTrue("help output", gpuFind(g, "NEW RUN CLR") >= 0)
  ioModel = imLegacy

run testKernelOnCards

proc settle(limit = 2_000_000) =
  var n = 0
  while n < limit and not waiting:
    if cpuStep() != sOk: break
    inc n

proc typeLine(line: string) =
  for ch in line & "\r":
    pushKey(ord(ch))
    var m = 0
    while m < 400_000 and not waiting:
      if cpuStep() != sOk: break
      inc m
    if waiting:
      discard cpuStep()          # let WAI see the IRQ
  settle(20_000_000)

proc basicRun(rom: string; prog: openArray[string]): seq[string] =
  ## Boot, type the program and RUN it; the screen lines between "run" and
  ## "DONE." (blank lines dropped).
  machineCards([CardGpu, CardIo])
  cpuReset()
  cpuLoadRom(rom)
  cpuBootRom()
  settle(6_000_000)
  for line in prog:
    typeLine(line)
  typeLine("run")
  let g = gpuCard()
  var rows: seq[string]
  for row in 0..29:
    rows.add(gpuLine(g, row))
  var start = -1
  for i in countdown(rows.high, 0):
    if rows[i].endsWith(">> run"):
      start = i
      break
  if start < 0:
    return @["<no run on screen>"]
  for i in start + 1 .. rows.high:
    if rows[i] == "DONE.":
      return
    if rows[i].len > 0:
      result.add(rows[i])
  result.add("<no DONE.>")

proc testBasicPrograms() =
  ## KRN-003: BASIC programs typed into the real kernel give the output
  ## worked out by hand (uBASIC semantics, 8-bit values that wrap).
  echo "== BASIC programs =="
  let rom = buildKernelRom()
  let cases: seq[(string, seq[string], seq[string])] = @[
    ("precedence", @["10 print 1+2*3"], @["7"]),
    ("8-bit wrap", @["10 print 200+100"], @["44"]),
    ("division", @["10 print 17/5", "20 print 20-3*4"], @["3", "8"]),
    ("string", @["10 print \"hello\""], @["hello"]),
    ("variables", @["10 let a = 7", "20 let b = a * 3", "30 print b - a"], @["14"]),
    ("for/next", @["10 for i = 1 to 4", "20 print i", "30 next i"], @["1", "2", "3", "4"]),
    ("if/then/else", @["10 let a = 7", "20 if a > 5 then print 1 else print 0",
                       "30 if a < 5 then print 1 else print 0"], @["1", "0"]),
    ("goto loop", @["10 let a = 0", "20 let a = a + 3", "30 if a < 9 then goto 20", "40 print a"], @["9"]),
    ("gosub", @["10 gosub 100", "20 print 2", "30 end", "100 print 1", "110 return"], @["1", "2"]),
    ("nested for", @["10 for i = 1 to 2", "20 for j = 1 to 2", "30 print i * 10 + j",
                     "40 next j", "50 next i"], @["11", "12", "21", "22"]),
    # each of these pins one fixed bug (kernel/ubasic*.s, printf.s, math.s)
    ("parentheses", @["10 print (1+2)*(3+4)", "20 print 2*(3+(4-1))"], @["21", "12"]),
    ("equals", @["10 if 3 = 3 then print 1 else print 0", "20 if 3 = 4 then print 1 else print 0"],
     @["1", "0"]),
    ("spaces", @["10 print   1  +   2"], @["3"]),
    ("zero", @["10 print 0", "20 print 5-5"], @["0", "0"]),
    ("rem", @["10 rem nothing here", "20 print 4"], @["4"]),
    ("mod, divide by 0", @["10 print 17 % 5", "20 print 7 / 0"], @["2", "0"]),
    ("separators", @["10 print \"x\", 5", "20 print 1; 2"], @["x 5", "12"]),
    ("let in then", @["10 if 1 < 2 then let a = 5 else let a = 6", "20 print a"], @["5"]),
    ("gosub nest", @["10 gosub 100", "20 print 3", "30 end", "100 gosub 200", "110 print 2",
                     "120 return", "200 print 1", "210 return"], @["1", "2", "3"]),
    ("rem last", @["10 print 6", "20 rem the end"], @["6"]),
    ("poke/peek", @["10 poke 208, 0, 77", "20 peek 208, 0, a", "30 print a"], @["77"]),
    ("poke expr", @["10 let h = 200", "20 poke h + 8, 1 * 5, 3 * 11", "30 peek 208, 5, b",
                    "40 print b + 1"], @["34"]),
    ("longest line", @["10 print " & "1+".repeat(34) & "1"], @["35"]),         # 78 characters
    ("line cut at 78", @["10 print " & "1+".repeat(38) & "1"], @["35"]),        # the rest is dropped
  ]
  for (name, prog, want) in cases:
    let got = basicRun(rom, prog)
    if got == want:
      ok("BASIC " & name)
    else:
      fail("BASIC " & name & ": got " & $got & ", want " & $want)
  ioModel = imLegacy

run testBasicPrograms

proc runGuest(steps: int) =
  ## guest time passes (the kernel waits in WAI; the cards tick)
  for i in 0..<steps:
    if cpuStep() != sOk: break

proc testKernelOnEink() =
  ## KRN-007: the e-ink graphics card (fw/eink/core with the UC8179 model
  ## as its panel) as the console: the kernel finds it by INFO, BASIC runs on
  ## it, the panel shows the prompt after the card's own refresh, and the
  ## terminal's `refresh` asks for a clean full refresh; on HDMI, INFO says
  ## HDMI and `refresh` does nothing.
  echo "== kernel on the e-ink card =="
  let rom = buildKernelRom()
  let table = loadMap(kernelDir / "kernel.map")
  let kindAt = table.resolve("gpu_kind")
  expectTrue("gpu_kind in the kernel map", kindAt >= 0)
  for (card, name) in [(CardEink, "5.83in"), (CardEink750, "7.5in")]:
    machineCards([card, CardIo])
    cpuReset()
    cpuLoadRom(rom)
    cpuBootRom()
    let g = gpuCard()
    settle(6_000_000)
    expectTrue(name & ": prompt in the card's text", gpuFind(g, ">>") >= 0)
    expect(name & ": INFO says e-paper", mem[kindAt], 1)
    runGuest(1_500_000)                      # 1.5 s: the power-on clean refresh (x0.1)
    expect(name & ": one clean refresh at power-on", int(simcard_eink_refreshes(g, 0)), 1)
    # the glass: the banner's row (row 1, text in the middle) has ink
    var frame = newSeq[uint32](GpuOutW * GpuOutH)
    simcard_render(g, addr frame[0])
    var ink = 0
    for y in 16..31:
      for x in 0..<GpuOutW:
        if frame[y * GpuOutW + x] == 0: inc ink
    expectTrue(name & ": the banner is on the glass", ink > 200)
    typeLine("10 print 6*7")
    typeLine("run")
    expectTrue(name & ": the program ran", gpuFind(g, "42") >= 0)
    typeLine("refresh")
    runGuest(1_500_000)
    expect(name & ": refresh asks for a clean refresh", int(simcard_eink_refreshes(g, 0)), 2)
    expectTrue(name & ": partial refreshes for the typing", simcard_eink_refreshes(g, 3) >= 1)
    expect(name & ": the panel model saw no command the chip would ignore", int(simcard_eink_errors(g)), 0)
  # HDMI: INFO says so, and refresh is harmless
  machineCards([CardGpu, CardIo])
  cpuReset()
  cpuLoadRom(rom)
  cpuBootRom()
  settle(6_000_000)
  expect("HDMI: INFO says HDMI", mem[kindAt], 0)
  typeLine("refresh")
  expectTrue("HDMI: refresh does nothing and the prompt returns", gpuFind(gpuCard(), "refresh") >= 0 and
             gpuFind(gpuCard(), "ERROR") < 0)
  ioModel = imLegacy

run testKernelOnEink

proc testProgramFull() =
  ## KRN-003: the 256-byte program buffer refuses a line that does not fit
  ## ("PROGRAM FULL") instead of overwriting memory, and keeps working. Each
  ## line below is 31 characters plus CR: 7 fit, the 8th does not.
  echo "== BASIC program buffer full =="
  let rom = buildKernelRom()
  var prog: seq[string]
  for i in 1..8:
    prog.add($(i * 10) & " print \"" & "a".repeat(20) & "\"")
  let got = basicRun(rom, prog)
  let g = gpuCard()
  expectTrue("the 8th line was refused", gpuFind(g, "PROGRAM FULL") >= 0)
  expectTrue("the 7 lines that fit ran", got == newSeqWith(7, "a".repeat(20)))
  ioModel = imLegacy

run testProgramFull

proc testBasicLeds() =
  ## KRN-003: POKE reaches the I/O space: the GPO LEDs at $f000
  echo "== BASIC poke to the LEDs =="
  let rom = buildKernelRom()
  let got = basicRun(rom, @["10 poke 240, 0, 165"])
  expectTrue("program ran", got.len == 0)
  expect("GPO after poke 240, 0, 165", mem[0xf000], 0xa5)
  ioModel = imLegacy

run testBasicLeds

proc testBasicJunkRam() =
  ## KRN-003: the kernel must not rely on RAM being zero at power-up (the
  ## SRAM comes up with junk). Its .bss (the BASIC program buffer and its
  ## index) was never cleared: on the whole-machine emulator the typed line
  ## went in after junk and RUN gave "TOKENIZER ERROR!".
  echo "== BASIC on power-up junk RAM =="
  let rom = buildKernelRom()
  ramJunk = true
  let got = basicRun(rom, @["10 print 6*7"])
  ramJunk = false
  if got == @["42"]:
    ok("BASIC on junk RAM")
  else:
    fail("BASIC on junk RAM: got " & $got & ", want @[\"42\"]")
  ioModel = imLegacy

run testBasicJunkRam

proc testBasicJunkRamVariables() =
  ## KRN-003: RUN starts every BASIC variable at 0. ubasic_init cleared the
  ## GOSUB and FOR stacks but not ub_variables, so on power-up junk RAM an
  ## unset variable printed junk: `print hi` gave 223236 on the whole-machine
  ## emulator (sim.nim zeroes RAM, so no other test saw it).
  echo "== BASIC variables on power-up junk RAM =="
  let rom = buildKernelRom()
  ramJunk = true
  let got = basicRun(rom, @["10 print a", "20 print z"])
  ramJunk = false
  if got == @["0", "0"]:
    ok("BASIC variables start at 0 on junk RAM")
  else:
    fail("BASIC variables on junk RAM: got " & $got & ", want @[\"0\", \"0\"]")
  ioModel = imLegacy

run testBasicJunkRamVariables

proc testSlotIrqShared() =
  ## KRN-005: a card holding IRQ_n low (slot 3 here) must not hide another
  ## card's IRQ: the kernel sleeps in WAI for keys, and every key must wake it.
  echo "== slot IRQs shared =="
  let rom = buildKernelRom()
  machineCards([CardGpu, CardIo])
  cpuReset()
  cpuLoadRom(rom)
  cpuBootRom()
  settle(6_000_000)
  expectTrue("kernel ready for input", waiting)
  heldSlotIrq = 0x04
  typeLine("help")
  let g = gpuCard()
  expectTrue("typed while slot 3 held its IRQ", gpuFind(g, ">> help") >= 0)
  expectTrue("the command ran", gpuFind(g, "NEW RUN CLR") >= 0)
  heldSlotIrq = 0
  ioModel = imLegacy

run testSlotIrqShared

proc testKernelNetwork() =
  ## KRN-004: the kernel's "net" command. "net join SSID PASSWORD" joins
  ## through the Wi-Fi card and prints the address; "net get HOST PORT"
  ## sends an HTTP/1.0 GET to a server running in this process and prints
  ## the reply until the server closes; "net" shows the link; anything else
  ## prints the usage.
  echo "== kernel networking =="
  let rom = buildKernelRom()
  machineCards([CardGpu, CardIo, CardWifi])
  cpuReset()
  cpuLoadRom(rom)
  cpuBootRom()
  let g = gpuCard()

  var server = newSocket()
  server.setSockOpt(OptReuseAddr, true)
  try:
    server.bindAddr(Port(8088), "127.0.0.1")
  except OSError:
    fail("port 8088 is busy; skipping the network test")
    ioModel = imLegacy
    return
  server.listen()

  proc runUntilShown(want: string, limit = 8_000_000): bool =
    var n = 0
    while n < limit:
      if cpuStep() != sOk: break
      inc n
      if (n mod 5000) == 0 and gpuFind(g, want) >= 0:
        return true
    gpuFind(g, want) >= 0

  settle(6_000_000)
  expectTrue("kernel ready for input", waiting)

  typeLine("net bogus")
  expectTrue("an unknown subcommand prints the usage", runUntilShown("net join SSID PASSWORD", 400_000))

  typeLine("net join cupc8 password")
  expectTrue("net join prints the address", runUntilShown("joined, address 127.0.0.1"))
  settle()
  typeLine("net")
  expectTrue("net shows the link", runUntilShown("link up, address 127.0.0.1", 2_000_000))
  settle()

  # serve the request while the machine keeps running (never block: the CPU
  # only advances in this loop)
  # everything but the Enter, which goes in below: the server must be
  # serving while the command runs
  for ch in "net get localhost 8088":
    pushKey(ord(ch))
    settle(400_000)
    if waiting: discard cpuStep()
  pushKey(13)
  var client: Socket
  var accepted = false
  var request = ""
  var served = false
  var n = 0
  while n < 12_000_000:
    if cpuStep() != sOk: break
    inc n
    if (n mod 1000) == 0:
      if gpuFind(g, "CUPC8-OK") >= 0 or gpuFind(g, "net timeout") >= 0:
        break
      if not accepted:
        var readable = @[server.getFd]
        if selectRead(readable, 0) > 0:
          client = newSocket()
          server.accept(client)
          client.getFd.setBlocking(false)
          accepted = true
      elif not served:
        var buf = newString(256)
        let got = client.getFd.recv(addr buf[0], 256, 0)
        if got > 0:
          request.add(buf[0 ..< got])
        if request.endsWith("\r\n\r\n"):
          client.send("HTTP/1.0 200 OK\r\n\r\nCUPC8-OK\r\n")
          client.close()
          served = true
  expectTrue("the request is an HTTP/1.0 GET with the host", request == "GET / HTTP/1.0\r\nHost: localhost\r\n\r\n")
  if request.len > 0 and request != "GET / HTTP/1.0\r\nHost: localhost\r\n\r\n":
    echo "  request: ", request.escape
  if gpuFind(g, "CUPC8-OK") < 0:
    echo "screen:"
    for row in 0..29:
      let line = gpuLine(g, row)
      if line.len > 0: echo "  |" & line
  expectTrue("the reply is printed up to the server closing", gpuFind(g, "CUPC8-OK") >= 0 and gpuFind(g, "HTTP/1.0 200 OK") >= 0)
  server.close()
  ioModel = imLegacy

run testKernelNetwork

proc testKernelNetWeakPower() =
  ## KRN-004: on a USB source under 3 A (SYSCTL.PWR_HI = 0) the "net"
  ## command refuses to start the radio, and says why.
  echo "== kernel networking on a weak USB source =="
  let rom = buildKernelRom()
  machineCards([CardGpu, CardIo, CardWifi])
  cpuReset()
  pwrHi = false
  cpuLoadRom(rom)
  cpuBootRom()
  let g = gpuCard()
  var n = 0
  while n < 6_000_000 and not waiting:
    if cpuStep() != sOk: break
    inc n
  expectTrue("kernel ready for input", waiting)
  for ch in "net" & "\r":
    pushKey(ord(ch))
    var m = 0
    while m < 400_000 and not waiting:
      if cpuStep() != sOk: break
      inc m
    if waiting:
      discard cpuStep()
  n = 0
  while n < 400_000 and gpuFind(g, "net off") < 0:
    if cpuStep() != sOk: break
    inc n
  expectTrue("weak source refused with a message", gpuFind(g, "USB power under 3A: net off") >= 0)
  expectTrue("no network timeout (the radio was never used)", gpuFind(g, "net timeout") < 0)
  pwrHi = true
  ioModel = imLegacy

run testKernelNetWeakPower

# ---------------------------------------------------------------------------
# the storage card: BASIC SAVE, LOAD, DIR, DEL (kernel/storage.s, ubasic.s)
# ---------------------------------------------------------------------------

let storeDir = rootDir / "build" / "storage"

proc fatcheck(args: string): tuple[output: string, exitCode: int] =
  execCmdEx("python3 " & quoteShell(toolsDir / "fatcheck.py") & " " & args)

proc storageCard(): SimCard =
  for c in slots:
    if not c.isNil and simcard_type(c) == CardStorage:
      return c
  SimCard(nil)

proc bootStorage(rom, img: string; wp = false; latencyMs = 0; fitted = true) =
  ## Power up with the storage card in slot 4 holding the image (none: "").
  if fitted:
    machineCards([CardGpu, CardIo, 0, CardStorage])
    let s = storageCard()
    if img.len > 0 and simcard_storage_image(s, img, cint(wp)) != 0:
      fail("cannot insert " & img)
    simcard_storage_latency(s, uint32(latencyMs))
  else:
    machineCards([CardGpu, CardIo])
  cpuReset()
  cpuLoadRom(rom)
  cpuBootRom()
  settle(6_000_000)

proc cmdOutput(cmd: string; stopAt = ">>"): seq[string] =
  ## Type a command; the non-blank screen lines after it, up to the next
  ## prompt (or the line starting with stopAt).
  typeLine(cmd)
  let g = gpuCard()
  var rows: seq[string]
  for row in 0..29:
    rows.add(gpuLine(g, row))
  var start = -1
  for i in countdown(rows.high, 0):
    if rows[i].endsWith(">> " & cmd):
      start = i
      break
  if start < 0:
    return @["<no " & cmd & " on screen>"]
  for i in start + 1 .. rows.high:
    if rows[i].startsWith(stopAt):
      break
    if rows[i].len > 0:
      result.add(rows[i])

proc runOutput(): seq[string] =
  result = cmdOutput("run", "DONE.")

proc testStorage() =
  ## KRN-006: BASIC SAVE, LOAD, DIR and DEL through the storage card model
  ## (fw/storage/core on a FAT image): a program saved, the machine powered
  ## off and on, loaded and run; the saved file as a PC reads it; a PC's file
  ## loaded; the error messages for no card, no storage card, a full card, a
  ## write-protected one, a missing file and a bad name; and a card that
  ## keeps READ "not ready" for 30 ms on every command.
  echo "== storage card: SAVE, LOAD, DIR, DEL =="
  let rom = buildKernelRom()
  createDir(storeDir)
  let img = storeDir / "card.img"
  var r = fatcheck("blank " & quoteShell(img) & " 4096")
  if r.exitCode != 0:
    fail("fatcheck blank: " & r.output)
    return
  # files a PC wrote: CR LF, a blank line, a line without a number, no last line end
  writeFile(storeDir / "pc.txt", "10 print \"from a pc\"\r\n\r\nno number here\r\n20 print 5 * 5\r\n30 print \"no line end\"")
  writeFile(storeDir / "big.dat", "x".repeat(70000))
  discard fatcheck("put " & quoteShell(img) & " PC.BAS " & quoteShell(storeDir / "pc.txt"))
  discard fatcheck("put " & quoteShell(img) & " BIG.DAT " & quoteShell(storeDir / "big.dat"))
  var long = ""
  for i in 1..9:
    long.add($(i * 10) & " print \"" & "a".repeat(20) & "\"\r\n")    # 7 of these fit
  writeFile(storeDir / "long.txt", long)
  discard fatcheck("put " & quoteShell(img) & " LONG.BAS " & quoteShell(storeDir / "long.txt"))

  let prog = @["10 print \"storage card test\"", "20 for i = 1 to 3", "30 print i * 11", "40 next i",
               "50 let a = 6", "60 print a * 7",
               "70 rem a long line so that the program is longer than one chunk", "80 print \"end\""]
  let want = @["storage card test", "11", "22", "33", "42", "end"]
  var text = ""
  for line in prog:
    text.add(line & "\r\n")

  bootStorage(rom, img)
  for line in prog:
    typeLine(line)
  expectTrue("SAVE", cmdOutput("save \"prog.bas\"") == @["SAVED"])
  let expectDir = storeDir / "expect"
  removeDir(expectDir)
  createDir(expectDir)
  writeFile(expectDir / "PROG.BAS", text)
  r = fatcheck("check " & quoteShell(img) & " " & quoteShell(expectDir))
  if r.exitCode != 0: echo r.output
  expectTrue("the saved program as a PC reads it (text, CR LF)", r.exitCode == 0)

  # off and on again: LOAD, RUN
  bootStorage(rom, img)
  expectTrue("LOAD after a power cycle", cmdOutput("load \"prog.bas\"") == @["LOADED"])
  let ran = runOutput()
  if ran != want: echo "got ", ran
  expectTrue("the loaded program runs", ran == want)

  # DIR: names and sizes (a 32-bit size too)
  let dir = cmdOutput("dir")
  if dir.len != 4: echo "dir ", dir
  expectTrue("DIR lists the saved program", ("PROG.BAS     " & $text.len) in dir)
  expectTrue("DIR lists a PC's file", ("PC.BAS       " & $getFileSize(storeDir / "pc.txt")) in dir)
  expectTrue("DIR prints a size over 65535", "BIG.DAT      70000" in dir)

  # a file a PC wrote
  expectTrue("LOAD a PC's file", cmdOutput("load \"pc.bas\"") == @["LOADED"])
  let pcRan = runOutput()
  if pcRan != @["from a pc", "25", "no line end"]: echo "got ", pcRan
  expectTrue("a PC's file runs (CR LF, blank and unnumbered lines, no last line end)",
             pcRan == @["from a pc", "25", "no line end"])

  # a file longer than the program buffer: the load stops at the first line that does not fit
  expectTrue("LOAD more than fits", cmdOutput("load \"long.bas\"") == @["PROGRAM FULL", "LOADED"])
  expectTrue("what fitted runs", runOutput() == newSeqWith(7, "a".repeat(20)))

  # DEL
  expectTrue("DEL", cmdOutput("del \"prog.bas\"").len == 0)
  expectTrue("DIR after DEL", cmdOutput("dir").len == 3)
  expectTrue("LOAD a deleted file", cmdOutput("load \"prog.bas\"") == @["file not found"])
  expectTrue("DEL a missing file", cmdOutput("del \"nothing\"") == @["file not found"])
  r = fatcheck("check " & quoteShell(img) & " --absent PROG.BAS --size PC.BAS=" & $getFileSize(storeDir / "pc.txt"))
  if r.exitCode != 0: echo r.output
  expectTrue("deleted as a PC sees it", r.exitCode == 0)

  # names
  expectTrue("SAVE without a name", cmdOutput("save") == @["SAVE, LOAD or DEL \"NAME\""])
  expectTrue("SAVE with a bad name", cmdOutput("save \"toolongname.bas\"") == @["bad file name"])
  expectTrue("an unquoted name", cmdOutput("save plain.bas") == @["SAVED"])

  # a card busy for 30 ms on every command: READ retries until it answers
  bootStorage(rom, img, latencyMs = 30)
  for line in prog:
    typeLine(line)
  expectTrue("SAVE to a slow card", cmdOutput("save \"slow.bas\"") == @["SAVED"])
  typeLine("new")
  expectTrue("LOAD from a slow card", cmdOutput("load \"slow.bas\"") == @["LOADED"])
  expectTrue("the program from the slow card runs", runOutput() == want)

  # write-protected: nothing written, reading is fine
  bootStorage(rom, img, wp = true)
  for line in prog:
    typeLine(line)
  expectTrue("SAVE to a write-protected card", cmdOutput("save \"wp.bas\"") == @["write protected"])
  expectTrue("DEL on a write-protected card", cmdOutput("del \"pc.bas\"") == @["write protected"])
  expectTrue("LOAD from a write-protected card", cmdOutput("load \"slow.bas\"") == @["LOADED"])

  # a USB source under 3 A (PWR_HI low): writes refused, reading is fine
  pwrHi = false
  bootStorage(rom, img)
  for line in prog:
    typeLine(line)
  expectTrue("SAVE below 3 A", cmdOutput("save \"weak.bas\"") == @["USB power under 3A: SD writes off"])
  expectTrue("DEL below 3 A", cmdOutput("del \"slow.bas\"") == @["USB power under 3A: SD writes off"])
  expectTrue("LOAD below 3 A", cmdOutput("load \"slow.bas\"") == @["LOADED"])
  expectTrue("the file loaded below 3 A runs", runOutput() == want)
  expectTrue("DIR below 3 A lists the card", cmdOutput("dir").len > 1)
  pwrHi = true
  bootStorage(rom, img)
  expectTrue("the card as it was: no WEAK.BAS, SLOW.BAS still there",
             cmdOutput("load \"weak.bas\"") == @["file not found"] and
             cmdOutput("load \"slow.bas\"") == @["LOADED"])

  # no card in the socket, and no storage card at all
  bootStorage(rom, "")
  for line in prog:
    typeLine(line)
  expectTrue("SAVE with no SD card", cmdOutput("save \"x.bas\"") == @["no SD card"])
  expectTrue("LOAD with no SD card", cmdOutput("load \"x.bas\"") == @["no SD card"])
  expectTrue("DIR with no SD card", cmdOutput("dir") == @["no SD card"])
  bootStorage(rom, "", fitted = false)
  expectTrue("SAVE with no storage card", cmdOutput("save \"x.bas\"") == @["no storage card"])
  expectTrue("DIR with no storage card", cmdOutput("dir") == @["no storage card"])

  # a full card
  let full = storeDir / "full.img"
  discard fatcheck("blank " & quoteShell(full) & " 128")
  r = fatcheck("fill " & quoteShell(full))
  if r.exitCode != 0: echo r.output
  bootStorage(rom, full)
  for line in prog:
    typeLine(line)
  expectTrue("SAVE to a full card", cmdOutput("save \"prog.bas\"") == @["card full"])
  ioModel = imLegacy

run testStorage

# ---------------------------------------------------------------------------
# the kernel API, programs at $7000 (kernel/api.s, sys.s; kernel-api.md)
# ---------------------------------------------------------------------------

proc kernelMap(): tuple[syms: Table[int, string], lines: seq[string]] =
  for line in lines(kernelDir / "kernel.map"):
    result.lines.add(line)
    let f = line.splitWhitespace()
    if f.len >= 3 and f[0] == "sym":
      result.syms[parseHexInt(f[1])] = f[2]

proc incDefines(text: string): seq[(string, int)] =
  ## the `%define NAME $hex` lines of an api.inc
  for line in text.splitLines():
    let f = line.splitWhitespace()
    if f.len >= 3 and f[0] == "%define" and f[2].startsWith("$"):
      result.add((f[1], parseHexInt(f[2][1 .. ^1])))

proc defineOf(defs: seq[(string, int)]; name: string): int =
  result = -1
  for (n, v) in defs:
    if n == name: return v

proc testKernelLayout() =
  ## KRN-010: the kernel's code, data and bss stay in their areas
  ## (memory-map.md): code $1000-$4fff, data $5000-$5fff, bss $6000-$6eff;
  ## $6f00 is the API block and $7000- the user program's.
  echo "== kernel memory layout =="
  let assembled = execCmdEx("bash assemble.sh", options = {poUsePath}, workingDir = kernelDir)
  if assembled.exitCode != 0:
    fail("kernel assembly failed: " & assembled.output)
    return
  var codeEnd, dataEnd, bssEnd = 0
  var bases = ""
  for line in kernelMap().lines:
    let f = line.splitWhitespace()
    if f.len == 0: continue
    case f[0]
    of "base": bases = line
    of "line": codeEnd = max(codeEnd, parseHexInt(f[1]) + 3)     # an instruction is at most 3 bytes
    of "data": dataEnd = max(dataEnd, parseHexInt(f[1]) + parseInt(f[2]))
    of "bss": bssEnd = max(bssEnd, parseHexInt(f[1]) + parseInt(f[2]))
    else: discard
  expectTrue("assembled for code $1000, data $5000, bss $6000 (" & bases & ")",
             bases == "base 0x1000 data 0x5000 bss 0x6000")
  expectTrue("code ends by $4fff (at $" & toHex(codeEnd - 1, 4) & ")", codeEnd <= 0x5000)
  expectTrue("data ends by $5fff (at $" & toHex(dataEnd - 1, 4) & ")", dataEnd <= 0x6000)
  expectTrue("bss ends by $6eff (at $" & toHex(bssEnd - 1, 4) & ")", bssEnd <= 0x6f00)

run testKernelLayout

proc testKernelApi() =
  ## KRN-010: the jump table (kernel/api.s, from $1003: 8 groups x 16 entries
  ## x 3 bytes) against kernel/api.inc: every entry is a B; a named entry
  ## goes to api_<name> (or api_none, a stub for now); every other to
  ## api_none. Entries are only added: every committed api.inc's entries are
  ## still there at the same addresses.
  echo "== kernel API table =="
  let assembled = execCmdEx("bash assemble.sh", options = {poUsePath}, workingDir = kernelDir)
  if assembled.exitCode != 0:
    fail("kernel assembly failed: " & assembled.output)
    return
  let image = readFile(kernelDir / "kernel.o")
  let syms = kernelMap().syms
  let defs = incDefines(readFile(kernelDir / "api.inc"))
  var named = initTable[int, string]()
  for (name, value) in defs:
    if value >= 0x1003 and value < 0x1183:
      if (value - 0x1003) mod 3 != 0:
        fail(name & " $" & toHex(value, 4) & " is not an entry's address")
      elif named.hasKey(value):
        fail(name & " and " & named[value] & " share $" & toHex(value, 4))
      else:
        named[value] = name
  var bad: seq[string]
  var stubs: seq[string]
  for g in 0..7:
    for n in 0..15:
      let a = 0x1003 + 48 * g + 3 * n
      let o = a - 0x1000
      if image[o].ord != 0xb0:
        bad.add("$" & toHex(a, 4) & " is not a B")
        continue
      let target = image[o + 1].ord or (image[o + 2].ord shl 8)
      let sym = syms.getOrDefault(target, "$" & toHex(target, 4))
      if named.hasKey(a):
        let want = "api_" & named[a][4 .. ^1].toLowerAscii
        if sym == "api_none":
          stubs.add(named[a])
        elif sym != want:
          bad.add(named[a] & " ($" & toHex(a, 4) & ") goes to " & sym & ", not " & want)
      elif sym != "api_none":
        bad.add("$" & toHex(a, 4) & " goes to " & sym & " but api.inc names no entry there")
  for b in bad: echo "  ", b
  expectTrue("the table matches api.inc (" & $named.len & " entries named)", bad.len == 0)
  if stubs.len > 0: echo "  stubs (api_none for now): ", stubs.join(" ")
  expectTrue("the table ends at $1182: api_none follows it",
             syms.getOrDefault(0x1183, "") == "api_none")
  # the API block's addresses: the kernel's (api.s) and the programs' (api.inc)
  for (name, value) in incDefines(readFile(kernelDir / "api.s")):
    expect(name & " in api.inc as in api.s", defineOf(defs, name), value, 4)
  # only added, never moved: every committed api.inc against this one
  let log = execCmdEx("git log --format=%H -- kernel/api.inc", workingDir = rootDir)
  var versions = 0
  var moved: seq[string]
  for commit in log.output.splitLines():
    if commit.len != 40: continue
    let old = execCmdEx("git show " & commit & ":kernel/api.inc", workingDir = rootDir)
    if old.exitCode != 0: continue
    inc versions
    for (name, value) in incDefines(old.output):
      let now = defineOf(defs, name)
      if now != value:
        moved.add(name & " was $" & toHex(value, 4) & " in " & commit[0 .. 6] & ", now " &
                  (if now < 0: "gone" else: "$" & toHex(now, 4)))
  for m in moved: echo "  ", m
  expectTrue("no entry of " & $versions & " committed api.inc versions moved or went", moved.len == 0)

run testKernelApi

proc mkprg(src, dest: string) =
  let r = execCmdEx("python3 " & quoteShell(toolsDir / "mkprg.py") & " " & quoteShell(src) &
                    " -o " & quoteShell(dest))
  if r.exitCode != 0:
    raise newException(IOError, "mkprg " & src & ": " & r.output)

proc runUntil(cond: proc (): bool; limit: int): bool =
  var n = 0
  while n < limit:
    if cond(): return true
    if cpuStep() != sOk: break
    inc n
  cond()

proc testApiProgram() =
  ## KRN-011: a program at $7000 (tools/testdata/api_prog.s) calling entries
  ## of every API group, started the way `cupc8.py run` does (the body at
  ## $7000, then API_RUN = 1, which the terminal takes while it waits for a
  ## key), on HDMI with the storage card; it returns to the terminal, whose
  ## stack is as before. Then one that calls API_EXIT with bytes still on
  ## the stack.
  echo "== kernel API: a program calling every group =="
  let rom = buildKernelRom()
  createDir(storeDir)
  let img = storeDir / "api.img"
  var r = fatcheck("blank " & quoteShell(img) & " 4096")
  if r.exitCode != 0:
    fail("fatcheck blank: " & r.output)
    return
  let prg = testdata / "api_prog.prg"
  mkprg(testdata / "api_prog.s", prg)
  bootStorage(rom, img)
  expectTrue("the terminal waits for a key", waiting)
  let sp0 = SP
  expect("API_RUN is 0 after power-up", mem[ApiRun], 0)
  expectTrue("the program goes in", runProgram(readFile(prg)))
  expectTrue("the program ran to its end",
             runUntil(proc (): bool = mem[0x7e3f] == 0xa5, 30_000_000))
  expect("API_RUN 2 while it ran", mem[0x7e30], 2)
  settle(2_000_000)
  expect("API_RUN 0 again at the prompt", mem[ApiRun], 0)
  let g = gpuCard()
  expectTrue("back at the prompt", waiting and gpuFind(g, ">>") >= 0)
  expect("the terminal's stack as before", SP, sp0, 4)
  # group 0
  expect("API_VERSION", mem[0x7e00], 1)
  expect("API_BLOCK low", mem[0x7e01], 0x00)
  expect("API_BLOCK high", mem[0x7e02], 0x6f)
  expect("API_SLOTS low", mem[0x7e03], 0x02)
  expect("API_SLOTS high", mem[0x7e04], 0x00)
  # group 1
  expectTrue("API_PUTS and API_PUTC (" & gpuLine(g, 0) & ")", gpuLine(g, 0).startsWith("API HELLO!"))
  let x = int(simcard_gpu_cell(g, 10, 20))
  expect("API_GOTOXY then API_PUTC: X at 10,20", x and 0xff, ord('X'))
  expect("API_ATTR: its attribute", (x shr 8) and 0xff, 0x1e)
  expect("API_GETXY ok", mem[0x7e05], 0)
  expect("API_GETXY column", mem[0x7e06], 11)
  expect("API_GETXY row", mem[0x7e07], 20)
  expect("API_POLLKEY with no key", mem[0x7e08], 0xff)
  let p = int(simcard_gpu_cell(g, 0, 29))
  expectTrue("API_POKE: P at 0,29 in $4e", (p and 0xff) == ord('P') and ((p shr 8) and 0xff) == 0x4e)
  # group 2
  expect("API_GFX_GETPIXEL ok", mem[0x7e09], 0)
  expect("API_GFX_PIXEL then GETPIXEL", mem[0x7e0a], 42)
  expect("API_GFX_FILL_RECT then GETPIXEL", mem[0x7e0b], 7)
  expect("API_GFX_VSYNC ok", mem[0x7e0c], 0)
  # group 3, on HDMI: nothing, $ff
  expect("API_EINK_GET on HDMI", mem[0x7e0d], 0xff)
  expect("API_EINK_GET leaves $ff (first)", mem[0x7e0e], 0xff)
  expect("API_EINK_GET leaves $ff (last)", mem[0x7e0f], 0xff)
  expect("API_EINK_STATUS on HDMI", mem[0x7e10], 0xff)
  expect("API_EINK_STATUS leaves $ff", mem[0x7e11], 0xff)
  expect("API_EINK_AUTO on HDMI", mem[0x7e12], 0xff)
  # group 4
  expect("API_ST_INFO", mem[0x7e13], 0)
  expect("API_ST_INFO media: SD", mem[0x7e14], 1)
  expect("API_ST_OPEN to write", mem[0x7e15], 0)
  expect("API_ST_WRITE", mem[0x7e16], 0)
  expect("API_ST_CLOSE", mem[0x7e17], 0)
  expect("API_ST_OPEN to read", mem[0x7e18], 0)
  expect("API_ST_SEEK", mem[0x7e19], 0)
  expect("API_ST_READ", mem[0x7e1a], 0)
  expect("API_ST_READ read the 4 bytes after the seek", mem[0x7e1b], 4)
  var got = ""
  for i in 0..3: got.add(char(mem[0x7e40 + i]))
  expectTrue("API_ST_READ data: ello (" & got & ")", got == "ello")
  expect("API_ST_RENAME", mem[0x7e1c], 0)
  expect("API_ST_DIR_FIRST", mem[0x7e1d], 0)
  expect("API_ST_DIR_FIRST size", mem[0x7e1e], 5)
  expect("API_ST_DIR_FIRST name length", mem[0x7e1f], 8)
  expect("API_ST_DIR_FIRST the renamed name", mem[0x7e20], ord('2'))
  expect("API_ST_DIR_NEXT: no more", mem[0x7e21], 0xff)
  expect("API_ST_DELETE", mem[0x7e22], 0)
  expect("API_ST_OPEN a deleted file: not found", mem[0x7e23], 3)
  r = fatcheck("check " & quoteShell(img) & " --absent API.TXT --absent API2.TXT")
  if r.exitCode != 0: echo r.output
  expectTrue("the card as a PC sees it: nothing left", r.exitCode == 0)
  # groups 5 and 7: not there yet
  expect("an empty net entry: $ff", mem[0x7e24], 0xff)
  expect("... and API_ERR $ff", mem[0x7e25], 0xff)
  expect("an empty reserved entry: $ff", mem[0x7e27], 0xff)
  # group 6
  expect("API_WAIT_MS", mem[0x7e26], 0)
  let t0 = mem[0x7e28] or (mem[0x7e29] shl 8)
  let t1 = mem[0x7e2c] or (mem[0x7e2d] shl 8)
  expectTrue("API_TICKS counts the 20 ms API_WAIT_MS waited (" & $t0 & " to " & $t1 & ")",
             t1 - t0 >= 18 and t1 - t0 <= 30)

  echo "== kernel API: API_EXIT =="
  let ex = testdata / "api_exit.prg"
  mkprg(testdata / "api_exit.s", ex)
  expectTrue("the program goes in", runProgram(readFile(ex)))
  expectTrue("it ran", runUntil(proc (): bool = mem[0x7e00] == 0x5a and mem[ApiRun] == 0, 2_000_000))
  settle(2_000_000)
  expect("API_EXIT does not return", mem[0x7e00], 0x5a)
  expectTrue("back at the prompt", waiting)
  expect("the terminal's stack as before, 6 bytes left behind", SP, sp0, 4)
  expectTrue("the terminal still works", cmdOutput("10 print 7*6").len == 0 and runOutput() == @["42"])
  expectTrue("a bad header is refused", not runProgram("C8P\x02" & "junk"))
  ioModel = imLegacy

run testApiProgram

proc testExec() =
  ## KRN-012: `exec "NAME"` from the storage card: a program file (the "C8P"
  ## header, version 1) loaded at $7000 over several chunks and run; one
  ## that fills $7000-$dfff exactly; any other file as BASIC (LOAD, RUN); a
  ## bad header version, a header cut short and one too big are refused
  ## with a message and nothing runs; a missing file; no name.
  echo "== exec from the storage card =="
  let rom = buildKernelRom()
  createDir(storeDir)
  let img = storeDir / "exec.img"
  var r = fatcheck("blank " & quoteShell(img) & " 4096")
  if r.exitCode != 0:
    fail("fatcheck blank: " & r.output)
    return
  let prg = storeDir / "exec.prg"
  mkprg(testdata / "exec_prog.s", prg)
  let file = readFile(prg)
  let body = file[4 .. ^1]
  var full = body
  while full.len < 0x7000 - 1: full.add('\0')
  full.add('\x5a')                              # the last byte, at $dfff
  proc put(name, data: string) =
    writeFile(storeDir / "put.bin", data)
    let r = fatcheck("put " & quoteShell(img) & " " & name & " " & quoteShell(storeDir / "put.bin"))
    if r.exitCode != 0: fail("fatcheck put " & name & ": " & r.output)
  put("PROG.PRG", file)
  put("FULL.PRG", "C8P\x01" & full)
  put("BIG.PRG", "C8P\x01" & full & "x")
  put("BADVER.PRG", "C8P\x02" & body)
  put("CUT.PRG", "C8P")
  put("BAS", "10 print 6*7\r\n20 print \"BASIC OK\"\r\n")
  bootStorage(rom, img)
  let sp0 = SP
  expectTrue("exec a program", cmdOutput("exec \"prog.prg\"") == @["NATIVE OK"])
  var same = true
  for i in 0 ..< body.len:
    if mem[0x7000 + i] != body[i].ord: same = false
  expectTrue("its " & $body.len & " bytes at $7000 (three chunks)", same)
  expect("the terminal's stack as before", SP, sp0, 4)
  mem[0xdfff] = 0
  expectTrue("exec one that fills $7000-$dfff", cmdOutput("exec full.prg") == @["NATIVE OK"])
  expect("its last byte at $dfff", mem[0xdfff], 0x5a)
  let bas = cmdOutput("exec \"bas\"", "DONE.")
  expectTrue("exec a BASIC program (" & $bas & ")", bas == @["42", "BASIC OK"])
  for i in 0x7000 .. 0x7010: mem[i] = 0          # anything run from here now would not print
  expectTrue("a bad header version is refused",
             cmdOutput("exec \"badver.prg\"") == @["bad program header"])
  expectTrue("a header cut short is refused", cmdOutput("exec \"cut.prg\"") == @["bad program header"])
  expectTrue("one byte too big is refused", cmdOutput("exec \"big.prg\"") == @["program too big"])
  expectTrue("a missing file", cmdOutput("exec \"nothing\"") == @["file not found"])
  expectTrue("no name", cmdOutput("exec") == @["EXEC \"NAME\""])
  expect("the terminal's stack as before, after all that", SP, sp0, 4)
  let help = cmdOutput("help")
  expectTrue("help lists exec", help.len > 0 and help[0].endsWith("EXEC"))
  bootStorage(rom, "", fitted = false)
  expectTrue("no storage card", cmdOutput("exec \"prog.prg\"") == @["no storage card"])
  ioModel = imLegacy

run testExec

if failures > 0:
  echo "FAILED ", failures, " check(s)"
  quit(1)
echo "ALL TESTS PASSED"
