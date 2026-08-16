
# cupcake simulator - nim edition!

import strutils
import terminal
import sdl2

import simdisplay
import simsd

when isMainModule:
  import times
  import os
  import parseopt
  import std/exitprocs

var log_mask* = 9
var last_gpo*: string = ""
var ins_retired*: int = 0

proc log(lvl : int, msg : string) =
  if (lvl and log_mask) > 0:
    when defined(emscripten):
      echo msg
    else:
        case lvl:
            of 8:
                setStyle({styleBright})
                setForegroundColor(fgBlue, true)
            of 1:
                setStyle({styleBright})
                setForegroundColor(fgRed, true)
            of 2:
                setForegroundColor(fgGreen)
            of 4:
                setStyle({styleDim})
            else:
                discard
        writeLine(stdout, msg)
        resetAttributes()

var
  PC*: int = 0x1000
  SP*: int = 0x0100
  R0*: int = 0
  R1*: int = 0
  ZF*: bool = false
  HF*: bool = false
  pcl*: int = 0
  mem*: array[0..0x10000, int]
  imageEnd*: int = 0

type
  StepResult* = enum
    sOk, sHalted, sPastImage
  MemAccessKind* = enum
    maRead, maWrite
  MemHook* = proc(kind: MemAccessKind; address, value, oldValue: int)
  RunExit* = enum
    reCount, reBreak, reStop, reHalted, rePastImage

var
  memHook*: MemHook = nil
  stopRequest*: bool = false
  stepOutArmed*: bool = false
  stepOutSP*: int = 0
  breakSet: array[0x10000, bool]
  breakCount: int = 0
  resumeBreak: int = -1

var
  spi_tx_buf: array[0..4, int]
  spi_rx_buf: array[0..4, int]
  keybuffer: int = 0xff
  has_key: bool = false

var
  display_active: bool = false

proc pushKey*(k: int) =
  keybuffer = k and 0xff
  has_key = true

proc keyPending*(): bool = has_key

proc fetch(): int =
  result = mem[PC] and 0xff
  PC += 1

proc reg_write(operands, val: int) =
  if (operands and 1) == 1:
    R1 = val and 0xff
  else:
    R0 = val and 0xff

proc reg_read(operands: int, dst_doreg: bool): int =
  var bit = 2
  if dst_doreg:
    bit = 1
  if (operands and bit) == bit:
    result = R1 and 0xff
  else:
    result = R0 and 0xff

proc get_imm(operands: int): tuple[has_imm: bool, val: int] =
  if (operands and 4) == 4:
    var imm = fetch()
    result = (true, imm)
  else:
    result = (false, 0)

proc ins_nop(o: int) =
  discard

proc ins_eq(o: int) =
  var tup = get_imm(o)
  var imm = tup[0]
  var rb = tup[1]
  if not imm:
    rb = reg_read(o, false)
  var ra = reg_read(o, true)
  ZF = ra == rb

proc ins_or(o: int) =
  var tup = get_imm(o)
  var imm = tup[0]
  var rb = tup[1]
  if not imm:
    rb = reg_read(o, false)
  var ra = reg_read(o, true)
  reg_write(o, ra or rb)

proc ins_add(o: int) =
  var tup = get_imm(o)
  var imm = tup[0]
  var rb = tup[1]
  if not imm:
    rb = reg_read(o, false)
  var ra = reg_read(o, true)
  reg_write(o, ra + rb)

proc ins_shl(o: int) =
  var tup = get_imm(o)
  var imm = tup[0]
  var rb = tup[1]
  if not imm:
    rb = reg_read(o, false)
  var ra = reg_read(o, true)
  reg_write(o, ra shl rb)

proc ins_mov(o: int) =
  var tup = get_imm(o)
  var imm = tup[0]
  var rb = tup[1]
  if not imm:
    rb = reg_read(o, false)
  reg_write(o, rb)

proc ins_st_do(o: int, a: int) =
  var address = a
  if (o and 4) == 4:
    var ra = reg_read(o, true)
    address += ra
  let
    value = reg_read(o, false)
    oldValue = mem[address]
  mem[address] = value
  case address shr 8:
    of 0xf0:
      if (address and 0xff) == 0: #gpo
        last_gpo = "GPO: $1 $2" % [toBin(mem[address], 8), toHex(mem[address], 2)]
        log(1, last_gpo)
      display_set_dc(mem[address] and 1)
    of 0xf1:    # spi
      var dev = address shr 4 and 0xf
      if dev == 0:  # display
        if not display_active:
          display_active = true
      var reg = address and 0xf
      case reg:
        of 0:   # tx
          spi_tx_buf[dev] = value
        of 2:   # transact
          case dev:
          of 0:
            display_transact(spi_tx_buf[dev])
          of 1:
            spi_rx_buf[dev] = sd_transact(spi_tx_buf[dev])
          of 2:
            if not has_key:
              spi_rx_buf[dev] = 0xff
            else:
              spi_rx_buf[dev] = keybuffer
              has_key = false
          else:
            discard
        else:
          discard
    else:
      discard
  if not memHook.isNil:
    memHook(maWrite, address, value, oldValue)

proc ins_st(o: int) =
  var address = fetch() or (fetch() shl 8)
  ins_st_do(o, address)

proc ins_std(o: int) =
  var address = fetch() or (fetch() shl 8)
  var address_d = mem[address] or (mem[address+1] shl 8)
  ins_st_do(o, address_d)

proc ins_ld_do(o: int, a: int) =
  var address = a
  if (o and 4) == 4:
    var rb = reg_read(o, false)
    address += rb
  let oldValue = mem[address]
  var value = oldValue
  case address shr 8:
    of 0xf1:    #spi
      var dev = address shr 4 and 0xf
      var reg = address and 0xf
      case reg:
        of 1:   # rx
          value = spi_rx_buf[dev]
        of 3:   # status
          case dev:
            of 0: #display
              value = 1
            of 2: #keyboard
              if has_key:
                value = 1
              else:
                value = 0
            of 1: #sd
              value = sd_isready()
            else:
              discard
        else:
          discard
    else:
      discard
  reg_write(o, value)
  if not memHook.isNil:
    memHook(maRead, address, value, oldValue)

proc ins_ld(o: int) =
  var address = fetch() or (fetch() shl 8)
  ins_ld_do(o, address)

proc ins_ldd(o: int) =
  var address = fetch() or (fetch() shl 8)
  var address_d = mem[address] or (mem[address+1] shl 8)
  ins_ld_do(o, address_d)

proc ins_gt(o: int) =
  var tup = get_imm(o)
  var imm = tup[0]
  var rb = tup[1]
  if not imm:
    rb = reg_read(o, false)
  var ra = reg_read(o, true)
  ZF = ra > rb

proc ins_lt(o: int) =
  var tup = get_imm(o)
  var imm = tup[0]
  var rb = tup[1]
  if not imm:
    rb = reg_read(o, false)
  var ra = reg_read(o, true)
  ZF = ra < rb

proc ins_sub(o: int) =
  var tup = get_imm(o)
  var imm = tup[0]
  var rb = tup[1]
  if not imm:
    rb = reg_read(o, false)
  var ra = reg_read(o, true)
  reg_write(o, ra - rb)

proc ins_shr(o: int) =
  var tup = get_imm(o)
  var imm = tup[0]
  var rb = tup[1]
  if not imm:
    rb = reg_read(o, false)
  var ra = reg_read(o, true)
  reg_write(o, ra shr rb)

proc ins_and(o: int) =
  var tup = get_imm(o)
  var imm = tup[0]
  var rb = tup[1]
  if not imm:
    rb = reg_read(o, false)
  var ra = reg_read(o, true)
  reg_write(o, ra and rb)

proc ins_xor(o: int) =
  var tup = get_imm(o)
  var imm = tup[0]
  var rb = tup[1]
  if not imm:
    rb = reg_read(o, false)
  var ra = reg_read(o, true)
  reg_write(o, ra xor rb)

proc ins_nor(o: int) =
  var tup = get_imm(o)
  var imm = tup[0]
  var rb = tup[1]
  if not imm:
    rb = reg_read(o, false)
  var ra = reg_read(o, true)
  reg_write(o, not (ra or rb))

proc ins_push(o: int) =
  var rb = 0
  if (o and 7) == 7:
    rb = (PC + 3) and 0xff
  elif (o and 6) == 6:
    rb = (PC + 4) shr 8
  else:
    var tup = get_imm(o)
    var imm = tup[0]
    rb = tup[1]
    if not imm:
      rb = reg_read(o, false)

  SP += 1
  mem[SP] = rb

proc ins_pop(o: int) =
  if (o and 7) == 7:
    pcl = mem[SP]
  elif (o and 6) == 6:
    PC = pcl or (mem[SP] shl 8)
    if stepOutArmed and SP <= stepOutSP:
      stepOutArmed = false
      stopRequest = true
  else:
    reg_write(o, mem[SP])

  SP -= 1

proc ins_b(o: int) =
  PC = fetch() or (fetch() shl 8)

proc ins_bzf(o: int) =
  var tmp = fetch() or (fetch() shl 8)
  if ZF:
    PC = tmp

proc ins_halt(o: int) =
  HF = true

proc ins_tmr0(o: int) =
  var tup = get_imm(o)
  var imm = tup[0]
  var rb = tup[1]
  if not imm:
    rb = reg_read(o, false)
  var ra = reg_read(o, true)
  discard ra
  discard rb

proc ins_tmr1(o: int) =
  var tup = get_imm(o)
  var imm = tup[0]
  var rb = tup[1]
  if not imm:
    rb = reg_read(o, false)
  var ra = reg_read(o, true)
  discard ra
  discard rb

proc decode() =
  var op = fetch()
  var ins = op and 0xf8
  var r = op and 7
  case ins:
    of 0x80: ins_nop(r)
    of 0x88: ins_mov(r)
    of 0x90: ins_push(r)
    of 0x98: ins_pop(r)
    of 0xa0: ins_ld(r)
    of 0xa8: ins_st(r)
    of 0x70: ins_ldd(r)
    of 0x78: ins_std(r)
    of 0xb0: ins_b(r)
    of 0xb8: ins_bzf(r)
    of 0x00: ins_eq(r)
    of 0x08: ins_gt(r)
    of 0x10: ins_lt(r)
    of 0x18: ins_and(r)
    of 0x20: ins_or(r)
    of 0x30: ins_xor(r)
    of 0x38: ins_nor(r)
    of 0x40: ins_add(r)
    of 0x48: ins_sub(r)
    of 0x60: ins_shl(r)
    of 0x68: ins_shr(r)
    of 0xe0: ins_tmr0(r)
    of 0xe8: ins_tmr1(r)
    of 0xf8: ins_halt(r)
    else:
      discard

proc cpuReset*() =
  PC = 0x1000
  SP = 0x0100
  R0 = 0
  R1 = 0
  ZF = false
  HF = false
  pcl = 0
  imageEnd = 0
  ins_retired = 0
  last_gpo = ""
  display_active = false
  has_key = false
  keybuffer = 0xff
  stopRequest = false
  stepOutArmed = false
  stepOutSP = 0
  resumeBreak = -1
  for i in 0..mem.high:
    mem[i] = 0
  for i in 0..spi_tx_buf.high:
    spi_tx_buf[i] = 0
    spi_rx_buf[i] = 0
  display_reset()

proc cpuLoadImage*(code: string) =
  var i = 0
  while i < code.len:
    mem[0x1000+i] = int(code[i])
    i += 1
  imageEnd = 0x1000 + i

proc cpuLoadFile*(path: string) =
  cpuLoadImage(readFile(path))

proc cpuStep*(): StepResult =
  ## Fetch/decode/execute one instruction and report why execution stopped.
  # A direct step consumes the resume allowance from a prior breakpoint hit.
  resumeBreak = -1
  if HF:
    return sHalted
  if PC >= imageEnd:
    return sPastImage
  decode()
  ins_retired += 1
  if HF: sHalted else: sOk

proc setBreak*(a: int) =
  let address = a and 0xffff
  if not breakSet[address]:
    breakSet[address] = true
    inc breakCount

proc clearBreak*(a: int) =
  let address = a and 0xffff
  if breakSet[address]:
    breakSet[address] = false
    dec breakCount
  if resumeBreak == address:
    resumeBreak = -1

proc hasBreak*(a: int): bool = breakSet[a and 0xffff]

proc clearAllBreaks*() =
  resumeBreak = -1
  if breakCount == 0:
    return
  for i in 0..breakSet.high:
    breakSet[i] = false
  breakCount = 0

proc cpuRun*(maxSteps: int): RunExit =
  ## Run a batch. Breakpoints stop before the marked instruction. After a hit,
  ## the next run skips that same breakpoint once so execution can resume.
  for i in 0..<maxSteps:
    if HF:
      return reHalted
    if PC >= imageEnd:
      return rePastImage
    let address = PC and 0xffff
    if breakCount > 0 and breakSet[address] and address != resumeBreak:
      resumeBreak = address
      return reBreak
    resumeBreak = -1
    decode()
    inc ins_retired
    if HF:
      return reHalted
    if stopRequest:
      stopRequest = false
      return reStop
  reCount

proc cpuStatusLine*(): string =
  "retired=$1 pc=$2 r0=$3 r1=$4 sp=$5 hf=$6" % [
    $ins_retired, toHex(PC, 4), toHex(R0, 2), toHex(R1, 2), toHex(SP, 4), $HF]

when defined(emscripten):
  proc emscripten_set_main_loop(fun: proc() {.cdecl.}, fps,
                                simulate_infinite_loop: cint) {.header: "<emscripten.h>".}

  proc emscripten_cancel_main_loop() {.header: "<emscripten.h>".}

  proc emscripten_set_main_loop_timing(mode: cint, value: cint) {.header: "<emscripten.h>".}

when isMainModule:
  addExitProc(resetAttributes)

  var binPath = ""
  var maxIns = 0
  var headless = false
  var doTrace = false
  var wantDisplay = true
  var dumpFb = ""

  var p = initOptParser()
  for kind, key, val in p.getopt():
    case kind
    of cmdArgument:
      binPath = key
    of cmdLongOption, cmdShortOption:
      case key
      of "max-ins", "n":
        maxIns = parseInt(val)
      of "headless":
        headless = true
        wantDisplay = false
      of "trace":
        doTrace = true
      of "log-mask":
        log_mask = parseInt(val)
      of "scale":
        display_setScale(parseInt(val))
      of "dump-fb":
        dumpFb = val
      of "help", "h":
        echo "usage: sim [--headless] [--max-ins:N] [--scale:N] [--dump-fb:path] [--trace] <kernel.o>"
        quit(0)
      else:
        echo "unknown option: ", key
        quit(1)
    of cmdEnd:
      discard

  if binPath.len == 0:
    if paramCount() > 0:
      binPath = paramStr(1)
    else:
      cpuLoadImage(readAll(stdin))
  else:
    cpuLoadFile(binPath)

  if wantDisplay:
    if not display_init():
      stderr.writeLine("display init failed: " & display_init_error)
      quit(2)

  discard sd_try_init()

  var atend = false
  var evt = defaultEvent

  proc pumpInput() =
    while pollEvent(evt):
      case evt.kind:
        of QuitEvent:
          atend = true
          break
        of TextInput:
          let t = evt.text()
          if t.text[0] != '\0':
            pushKey(ord(t.text[0]))
        of KeyDown:
          let e = evt.key()
          if e.repeat:
            continue
          case e.keysym.sym:
            of K_RETURN, K_KP_ENTER:
              pushKey(13)
            of K_BACKSPACE:
              pushKey(8)
            else:
              discard
        else:
          discard

  proc exec() {.cdecl.} =
    if PC >= imageEnd or HF:
      echo "HALT!"
      when defined(emscripten):
        emscripten_cancel_main_loop()
      atend = true
      return

    if doTrace:
      echo "TRACE pc=$1 op=$2" % [toHex(PC, 4), toHex(mem[PC], 2)]

    when defined(emscripten):
      for i in 0..10000:
        if cpuStep() != sOk:
          atend = true
          break
    else:
      if cpuStep() != sOk:
        atend = true
        return

  when defined(emscripten):
    emscripten_set_main_loop(exec, 0, 0)
  else:
    var start = cpuTime()
    var lastPresent = start
    var lastMhz = start
    var lastMhzIns = 0
    if wantDisplay:
      display_render()
    while not atend:
      exec()
      if maxIns > 0 and ins_retired >= maxIns:
        echo cpuStatusLine()
        if last_gpo.len > 0:
          echo last_gpo
        break
      if not headless:
        if (ins_retired and 0x1ff) == 0:
          pumpInput()
          let now = cpuTime()
          if now - lastPresent >= 0.016:
            display_render()
            lastPresent = now
          if now - lastMhz >= 1.0:
            let dt = now - lastMhz
            log(8, "$1 MHz" % formatFloat(float(ins_retired - lastMhzIns) / dt / 1_000_000, ffDecimal, 2))
            lastMhz = now
            lastMhzIns = ins_retired
    if dumpFb.len > 0:
      display_dumpPpm(dumpFb)
      echo "wrote framebuffer ", dumpFb
    if maxIns == 0:
      echo cpuStatusLine()
      while not atend:
        pumpInput()
        display_render()
        sleep(16)
