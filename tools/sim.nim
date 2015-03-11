
# cupcake simulator - nim edition!

import strutils

proc log(lvl, msg) =
    writeln(stdout, msg)

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

proc fetch(): int =
  result = mem[PC] and 0xff
  log(3, "fetch(): $1 $2" % [toHex(PC, 4), toHex(mem[PC], 2)])
  PC += 1

proc reg_write(operands, val: int) =
  if (operands and 1) == 1:
    R1 = val and 0xff
  else:
    R0 = val and 0xff

proc reg_read(operands: int, dst_reg: bool): int =
  var bit = 2
  if dst_reg:
    bit = 1
  if (operands and bit) == bit:
    result = R1 and 0xff
  else:
    result = R0 and 0xff 

proc get_imm(operands: int): tuple[has_imm: bool, val: int] =
  if (operands and 4) == 4:
    log(3, "get_imm(): $1" % $operands)
    var imm = fetch()
    result = (true, imm)
  else:
    result = (false, 0)

type fop = (proc(operands: int))

proc ins_nop(o: int) = 
  # do nothing?? how to do this? todo python 'pass' equivalent
  var a: int = 1

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
  log(0, "mov")
  var tup = get_imm(o)
  var imm = tup[0]
  var rb = tup[1]
  log(0, "$1" % toHex(rb, 2))
  if not imm:
    rb = reg_read(o, false)
  reg_write(o, rb)

proc ins_st(o: int) =
  var address = fetch() or fetch() shl 8
  if (o and 4) == 4:
    var ra = reg_read(o, true)
    address += ra
  mem[address] = reg_read(o, false)
  # todo -mmu

proc ins_ld(o: int) =
  var address = fetch() or fetch() shl 8
  if (o and 4) == 4:
    var rb = reg_read(o, true)
    address += rb
  reg_write(o, mem[address])
  # todo -mmu

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

proc ins_b(o: int) =
  PC = fetch() or (fetch() shl 8)

proc ins_bzf(o: int) =
  var tmp = fetch() or (fetch() shl 8)
  if ZF:
    PC = tmp

proc ins_halt(o: int) =
  log(0, "HALT!")
  HF = true

proc decode() =
  var op = fetch()
  log(3, "decode: $1" % toBin(op, 8))
  var ins = op and 0xf8
  # todo - call function table1
  var r = op and 7
  case ins:
    of 0x80: ins_nop(r)
    of 0x88: ins_mov(r)
    #of 0x90: ins_push(r)
    #of 0x98: ins_pop(r)
    of 0xa0: ins_ld(r)
    of 0xa8: ins_st(r)
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
      log(1, "Unsupported op = $1!" % toHex(ins, 2))
  log(2, "  r0 = $1" % toHex(R0, 2))
  log(2, "  r1 = $1" % toHex(R1, 2))
  log(2, "  pc = $1" % toHex(PC, 4))
  log(2, "  sp = $1" % toHex(SP, 4))
  #log(2, "  zf = $1" % ZF)

proc exec() =
  # todo - time/speed
  var ins_ctr = 0
  while PC != eof and not HF:
    ins_ctr += 1
    decode()
    if ins_ctr mod 500000 == 0:
      ins_ctr = 0

import os
proc loadcode() =
  let code = if paramCount() > 0: readFile paramStr(1)
             else: readAll stdin
  var i = 0
  while i < code.len:
    mem[0x1000+i] = int(code[i])
    i += 1
  eof = PC + i 

loadcode()
exec()
