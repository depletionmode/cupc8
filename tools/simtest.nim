# In-repo tests that drive the shipped CUPC/8 CPU in sim.nim
# plus the in-tree assembler (tools/as.py).

import os
import osproc
import net
import selectors
import nativesockets
import strutils
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
  expectTrue("previous instruction anchor",
             table.prevInsAddr(termAddress + 2, 1) == termAddress)

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
  expect("slot and SPI IRQs unmasked", irqMask, 9)

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

proc testKernelNetwork() =
  ## KRN-004: the kernel's "net" command joins through the Wi-Fi card,
  ## connects to a server running in this process and prints the reply.
  echo "== kernel networking =="
  let rom = buildKernelRom()
  machineCards([CardGpu, CardIo, CardWifi])
  cpuReset()
  cpuLoadRom(rom)
  cpuBootRom()
  let g = gpuCard()

  # a server on port 8088, which the kernel's net command connects to
  var server = newSocket()
  server.setSockOpt(OptReuseAddr, true)
  try:
    server.bindAddr(Port(8088), "127.0.0.1")
  except OSError:
    fail("port 8088 is busy; skipping the network test")
    ioModel = imLegacy
    return
  server.listen()

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

  # serve the request while the machine keeps running (never block: the CPU
  # only advances in this loop)
  var client: Socket
  var accepted = false
  var served = false
  n = 0
  while n < 8_000_000:
    if cpuStep() != sOk: break
    inc n
    if (n mod 1000) == 0:
      # scanning the screen is costly, so only between socket polls
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
        var buf = newString(64)
        let got = client.getFd.recv(addr buf[0], 64, 0)
        if got > 0:
          client.send("CUPC8-OK\r\n")
          served = true
  expectTrue("server saw the request", served)
  if gpuFind(g, "CUPC8-OK") < 0:
    echo "screen:"
    for row in 0..12:
      let line = gpuLine(g, row)
      if line.len > 0: echo "  |" & line
  expectTrue("reply printed on screen", gpuFind(g, "CUPC8-OK") >= 0)
  if served: client.close()
  server.close()
  ioModel = imLegacy

run testKernelNetwork

if failures > 0:
  echo "FAILED ", failures, " check(s)"
  quit(1)
echo "ALL TESTS PASSED"
