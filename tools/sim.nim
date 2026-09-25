
# cupcake simulator - nim edition!

import strutils
import terminal
import sdl2

import simdisplay
import simsd
import simcards

when isMainModule:
  import times
  import os
  import parseopt
  import std/exitprocs
  import sequtils
  import posix
  import termios
  import simmachine

var log_mask* = 9
var last_gpo*: string = ""
var ins_retired*: int = 0

var statusShown = false  ## the speed line is on screen, without its newline

proc log(lvl : int, msg : string) =
  if (lvl and log_mask) > 0:
    when defined(emscripten):
      echo msg
    else:
        if statusShown:
          stdout.write("\r\e[K")   # the next line takes the speed line's place
          statusShown = false
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

proc speedLine(ips: float): string =
  ## instructions per second, and the CPU clock that is: the sim counts one
  ## instruction per microsecond, ~12 clocks of the real 12 MHz CPU
  "$1 MIPS, as a $2 MHz CUPC/8 (the real one: 12 MHz, ~1 MIPS)" %
    [formatFloat(ips / 1_000_000, ffDecimal, 2), formatFloat(ips * 12 / 1_000_000, ffDecimal, 1)]

proc status(msg: string) =
  ## the speed line: rewritten in place, not one line per second
  if (8 and log_mask) > 0:
    when defined(emscripten):
      echo msg
    else:
      setStyle({styleBright})
      setForegroundColor(fgBlue, true)
      stdout.write("\r\e[K" & msg)
      resetAttributes()
      flushFile(stdout)
      statusShown = true

when isMainModule and not defined(emscripten):
  addExitProc(proc () =
    if statusShown: stdout.write("\n"))   # leave the last speed line for the shell

var
  PC*: int = 0x1000
  SP*: int = 0x0100
  R0*: int = 0
  R1*: int = 0
  ZF*: bool = false
  HF*: bool = false
  IF*: bool = false
  waiting*: bool = false
  pcl*: int = 0
  lastOp: int = 0                # the opcode of the instruction that retired last
  mem*: array[0..0x10000, int]
  imageEnd*: int = 0
  irqPending*: int = 0
  irqMask*: int = 0
  tmr0*: int = 0
  tmr1*: int = 0

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

# ---------------------------------------------------------------------------
# I/O model. imLegacy: the original devices (ILI9340 on SPI 0, SD on 1,
# keyboard on 2, D/C on GPO bit 0). imCards: the Milestone 1 machine
# (doc/hardware/memory-map.md): the ROM chip with its windows, SYSCTL,
# ROM_BANK, SLOT_IRQ, per-device SPI registers with SPI_CS, and slot cards
# running the real firmware cores (tools/simcards.nim).
type IoModel* = enum imLegacy, imCards

var
  ioModel*: IoModel = imLegacy
  slots*: array[6, SimCard]      # slot n = SPI device n; nil = empty
  rom*: seq[uint8]               # the ROM chip (512 KB)
  romOff*: bool = false
  pwrHi*: bool = true            # USB-C source >= 3.0 A (a board input, kept across reset)
  romBank*: int = 0
  ramBank*: int = 2              # RAM_BANK ($f205): the $8000-$bfff window's SRAM bank
  xram*: seq[int]                # SRAM $0f000-$7ffff; mem[] holds $00000-$0efff (its
                                 # $f000-$ffff are the I/O registers' shadows)
  ramJunk*: bool = false         # cpuReset leaves RAM as the SRAM powers up (the
                                 # emulator's pattern, soc/emu/board.h), not zeroed
  spiTxR, spiRxR, spiCfgR: array[8, int]
  spiHold*: int = -1             # device selected by SPI_CS, -1 = none
  slotIrqPrev: int = 0
  lastCardTick: int = 0

proc simMillis*(): uint32 =
  ## Guest time: about one instruction per microsecond at 12 MHz.
  uint32(ins_retired div 1000)

var heldSlotIrq*: int = 0       ## test hook: slots whose IRQ_n is held low (another card's)

proc slotIrqBits*(): int =
  result = heldSlotIrq and 0x3f
  for i in 0..5:
    if not slots[i].isNil and simcard_irq(slots[i]) != 0:
      result = result or (1 shl i)

proc machineCards*(cards: openArray[int]) =
  ## Cards mode with the given card types in slots 1.. (0 = empty).
  ioModel = imCards
  for i in 0..5:
    if not slots[i].isNil:
      simcard_free(slots[i])
      slots[i] = SimCard(nil)
    if i < cards.len and cards[i] != 0:
      slots[i] = simcard_new(cint(cards[i]))
  if rom.len == 0:
    rom = newSeq[uint8](512 * 1024)
    for i in 0..rom.high: rom[i] = 0xff

proc cpuLoadRom*(path: string) =
  let data = readFile(path)
  rom = newSeq[uint8](512 * 1024)
  for i in 0..rom.high:
    rom[i] = if i < data.len: uint8(data[i]) else: 0xff'u8

proc raiseIrq*(bit: int) =
  irqPending = (irqPending or (1 shl bit)) and 0x0f
  mem[0xf200] = irqPending

proc cardsTick*() =
  ## Let the cards do background work, and latch IRQ0 on a new slot IRQ.
  let now = simMillis()
  for c in slots:
    if not c.isNil:
      simcard_tick(c, now)
  # a new assertion on any slot line latches IRQ0, even while another card
  # is still holding its own line low
  let bits = slotIrqBits()
  if (bits and not slotIrqPrev) != 0:
    raiseIrq(0)
  slotIrqPrev = bits
  lastCardTick = ins_retired

proc ioCard(): SimCard =
  for c in slots:
    if not c.isNil and simcard_type(c) == CardIo:
      return c
  SimCard(nil)

proc gpuCard*(): SimCard =
  for c in slots:
    if not c.isNil and simcard_type(c) == CardGpu:
      return c
  SimCard(nil)

var gpuFrame: seq[uint32] = @[]

proc gpuPresent*() =
  ## Render the GPU card's picture into the simulator display.
  let c = gpuCard()
  if c.isNil:
    return
  if gpuFrame.len == 0:
    gpuFrame = newSeq[uint32](GpuOutW * GpuOutH)
  display_setSize(GpuOutW, GpuOutH)
  simcard_render(c, addr gpuFrame[0])
  display_blit(addr gpuFrame[0])

proc pushKey*(k: int) =
  if ioModel == imCards:
    let c = ioCard()
    if not c.isNil:
      simcard_type_ascii(c, uint8(k and 0xff), simMillis())
      cardsTick()
    return
  keybuffer = k and 0xff
  has_key = true
  raiseIrq(0)

proc keyPending*(): bool = has_key

proc romWindow(a: int): int =
  ## ROM chip offset for CPU address a, or -1 if a is not in a ROM window.
  if ioModel != imCards or romOff or a < 0xe000 or a > 0xefff:
    return -1
  if a < 0xe800: a and 0x7ff
  else: (romBank shl 11) or (a and 0x7ff)

proc physRead*(p: int): int =
  ## The 512 KB SRAM by physical address (extended-ram.md).
  if p < 0xf000: mem[p] and 0xff
  else: xram[p - 0xf000] and 0xff

proc physWrite*(p, v: int) =
  if p < 0xf000: mem[p] = v and 0xff
  else: xram[p - 0xf000] = v and 0xff

proc ramRead(a: int): int =
  ## RAM at CPU address a: the window at $8000-$bfff shows bank RAM_BANK
  ## (M1 machine only; bank 2 is the identity map).
  if ioModel == imCards and ramBank != 2 and (a and 0xc000) == 0x8000:
    physRead((ramBank shl 14) or (a and 0x3fff))
  else:
    mem[a]

proc ramWrite(a, v: int) =
  if ioModel == imCards and ramBank != 2 and (a and 0xc000) == 0x8000:
    physWrite((ramBank shl 14) or (a and 0x3fff), v)
  else:
    mem[a] = v

proc memRead(a: int): int =
  let a = a and 0xffff
  let r = romWindow(a)
  if r >= 0:
    return int(rom[r mod rom.len])
  ramRead(a) and 0xff

proc fetch(): int =
  result = memRead(PC)
  PC = (PC + 1) and 0xffff

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
  # shifts of 8 or more give 0 (a native shift by >= 64 is undefined in C)
  reg_write(o, if rb > 7: 0 else: ra shl rb)

proc ins_mov(o: int) =
  var tup = get_imm(o)
  var imm = tup[0]
  var rb = tup[1]
  if not imm:
    rb = reg_read(o, false)
  reg_write(o, rb)

proc spiSelect(dev: int, on: bool) =
  if dev >= 0 and dev < 6 and not slots[dev].isNil:
    simcard_select(slots[dev], cint(on))

proc spiExchange(dev: int, tx: int): int =
  ## One byte on device dev (CS already low). Empty slots read the pull-up.
  if dev >= 0 and dev < 6 and not slots[dev].isNil:
    result = int(simcard_miso(slots[dev]))
    simcard_mosi(slots[dev], uint8(tx and 0xff))
  else:
    result = 0xff

proc cardsStore(address, value: int) =
  let v = value and 0xff
  if address >= 0xe000 and address <= 0xefff and not romOff:
    return                                   # CPU writes to the ROM windows are ignored
  if address < 0xf000:
    ramWrite(address, v)
    return
  case (address shr 8) and 0xf
  of 0x0:
    if (address and 0xff) == 0:
      mem[0xf000] = v
      last_gpo = "GPO: $1 $2" % [toBin(v, 8), toHex(v, 2)]
      log(1, last_gpo)
  of 0x1:
    let dev = (address shr 4) and 0xf
    if dev < 8:
      case address and 0xf
      of 0x0: spiTxR[dev] = v
      of 0x2:
        let held = spiHold == dev
        if not held: spiSelect(dev, true)
        spiRxR[dev] = spiExchange(dev, spiTxR[dev])
        if not held: spiSelect(dev, false)
        raiseIrq(3)
      of 0x4:
        if (v and 1) == 1:
          if spiHold != dev:
            spiSelect(spiHold, false)
            spiHold = dev
            spiSelect(dev, true)
        elif spiHold == dev:
          spiSelect(dev, false)
          spiHold = -1
      of 0xf: spiCfgR[dev] = v
      else: discard
      cardsTick()
  of 0x2:
    case address and 0xff
    of 0: irqPending = irqPending and not v and 0x0f
    of 1: irqMask = v and 0x0f
    of 3: romOff = (v and 1) == 1
    of 4: romBank = v
    of 5: ramBank = v and 0x1f
    else: discard
  else:
    discard

proc cardsLoad(address: int): int =
  if address < 0xf000:
    return memRead(address)
  case (address shr 8) and 0xf
  of 0x0:
    if (address and 0xff) == 0: mem[0xf000] and 0xff else: 0
  of 0x1:
    let dev = (address shr 4) and 0xf
    if dev >= 8: return 0
    case address and 0xf
    of 0x1: spiRxR[dev]
    of 0x3: 1
    of 0x4: (if spiHold == dev: 1 else: 0)
    else: 0
  of 0x2:
    case address and 0xff
    of 0: irqPending
    of 1: irqMask
    of 2: slotIrqBits()
    of 3: (if romOff: 1 else: 0) or (if pwrHi: 2 else: 0)
    of 4: romBank
    of 5: ramBank
    else: 0
  else: 0

proc cardsLoadTest*(address: int): int = cardsLoad(address)
proc cardsStoreTest*(address, value: int) = cardsStore(address, value)

proc ins_st_do(o: int, a: int) =
  var address = a
  if (o and 4) == 4:
    var ra = reg_read(o, true)
    address += ra
  address = address and 0xffff
  let
    value = reg_read(o, false)
    oldValue = mem[address]
  if ioModel == imCards:
    cardsStore(address, value)
    if not memHook.isNil:
      memHook(maWrite, address, value, oldValue)
    return
  mem[address] = value
  case address shr 8:
    of 0xf0:
      if (address and 0xff) == 0: #gpo
        last_gpo = "GPO: $1 $2" % [toBin(mem[address], 8), toHex(mem[address], 2)]
        log(1, last_gpo)
      display_set_dc(mem[address] and 1)
    of 0xf2:    # irq
      case address and 0xff:
        of 0:
          irqPending = irqPending and not value
          mem[address] = irqPending
        of 1:
          irqMask = value and 0x0f      # 4 IRQs; bits 7:4 read 0 (memory-map.md)
          mem[address] = irqMask
        else:
          discard
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
          if dev != 2:
            raiseIrq(3)
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
  var address_d = memRead(address) or (memRead(address + 1) shl 8)
  ins_st_do(o, address_d)

proc ins_ld_do(o: int, a: int) =
  var address = a
  if (o and 4) == 4:
    var rb = reg_read(o, false)
    address += rb
  address = address and 0xffff
  if ioModel == imCards:
    let value = cardsLoad(address)
    reg_write(o, value)
    if not memHook.isNil:
      memHook(maRead, address, value, mem[address])
    return
  let oldValue = mem[address]
  var value = oldValue
  case address shr 8:
    of 0xf2:    # irq
      case address and 0xff:
        of 0:
          value = irqPending
        of 1:
          value = irqMask
        else:
          discard
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
  var address_d = memRead(address) or (memRead(address + 1) shl 8)
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
  # shifts of 8 or more give 0 (a native shift by >= 64 is undefined in C)
  reg_write(o, if rb > 7: 0 else: ra shr rb)

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

  # Manual 3.1/3.2: SP points to the next free byte ([SP] <= Rb; SP <= SP + 1),
  # matching cpu.vhd.
  let oldValue = ramRead(SP)
  ramWrite(SP, rb and 0xff)
  if not memHook.isNil:
    memHook(maWrite, SP, rb and 0xff, oldValue)
  SP += 1

proc flagsNibble(): int =
  (if ZF: 1 else: 0) or (if IF: 2 else: 0)

proc setFlags(n: int) =
  ZF = (n and 1) != 0
  IF = (n and 2) != 0

proc ins_pop(o: int) =
  SP -= 1
  if (o and 7) == 7:
    pcl = ramRead(SP)
  elif (o and 6) == 6:
    PC = pcl or (ramRead(SP) shl 8)
    if stepOutArmed and SP <= stepOutSP:
      stepOutArmed = false
      stopRequest = true
  elif (o and 7) == 4:
    setFlags(ramRead(SP))
  else:
    reg_write(o, ramRead(SP))

proc ins_b(o: int) =
  PC = fetch() or (fetch() shl 8)

proc ins_bzf(o: int) =
  var tmp = fetch() or (fetch() shl 8)
  if ZF:
    PC = tmp

proc ins_halt(o: int) =
  HF = true
  waiting = false

proc timerOperand(o: int): int =
  var tup = get_imm(o)
  if tup[0]:
    tup[1]
  else:
    reg_read(o, false)

proc ins_tmr0(o: int) =
  tmr0 = timerOperand(o) and 0xff

proc ins_tmr1(o: int) =
  tmr1 = timerOperand(o) and 0xff

proc ins_cli(o: int) =
  IF = false

proc ins_sti(o: int) =
  IF = true

proc ins_wai(o: int) =
  if IF:
    waiting = true

proc pushByte(v: int) =
  let
    value = v and 0xff
    oldValue = ramRead(SP)
  ramWrite(SP, value)
  if not memHook.isNil:
    memHook(maWrite, SP, value, oldValue)
  SP += 1

proc irqReady(): int =
  let bits = irqPending and irqMask
  if bits == 0:
    return -1
  for i in 0..3:
    if (bits and (1 shl i)) != 0:
      return i
  -1

proc takeIrq(n: int) =
  waiting = false
  let ret = PC and 0xffff
  pushByte(ret shr 8)
  pushByte(ret and 0xff)
  pushByte(flagsNibble())
  IF = false
  let va = 0x0010 + n * 2
  PC = (mem[va] and 0xff) or ((mem[va + 1] and 0xff) shl 8)

proc tickTimers() =
  if tmr0 > 0:
    dec tmr0
    if tmr0 == 0:
      raiseIrq(1)
  if tmr1 > 0:
    dec tmr1
    if tmr1 == 0:
      raiseIrq(2)

proc serviceIrq() =
  if not IF:
    return
  # POP pcl and the POP pch after it are one return: an IRQ taken between
  # them would push over the popped byte and its handler's own POP pcl would
  # replace the pcl register, so the return would go astray (cpu.vhd)
  if lastOp == 0x9f:
    return
  let n = irqReady()
  if n >= 0:
    takeIrq(n)

proc decode() =
  var op = fetch()
  lastOp = op
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
    of 0xc0: ins_cli(r)
    of 0xc8: ins_sti(r)
    of 0xf0: ins_wai(r)
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
  IF = false
  waiting = false
  pcl = 0
  lastOp = 0
  imageEnd = 0
  ins_retired = 0
  last_gpo = ""
  display_active = false
  has_key = false
  keybuffer = 0xff
  irqPending = 0
  irqMask = 0
  tmr0 = 0
  tmr1 = 0
  stopRequest = false
  stepOutArmed = false
  stepOutSP = 0
  resumeBreak = -1
  for i in 0..mem.high:
    mem[i] = if ramJunk and i < 0xf000: (i * 13 + 5) and 0xff else: 0
  for i in 0..spi_tx_buf.high:
    spi_tx_buf[i] = 0
    spi_rx_buf[i] = 0
  display_reset()
  # cards-mode chipset state (the cards themselves keep their own state)
  spiSelect(spiHold, false)
  spiHold = -1
  for i in 0..7:
    spiTxR[i] = 0
    spiRxR[i] = 0
    spiCfgR[i] = 0
  romOff = false
  romBank = 0
  ramBank = 2
  if xram.len == 0:
    xram = newSeq[int](0x80000 - 0xf000)
  for i in 0..xram.high:
    xram[i] = if ramJunk: ((i + 0xf000) * 13 + 5) and 0xff else: 0
  slotIrqPrev = 0
  lastCardTick = 0

proc cpuLoadImage*(code: string) =
  ## Fast start: the image at $1000 and PC = $1000 (no boot ROM). In cards
  ## mode the slot table the boot ROM would have left at $0002-$0007 is
  ## filled in, and the ROM is switched off as the kernel would.
  var i = 0
  while i < code.len:
    mem[0x1000+i] = int(code[i])
    i += 1
  imageEnd = 0x1000 + i
  if ioModel == imCards:
    for s in 0..5:
      mem[0x0002 + s] = if slots[s].isNil: 0 else: int(simcard_type(slots[s]))

proc cpuBootRom*() =
  ## Hardware reset in cards mode: execute the boot ROM from $e000.
  PC = 0xe000
  imageEnd = 0x10000

proc cpuLoadFile*(path: string) =
  cpuLoadImage(readFile(path))

const
  ProgramBase* = 0x7000          ## user programs (memory-map.md)
  ProgramEnd* = 0xe000
  ApiRun* = 0x6f21               ## the API block's API_RUN mailbox (kernel/api.s)

proc runProgram*(data: string): bool =
  ## What `cupc8.py run` does through the system card: the program's body at
  ## $7000, then API_RUN = 1; the kernel's terminal starts it while it waits
  ## for a key. A file with the "C8P" header must be version 1; a file
  ## without one is the body itself. False (nothing written) otherwise.
  var body = data
  if body.len >= 3 and body[0 .. 2] == "C8P":
    if body.len < 4 or body[3] != '\x01':
      return false
    body = body[4 .. ^1]
  if body.len > ProgramEnd - ProgramBase:
    return false
  for i, c in body:
    mem[ProgramBase + i] = ord(c)
  mem[ApiRun] = 1
  true

proc cpuStep*(): StepResult =
  ## Fetch/decode/execute one instruction and report why execution stopped.
  # A direct step consumes the resume allowance from a prior breakpoint hit.
  resumeBreak = -1
  if HF:
    return sHalted
  if ioModel == imCards and ins_retired - lastCardTick >= 64:
    cardsTick()
  if waiting:
    # parked in WAI the CPU loops tick, settle, check: 3 clocks per timer
    # count (cpu.vhd), so 4 counts in each microsecond step of the sim's clock
    for k in 0..3:
      tickTimers()
      serviceIrq()
      if not waiting: break
    inc ins_retired
    return sOk
  if PC >= imageEnd:
    return sPastImage
  decode()
  ins_retired += 1
  tickTimers()
  if HF:
    return sHalted
  serviceIrq()
  sOk

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
  ## A parked WAI ticks the timers once and returns so the host can sleep.
  if waiting:
    if ioModel == imCards:
      cardsTick()
    tickTimers()
    serviceIrq()
    if waiting:
      return reCount
  for i in 0..<maxSteps:
    if ioModel == imCards and ins_retired - lastCardTick >= 64:
      cardsTick()
    if HF:
      return reHalted
    if waiting:
      return reCount
    elif PC >= imageEnd:
      return rePastImage
    else:
      let address = PC and 0xffff
      if breakCount > 0 and breakSet[address] and address != resumeBreak:
        resumeBreak = address
        return reBreak
      resumeBreak = -1
      decode()
      inc ins_retired
      tickTimers()
      if HF:
        return reHalted
      serviceIrq()
    if stopRequest:
      stopRequest = false
      return reStop
  reCount

proc cpuStatusLine*(): string =
  "retired=$1 pc=$2 r0=$3 r1=$4 sp=$5 hf=$6 if=$7" % [
    $ins_retired, toHex(PC, 4), toHex(R0, 2), toHex(R1, 2), toHex(SP, 4), $HF, $IF]

when defined(emscripten):
  proc emscripten_set_main_loop(fun: proc() {.cdecl.}, fps,
                                simulate_infinite_loop: cint) {.header: "<emscripten.h>".}

  proc emscripten_cancel_main_loop() {.header: "<emscripten.h>".}

  proc emscripten_set_main_loop_timing(mode: cint, value: cint) {.header: "<emscripten.h>".}

when isMainModule:
  var consoleOn = false          # --console: the USB console's rings on this terminal
  addExitProc(proc () =
    if not consoleOn: resetAttributes())   # no escape codes in the console's stream

  var binPath = ""
  var maxIns = 0
  var headless = false
  var doTrace = false
  var wantDisplay = true
  var dumpFb = ""
  # the Milestone 1 machine (the default; --legacy for the old I/O model)
  var legacy = defined(emscripten)
  var cardList = "hdmi,io"
  var sdPath = ""
  var romPath = ""
  var typed = ""                 # --type: the keys to type
  var dumpText = ""
  var settleMs = 2000
  var scaleSet = false

  const usage = """usage: sim [options] [kernel.o]

The Milestone 1 machine (the default): reset runs the boot ROM, which loads
the kernel from the ROM chip; the slot cards run the real card firmware cores.
  --cards:LIST      slot cards, slots 1.. in order (default hdmi,io); kinds:
                    """ & CardKindNames & """

  --sd:IMAGE        the storage card's SD card: a FAT image (a blank 32 MB one
                    is made if the file does not exist)
  --rom:FILE        boot this ROM image (default: built from rom/boot.s and
                    kernel.o, or from kernel/ when no kernel.o is given)
  --type:TEXT       type TEXT on the keyboard (\n = Enter), one key each time
                    the CPU parks in WAI (the kernel's keyboard wait); repeatable
  --dump-text:PATH  at exit, write the console's text (- = stdout)
  --settle:MS       headless: guest ms to run on once the typed text is used up
                    and the machine is idle again (default 2000); then exit
  --console         the USB console (doc/proposals/usb-console.md) on this
                    terminal, as the system card carries it to a PC: the
                    kernel's terminal output on stdout (\n as CR LF), stdin
                    (raw, if a terminal; Ctrl-] quits) typed into the machine,
                    HOST set while it runs. The sim's own messages go to
                    stderr. Headless with stdin a pipe: it exits --settle ms
                    after stdin's end and the last console traffic
The Wi-Fi card uses the host's own sockets: any SSID joins, and the machine
reaches the real network and localhost directly.
  --legacy          the old I/O model (ILI9340 display, SD on SPI 1, keyboard on
                    SPI 2); kernel.o (or stdin) is loaded at $1000 and run
Both:
  --headless  --max-ins:N  --scale:N  --dump-fb:PATH (a PPM)  --trace  --log-mask:N"""

  proc unescapeTyped(t: string): string =
    ## --type text: \n and \r are Enter, \t Tab, \e Escape, \\ a backslash.
    var i = 0
    while i < t.len:
      if t[i] == '\\' and i + 1 < t.len:
        inc i
        case t[i]
        of 'n', 'r': result.add('\r')
        of 't': result.add('\t')
        of 'e': result.add('\x1b')
        else: result.add(t[i])
      else:
        result.add(if t[i] == '\n': '\r' else: t[i])
      inc i

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
        scaleSet = true
      of "dump-fb":
        dumpFb = val
      of "legacy":
        legacy = true
      of "cards":
        cardList = val
      of "sd":
        sdPath = val
      of "rom":
        romPath = val
      of "type":
        typed.add(unescapeTyped(val))
      of "dump-text":
        dumpText = val
      of "settle":
        settleMs = parseInt(val)
      of "console":
        consoleOn = true
        log_mask = 0                 # no GPO lines or speed line in the console's stream
      of "help", "h":
        echo usage
        quit(0)
      else:
        echo "unknown option: ", key
        quit(1)
    of cmdEnd:
      discard

  proc die(msg: string) =
    stderr.writeLine("sim: " & msg)
    quit(1)

  proc note(msg: string) =
    ## the sim's own messages: stdout, or stderr while stdout is the console
    if consoleOn: stderr.writeLine(msg)
    else: echo msg

  if consoleOn and legacy:
    die("--console is for the M1 machine (not --legacy)")

  # --console: the rings in the API block (memory-map.md), moved to and from
  # this terminal as fw/sysctl/core/console.c moves them to a PC
  const
    ConOutHead = 0x6f22
    ConOutTail = 0x6f23
    ConInHead = 0x6f24
    ConInTail = 0x6f25
    ConFlags = 0x6f26
    ConOut = 0x6f40
    ConIn = 0x6fc0
  var conPending: seq[char]         # typed, not yet in CON_IN
  var conCr = false                 # the last byte typed was CR
  var conEof = false                # stdin has ended
  var conSaved: Termios
  var conRaw = false

  proc cfmakeraw(t: ptr Termios) {.importc, header: "<termios.h>".}

  proc consoleRestore() {.noconv.} =
    if conRaw:
      discard tcSetAttr(0, TCSADRAIN, addr conSaved)
      conRaw = false

  proc consoleStart() =
    if isatty(0) != 0:
      discard tcGetAttr(0, addr conSaved)
      var t = conSaved
      cfmakeraw(addr t)
      discard tcSetAttr(0, TCSANOW, addr t)
      conRaw = true
      addExitProc(consoleRestore)
      stderr.write("sim: the USB console on this terminal: Ctrl-] quits\r\n")
    discard fcntl(0, F_SETFL, fcntl(0, F_GETFL) or O_NONBLOCK)

  proc consolePoll(input: bool): bool =
    ## one poll of the card's: HOST, CON_OUT to stdout, stdin to CON_IN
    ## (only once `input`: the kernel is up, so its boot does not zero what
    ## was typed ahead); true if anything moved
    if (mem[ConFlags] and 1) == 0:
      mem[ConFlags] = 1               # opened, or the kernel zeroed it at boot
    var t = mem[ConOutTail] and 127
    let h = mem[ConOutHead] and 127
    var s = ""
    while t != h:
      let c = mem[ConOut + t] and 0xff
      if c == 10: s.add("\r\n") else: s.add(chr(c))
      t = (t + 1) and 127
    mem[ConOutTail] = t
    if s.len > 0:
      stdout.write(s)
      flushFile(stdout)
      result = true
    if not conEof:
      var buf: array[256, char]
      let n = posix.read(0, addr buf[0], buf.len)
      if n == 0:
        conEof = true
      for i in 0 ..< max(n, 0):
        if conRaw and buf[i] == '\x1d':
          quit(0)
        conPending.add(buf[i])
    var hd = mem[ConInHead] and 63
    let tl = mem[ConInTail] and 63
    while input and conPending.len > 0 and ((hd + 1) and 63) != tl:
      let b = conPending[0]
      conPending.delete(0)
      let afterCr = conCr
      conCr = b == '\r'
      var k = b
      if b == '\n':
        if afterCr: continue          # CR LF: one Enter
        k = '\r'
      mem[ConIn + hd] = ord(k)
      hd = (hd + 1) and 63
      result = true
    mem[ConInHead] = hd

  proc setupCards() =
    ## The M1 machine: the cards in their slots, the SD image in the storage
    ## card, the ROM image in the ROM chip, and reset into the boot ROM.
    var kinds: seq[int]
    for name in cardList.split(','):
      let k = cardKind(name)
      if k < 0:
        die("unknown card kind '" & name & "' (" & CardKindNames & ")")
      kinds.add(k)
    if kinds.len > 6:
      die("6 slots, " & $kinds.len & " cards")
    if kinds.filterIt(it == CardStorage).len > 1:
      die("one storage card at most (the card's FatFs has one volume per process)")
    machineCards(kinds)
    if sdPath.len > 0:
      if CardStorage notin kinds:
        die("--sd needs a storage card in --cards")
      if not fileExists(sdPath):
        try:
          makeFatImage(sdPath)
        except IOError as e:
          die(e.msg)
        note("made a blank FAT image " & sdPath)
      for c in slots:
        if not c.isNil and simcard_type(c) == CardStorage and
           simcard_storage_image(c, cstring(sdPath), 0) != 0:
          die("cannot open the SD image " & sdPath)
    try:
      if romPath.len == 0:
        romPath = if binPath.len > 0: makeRom(buildBootRom(), binPath, binPath.changeFileExt("rom"))
                  else: buildKernelRom()
    except IOError as e:
      die(e.msg)
    cpuReset()
    cpuLoadRom(romPath)
    cpuBootRom()
    if not scaleSet:
      display_setScale(2)          # 640x480 at 3x does not fit most screens
    display_setSize(GpuOutW, GpuOutH)

  if not legacy:
    setupCards()
  elif binPath.len == 0:
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

  if legacy:
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
            of K_ESCAPE:
              pushKey(27)
            of K_TAB:
              pushKey(9)
            else:
              # Ctrl+letter (no TextInput comes for it)
              let sym = int(e.keysym.sym)
              if (e.keysym.modstate and KMOD_CTRL) != 0 and sym >= ord('a') and sym <= ord('z'):
                pushKey(sym - ord('a') + 1)
        else:
          discard

  # Hooks for later features (a program to load and run, ...): each runs
  # once, when the kernel first parks in WAI (it is at its prompt).
  var onKernelReady: seq[proc()] = @[]

  proc runCards() =
    ## The M1 machine's main loop. The CPU runs flat out; while it is parked
    ## in WAI, guest time follows the host clock (interactive) or runs on
    ## without sleeping (headless). --type keys go in one at a time, each
    ## once the CPU has run and parked in WAI again.
    var pos = 0                       # next key of `typed`
    var ranSinceKey = true
    var keyAt = 0                     # ins_retired when the last key went in
    var readyDone = false
    var idleAt = -1                   # ins_retired when the typed text was used up and the CPU parked
    var lastReal = epochTime()
    # guest time is one microsecond per instruction (WAI steps included);
    # interactive runs keep it level with the host clock from here
    let realStart = lastReal
    let insStart = ins_retired
    var lastPresent = 0.0
    var lastMhz = lastReal
    var lastMhzIns = 0
    var conLast = 0                   # ins_retired at the last console poll
    if consoleOn: consoleStart()
    while not atend:
      if HF or PC >= imageEnd:
        note("HALT!")
        break
      if maxIns > 0 and ins_retired >= maxIns:
        break
      if consoleOn and ins_retired - conLast >= 2000:
        conLast = ins_retired         # every 2 guest ms, as the card polls
        if consolePoll(readyDone) or conPending.len > 0 or not conEof:
          idleAt = -1                 # still typing, or printing: not idle
      if headless and idleAt >= 0 and ins_retired - idleAt >= settleMs * 1000:
        break
      if waiting:
        if not readyDone:
          readyDone = true
          for hook in onKernelReady: hook()
        if not ranSinceKey and ins_retired - keyAt >= settleMs * 1000:
          ranSinceKey = true          # the key woke nothing (no IO card, IRQs off): go on
        if ranSinceKey:
          if pos < typed.len:
            pushKey(ord(typed[pos]))
            inc pos
            ranSinceKey = false
            keyAt = ins_retired
          elif idleAt < 0:
            idleAt = ins_retired
        var steps = 1000
        if not headless:
          # sleep only while the guest is ahead of the host clock: a sleep per
          # WAI would cap a machine that wakes often (a timer tick) at a few
          # hundred instructions per millisecond
          let behind = insStart + int((epochTime() - realStart) * 1_000_000) - ins_retired
          if behind <= 0:
            sleep(1)
            steps = 1000
          else:
            steps = min(behind, 100_000)
        if maxIns > 0:
          steps = min(steps, maxIns - ins_retired)
        var i = 0
        while i < steps and waiting and not HF:
          discard cpuStep()
          inc i
      else:
        ranSinceKey = true
        var batch = 4096
        if maxIns > 0:
          batch = min(batch, maxIns - ins_retired)
        if doTrace:
          echo "TRACE pc=$1 op=$2" % [toHex(PC, 4), toHex(memRead(PC), 2)]
          batch = 1
        discard cpuRun(batch)
      if not headless:
        let now = epochTime()
        if now - lastPresent >= 0.016:
          pumpInput()
          gpuPresent()
          display_render()
          lastPresent = now
        if now - lastMhz >= 1.0:
          status(speedLine(float(ins_retired - lastMhzIns) / (now - lastMhz)))
          lastMhz = now
          lastMhzIns = ins_retired
      lastReal = epochTime()
    note(cpuStatusLine())
    if dumpText.len > 0:
      let g = gpuCard()
      if g.isNil:
        stderr.writeLine("sim: --dump-text: no graphics card")
      else:
        let text = screenLines(g).join("\n") & "\n"
        if dumpText == "-": stdout.write(text)
        else: writeFile(dumpText, text)
    if dumpFb.len > 0:
      gpuPresent()
      display_dumpPpm(dumpFb)
      note("wrote framebuffer " & dumpFb)
    if not headless and maxIns == 0 and not atend:
      while not atend:                # halted: keep the window up until it is closed
        pumpInput()
        display_render()
        sleep(16)

  if not legacy:
    runCards()
    quit(0)

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
      if waiting:
        pumpInput()
        sleep(1)
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
            status(speedLine(float(ins_retired - lastMhzIns) / dt))
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
