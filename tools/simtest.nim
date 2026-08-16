# In-repo tests that drive the shipped CUPC/8 CPU in sim.nim
# plus the in-tree assembler (tools/as.py).

import os
import osproc
import strutils
import sim
import simdisplay

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
    doAssert cpuStep()

proc runToHalt(maxSteps = 20000): int =
  var n = 0
  while n < maxSteps:
    if not cpuStep():
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

  doAssert cpuStep()
  if PC != entry:
    fail("after boot B, pc=$# expected $#" % [toHex(PC, 4), toHex(entry, 4)])
  else:
    ok("boot B landed at main $" & toHex(PC, 4))

  doAssert cpuStep()  # mov r0, #0x42
  if R0 != 0x42:
    fail("after mov, r0=$# expected 42" % [toHex(R0, 2)])
  else:
    ok("mov r0, #0x42")

  doAssert cpuStep()  # st $2000, r0
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

  doAssert cpuStep()
  if PC != mainAddr:
    fail("pc stayed at $# after boot B (wanted main $" & toHex(mainAddr, 4) & ")" %
         [toHex(PC, 4)])
    return
  if PC == 0x1003:
    fail("pc fell through empty/NOP path")
    return
  ok("pc followed boot B into main $" & toHex(PC, 4))

  # main: push pch; push pcl; b ili9340_init
  if (mem[PC] and 0xf8) != 0x90:
    fail("main does not start with push (op=$#)" % [toHex(mem[PC], 2)])
  if (mem[PC+1] and 0xf8) != 0x90:
    fail("second main insn is not push")
  if (mem[PC+2] and 0xf8) != 0xb0:
    fail("third main insn is not B")
    return
  let initAddr = mem[PC+3] or (mem[PC+4] shl 8)
  doAssert cpuStep()
  doAssert cpuStep()
  doAssert cpuStep()
  if PC != initAddr:
    fail("after main's first calls, pc=$# expected ili9340_init $" &
         toHex(initAddr, 4) % [toHex(PC, 4)])
  else:
    ok("first kernel calls: pc now ili9340_init $" & toHex(PC, 4))

  var steps = 0
  while steps < 40 and last_gpo.len == 0:
    if not cpuStep():
      break
    inc steps
  if last_gpo.len == 0:
    fail("ili9340_init did not store GPO (mem[f000]=$#)" % [toHex(mem[0xf000], 2)])
  else:
    ok("kernel executed ili9340 reset via " & last_gpo)
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
  expect("stack[0101]", mem[0x0101], 1)
  expect("stack[0102]", mem[0x0102], 2)

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
    if not cpuStep():
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
  expect("reset mem", mem[0x1234], 0)
  expectTrue("reset last_gpo", last_gpo.len == 0)

# ---------------------------------------------------------------------------

testTinyProgram()
testAssemblerEncodings()
testAssemblerRejects()
testAluImm()
testAluReg()
testCmp()
testStack()
testCallRet()
testMem()
testIndirect()
testFlow()
testGpo()
testSpiStatus()
testMulDiv()
testZfSurvive()
testAddrSplit()
testBssData()
testDefine()
testLegacyAlu()
testLegacyStack()
testLegacyGpo()
testLegacyMem()
testLegacyMath()
testResetState()
testKernelBoot()

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
  while n < 400 and cpuStep():
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

testDisplayRect()

if failures > 0:
  echo "FAILED ", failures, " check(s)"
  quit(1)
echo "ALL TESTS PASSED"
