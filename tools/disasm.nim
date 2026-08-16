## Pure CUPC/8 instruction decoder used by the terminal debugger.

import strutils

type DisIns* = object
  address*, len*: int
  text*: string
  valid*: bool
  isBranch*, isCall*: bool
  target*: int

proc hexByte(value: int): string = "0x" & toHex(value and 0xff, 2)
proc hexAddr(value: int): string = "$" & toHex(value and 0xffff, 4)
proc regName(bit: int): string = (if bit == 0: "r0" else: "r1")

proc disasm*(m: openArray[int]; a: int; collapseCalls = true): DisIns =
  result = DisIns(address: a, len: 1, text: "", valid: false,
                  isBranch: false, isCall: false, target: -1)
  if a < 0 or a > m.high:
    result.text = "db 0x00"
    return

  let op = m[a] and 0xff
  if collapseCalls and a + 4 <= m.high and op == 0x96 and
      (m[a + 1] and 0xff) == 0x97 and (m[a + 2] and 0xff) == 0xb0:
    result.len = 5
    result.valid = true
    result.isBranch = true
    result.isCall = true
    result.target = (m[a + 3] and 0xff) or ((m[a + 4] and 0xff) shl 8)
    result.text = "call " & hexAddr(result.target)
    return

  let
    base = op and 0xf8
    operands = op and 7
    dst = operands and 1
    src = (operands shr 1) and 1
    immediate = (operands and 4) != 0

  template need(count: int): bool = a + count - 1 <= m.high
  template immValue(): int = m[a + 1] and 0xff
  template addrValue(): int =
    (m[a + 1] and 0xff) or ((m[a + 2] and 0xff) shl 8)

  case base
  of 0x80:
    result.valid = true
    result.text = "nop"
  of 0xf8:
    result.valid = true
    result.text = "halt"
  of 0xc0:
    result.valid = true
    result.text = "cli"
  of 0xc8:
    result.valid = true
    result.text = "sti"
  of 0xf0:
    result.valid = true
    result.text = "wai"
  of 0xb0, 0xb8:
    if not need(3):
      result.text = "db " & hexByte(op)
      return
    result.valid = true
    result.len = 3
    result.target = addrValue()
    result.isBranch = true
    result.text = (if base == 0xb0: "b " else: "bzf ") &
                  hexAddr(result.target)
  of 0xa0, 0x70:
    if not need(3):
      result.text = "db " & hexByte(op)
      return
    result.valid = true
    result.len = 3
    result.target = addrValue()
    let mnemonic = if base == 0xa0: "ld " else: "ldd "
    result.text = mnemonic & regName(dst) & ", " & hexAddr(result.target)
    if immediate:
      result.text.add("+" & regName(src))
  of 0xa8, 0x78:
    if not need(3):
      result.text = "db " & hexByte(op)
      return
    result.valid = true
    result.len = 3
    result.target = addrValue()
    let mnemonic = if base == 0xa8: "st " else: "std "
    result.text = mnemonic & hexAddr(result.target)
    if immediate:
      result.text.add("+" & regName(dst))
    result.text.add(", " & regName(src))
  of 0x90:
    result.valid = true
    if operands == 6:
      result.text = "push pch"
    elif operands == 7:
      result.text = "push pcl"
    elif immediate:
      if not need(2):
        result.valid = false
        result.text = "db " & hexByte(op)
        return
      result.len = 2
      result.text = "push #" & hexByte(immValue())
    else:
      result.text = "push " & regName(src)
  of 0x98:
    result.valid = true
    if operands == 6:
      result.text = "pop pch"
    elif operands == 7:
      result.text = "pop pcl"
    elif operands == 4:
      result.text = "pop f"
    else:
      result.len = if immediate: 2 else: 1
      if not need(result.len):
        result.valid = false
        result.len = 1
        result.text = "db " & hexByte(op)
        return
      result.text = "pop " & regName(dst)
  of 0x00, 0x08, 0x10, 0x18, 0x20, 0x30, 0x38, 0x40, 0x48,
     0x60, 0x68, 0x88, 0xe0, 0xe8:
    let name =
      case base
      of 0x00: "eq"
      of 0x08: "gt"
      of 0x10: "lt"
      of 0x18: "and"
      of 0x20: "or"
      of 0x30: "xor"
      of 0x38: "nor"
      of 0x40: "add"
      of 0x48: "sub"
      of 0x60: "shl"
      of 0x68: "shr"
      of 0x88: "mov"
      of 0xe0: "tmr0"
      else: "tmr1"
    result.valid = true
    result.text = name & " " & regName(dst) & ", "
    if immediate:
      if not need(2):
        result.valid = false
        result.text = "db " & hexByte(op)
        return
      result.len = 2
      result.text.add("#" & hexByte(immValue()))
    else:
      result.text.add(regName(src))
  else:
    result.text = "db " & hexByte(op)
