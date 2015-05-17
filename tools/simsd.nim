import strutils

var
  mem: array[0x1000000, int]
  state = "POWERON"
  crc: array[2, int]
  cmd_data: array[8, int]
  address: int
  pos_cmd: int
  pos_buf: int
  r1: int
  token: int
  spi_ready: int

proc sd_transact*(b: int): int =
  #writeln(stdout, "enter state = $1" % state)
  spi_ready = 0
  if state == "READ_OP":
    if pos_buf == 0:
      # data token
      result = 0xfe
    elif pos_buf < 513:
      result = mem[address + pos_buf - 1]
    else:
      result = crc[pos_buf - 512 - 1]

    inc pos_buf

    if pos_buf == 515:
      pos_buf = 0
      state = "READY"
  elif state == "WRITE_OP":
    if pos_buf == 0:
      # data token
      token = b
    elif pos_buf < 513:
      mem[address + pos_buf - 1] = b

    inc pos_buf

    if pos_buf == 516:
      # data response
      pos_buf = 0
      state = "READY"
      result = 0x05
  else:
    # reading cmd data
    if b != 0xff:
      r1 = 0xff
      cmd_data[pos_cmd] = b
      inc pos_cmd
    else:
      # do cmd & read response
      
      pos_cmd = 0
      #address = (cmd_data[1] shl 24) or (cmd_data[2] shl 16) or (cmd_data[3]) shl 8) or (cmd_data[4])
      
      # parse cmds 
      case cmd_data[0] and 0x3f:
        of 0:
          state = "IDLE"
          r1 = 0x01
        of 1:
          if state == "IDLE":
            r1 = 0x00
            state = "READY"
          else:
            r1 = 0x04
            state = "POWERON"
        of 16:
          # set blocklen; just assume 512 for now
          if state == "READY":
            r1 = 0x00
          else:
            r1 = 0x04
        of 17:
          # read
          if state == "READY":
            r1 = 0x00
            state = "READ_OP"
          else:
            r1 = 0x04
        of 24:
          # write
          if state == "READY":
            r1 = 0x00
            state = "WRITE_OP"
          else:
            r1 = 0x04
        else:
          r1 = 0x01
 
      result = r1

  spi_ready = 1
  #writeln(stdout, "exit state = $1" % state)
  return result

proc sd_isready*(): int = 
  result = spi_ready
  return

var a = sd_transact(64 + 0)
a = sd_transact(0)
a = sd_transact(0)
a = sd_transact(0)
a = sd_transact(0)
a = sd_transact(1)
writeln(stdout, "r1: $1" % toHex(sd_transact(0xff), 2))

a = sd_transact(64 + 1)
a = sd_transact(0)
a = sd_transact(0)
a = sd_transact(0)
a = sd_transact(0)
a = sd_transact(1)
writeln(stdout, "r1: $1" % toHex(sd_transact(0xff), 2))

a = sd_transact(64 + 16)
a = sd_transact(0)
a = sd_transact(0)
a = sd_transact(2)
a = sd_transact(0)
a = sd_transact(1)
writeln(stdout, "r1: $1" % toHex(sd_transact(0xff), 2))

a = sd_transact(64 + 24)
a = sd_transact(0)
a = sd_transact(0)
a = sd_transact(0)
a = sd_transact(0)
a = sd_transact(1)
writeln(stdout, "r1: $1" % toHex(sd_transact(0xff), 2))
for i in 0..512:
  a = sd_transact(i mod 256)
a = sd_transact(0)
a = sd_transact(0)
writeln(stdout, "data response: $1" % toHex(sd_transact(0xff), 2))

a = sd_transact(64 + 17)
a = sd_transact(0)
a = sd_transact(0)
a = sd_transact(0)
a = sd_transact(0)
a = sd_transact(1)
writeln(stdout, "r1: $1" % toHex(sd_transact(0xff), 2))
for i in 0..512:
  a = sd_transact(0xff)
  #echo a
a = sd_transact(0xff)
a = sd_transact(0xff)
