
# cupcake simulator - nim edition!

import strutils
import times
import terminal
import sdl2, sdl2/gfx

import simdisplay
import simsd

discard sdl2.init(INIT_EVERYTHING)

system.addQuitProc(resetAttributes)

var log_mask = 9
proc log(lvl, msg) =
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
        writeln(stdout, msg)
        resetAttributes()

var
  PC: int = 0x1000
  SP: int = 0x0100
  R0: int = 0
  R1: int = 0
  ZF: bool = false
  HF: bool = false
  pcl: int = 0
  mem: array[0..0x10000, int]
  eof: int = 0

var
  spi_tx_buf: array[0..4, int]
  spi_rx_buf: array[0..4, int]
  keybuffer: int = 0xff
  has_key: bool = false

var
  display_active: bool = false

proc fetch(): int =
  result = mem[PC] and 0xff
  #log(4, "fetch(): $1 $2" % [toHex(PC, 4), toHex(mem[PC], 2)])
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
    #log(4, "get_imm(): $1" % $operands)
    var imm = fetch()
    result = (true, imm)
  else:
    result = (false, 0)

type fop = (proc(operands: int))

proc do_alu(o: int, v: int) =
  var tup = get_imm(o)
  var imm = tup[0]
  var rb = tup[1]
  if not imm:
    rb = reg_read(o, false)
  var ra = reg_read(o, true)
  reg_write(o, v)

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
  mem[address] = reg_read(o, false)
  # todo -mmu
  # mmu
  case address shr 8:
    of 0xf0:
      if (address and 0xff) == 0: #gpo
        log(1, "GPO: $1 $2" % [toBin(mem[address], 8), toHex(mem[address], 2)])
    of 0xf1:    # spi
      var dev = address shr 4 and 0xf
      if dev == 0:  # display
        if not display_active:
          display_active = true
          # simdisplay.init()
      var reg = address and 0xf
      case reg:
        of 0:   # tx
          spi_tx_buf[dev] = reg_read(o, false)
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
              #log(1, "HAS KEY $1" % [toHex(keybuffer, 2)])
              spi_rx_buf[dev] = keybuffer
              has_key = false
          else:
            discard
        else:
          discard
    else:
      discard

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
  reg_write(o, mem[address])
  # todo -mmu
  # mmu
  case address shr 8:
    of 0xf1:    #spi
      var dev = address shr 4 and 0xf
      var reg = address and 0xf
      case reg:
        of 1:   # rx
          #if spi_rx_buf[dev] != 0xff:
          #    echo "READ"
          reg_write(o, spi_rx_buf[dev])
        of 3:   # status
          case dev:
            of 0: #display
              reg_write(o, 1) # always return 1 for now (TODO)
            of 2: #keyboard
              # TODO THIS BLOCKING HACK WONT WORK ON REAL HARDWARE!!! :( :(
              if has_key:
                reg_write(o, 1) # always return 1 for now (TODO)
              else:
                reg_write(o, 0) # always return 1 for now (TODO)
            of 1: #sd
              reg_write(o, sd_isready())
            else:
              discard
        else:
          discard
    else:
      discard

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

proc ins_not(o: int) = 
  var ra = reg_read(o, true)
  reg_write(o, not ra)

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
  #log(4, "stack push($1): $2" % [toHex(SP, 4), toHex(mem[SP], 2)])

proc ins_pop(o: int) =
  if (o and 7) == 7:
    pcl = mem[SP]
  elif (o and 6) == 6:
    PC = pcl or (mem[SP] shl 8)
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

proc decode() =
  var op = fetch()
  #log(4, "decode: $1" % toBin(op, 8))
  var ins = op and 0xf8
  ## todo - call function table1
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
    of 0xf8: ins_halt(r)
    else:
      discard
      #log(1, "Unsupported op = $1!" % toHex(ins, 2))
  #log(2, "  r0 = $1" % toHex(R0, 2))
  #log(2, "  r1 = $1" % toHex(R1, 2))
  #log(2, "  pc = $1" % toHex(PC, 4))
  #log(2, "  sp = $1" % toHex(SP, 4))
  #log(2, "  zf = $1" % ZF)

import os
proc loadcode() =
  when defined(emscripten):
    let code = readFile "kernel.o"
  else:
    let code = if paramCount() > 0: readFile paramStr(1)
               else: readAll stdin
  var i = 0
  while i < code.len:
    mem[0x1000+i] = int(code[i])
    i += 1
  eof = PC + i 

when defined(emscripten):
  proc emscripten_set_main_loop(fun: proc() {.cdecl.}, fps,
                                simulate_infinite_loop: cint) {.header: "<emscripten.h>".}

  proc emscripten_cancel_main_loop() {.header: "<emscripten.h>".}

  proc emscripten_set_main_loop_timing(mode: cint, value: cint) {.header: "<emscripten.h>".}

loadcode()

var atend = false
var evt = defaultEvent

proc exec() {.cdecl.} =
  if PC >= eof or HF:
    echo "HALT!"
    when defined(emscripten):
      emscripten_cancel_main_loop()
    atend = true
    return

  when defined(emscripten):
    # run multiple loops per frame
    for i in 0..10000:
      decode()
  else:
    # native so run as fast as possible
    decode()
  
  while pollEvent(evt):
    case evt.kind:
      of QuitEvent:
        atend = true
        break
      of KeyDown:
        let e = evt.key()
        keybuffer = getKeyFromScancode(e.keysym.scancode)
        has_key = true
        #writeln(stdout, "key")
      else:
        discard

when defined(emscripten):
  emscripten_set_main_loop(exec, 0, 0)
else:
  var ins_ctr = 0
  var start = cpuTime()
  while not atend:
    exec()
    ins_ctr += 1
    if ins_ctr mod 100000 == 0:
      ins_ctr = 0
      var elapsed = cpuTime() - start
      log(8, "$1 MHz" % formatFloat(1000000*4/elapsed/10000000, ffDecimal, 2))
      start = cpuTime()
  while true:
      discard

