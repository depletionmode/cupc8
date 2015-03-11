#!/usr/bin/env python3

# cupcake cpu simulator

import sys, argparse

parser = argparse.ArgumentParser(prog='python3 sim.py', description='Simulate CUPCake CPU.')
parser.add_argument('file', help='binary code file to execute', type=argparse.FileType('rb'))
parser.add_argument('-v', help='verbosity [-v ins, -vv reg, -vvv fetch+decode]', action='count')
parser.add_argument('-s', help='speed', action='count')
args = parser.parse_args()

from colorama import init, Style, Back, Fore
init()

# display on spi 0
import simdisplay
display_active=False
spi0_tx_buf = 0

PC = 0x1000
SP = 0x0100
R0 = 0
R1 = 0
ZF = 0
HF = 0

pcl = 0

mem = bytearray(0x10000)
eof = 0

LOG_DIM=False
SHOW_REG=False

def _log(v, s):
    _v = args.v
    if _v == None: _v = 0
    if v <= _v:
        if v >= 3:
            print(Style.DIM + s + Style.RESET_ALL)
        else:
            print(s + Style.RESET_ALL)

def fetch():
    global PC
    _log(3, 'fetch(): {:x} {:x}'.format(PC, mem[PC]))
    PC += 1
    return mem[PC-1]

def reg_write(operands, val):
    global R0
    global R1
    val &= 0xff
    if operands & 1 == 1: R1 = val
    else: R0 = val

def reg_read(operands, dst_reg=False):
    bit = 2
    if dst_reg: bit = 1
    if (operands & bit) == bit: return R1 & 0xff
    return R0 & 0xff

def get_imm(operands):
    if operands & 4:
        _log(3, 'get_imm(): {}'.format(operands))
        return (True, fetch())
    return (False, 0)

ops = {
        'nop':0x80, 'mov':0x88, 'push':0x90, 'pop':0x98,
        'ld' :0xa0, 'st' :0xa8, 'b' :0xb0, 'bzf':0xb8,
        'eq' :0x00, 'gt' :0x08, 'lt' :0x10, 'and':0x18,
        'or' :0x20, 'xor' :0x30, 'nor':0x38,
        'add':0x40, 'sub':0x48,
        'shl':0x60, 'shr':0x68
      }

def _nop(operands):
    pass

def _eq(operands):
    global ZF
    (imm, rb) = get_imm(operands)
    if not imm:
        rb = reg_read(operands)
    ra = reg_read(operands, True)
    ZF = ra == rb

def _or(operands):
    (imm, rb) = get_imm(operands)
    if not imm:
        rb = reg_read(operands)
    ra = reg_read(operands, True)
    reg_write(operands, ra | rb)

def _add(operands):
    (imm, rb) = get_imm(operands)
    if not imm:
        rb = reg_read(operands)
    ra = reg_read(operands, True)
    reg_write(operands, ra + rb)

def _shl(operands):
    (imm, rb) = get_imm(operands)
    if not imm:
        rb = reg_read(operands)
    ra = reg_read(operands, True)
    reg_write(operands, ra << rb)

def _mov(operands):
    (imm, rb) = get_imm(operands)
    if not imm:
        rb = reg_read(operands)
    reg_write(operands, rb)
    pass

def _st(operands):
    addr = fetch() | fetch() << 8
    if operands & 4:
        ra = reg_read(operands, True)
        addr += ra
    mem[addr] = reg_read(operands)
    # mmu
    if addr == 0xf000:  # gpo
        _log(0, Fore.RED + Style.BRIGHT + 'GPO: {0:8b}'.format(mem[addr]))
    if addr >> 4 == 0xf10:  # spi0
        global spi0_tx_buf, display_active
        if not display_active:
            simdisplay.init()
            display_active = True
        reg = addr & 0xf
        if reg == 0:  # tx buf
            spi0_tx_buf = reg_read(operands)  # save for transact
        elif reg == 2: # transact
#            _log(0, Fore.RED + Style.BRIGHT + 'SPI0 WRITE: 0x{:x}'.format(spi0_tx_buf))
            simdisplay.transact(spi0_tx_buf)
            #simdisplay.write(spi0_tx_buf)

def _ld(operands):
    addr = fetch() | fetch() << 8
    if operands & 4:
        rb = reg_read(operands)
        addr += rb
    reg_write(operands, mem[addr])
    # mmu
    if addr >> 4 == 0xf10:  # spi0
        reg = addr & 0xf
        if reg == 1:  # rx buf
            reg_write(operands, 0)  # no rx from display module
        elif reg == 3: # status
            reg_write(operands, 1)  # always return DONE for now

def _gt(operands):
    global ZF
    (imm, rb) = get_imm(operands)
    if not imm:
        rb = reg_read(operands)
    ra = reg_read(operands, True)
    ZF = ra > rb

def _not(operands):
    ra = reg_read(operands, True)
    reg_write(operands, ~ra)

def _sub(operands):
    (imm, rb) = get_imm(operands)
    if not imm:
        rb = reg_read(operands)
    ra = reg_read(operands, True)
    reg_write(operands, ra - rb)

def _shr(operands):
    (imm, rb) = get_imm(operands)
    if not imm:
        rb = reg_read(operands)
    ra = reg_read(operands, True)
    reg_write(operands, ra >> rb)

def _push(operands):
    global SP
    rb = 0
    if operands & 7 == 7:
        rb = (PC + 3) & 0xff
    elif operands & 6 == 6:
        rb = (PC + 4) >> 8
    else:
        (imm, rb) = get_imm(operands)
        if not imm:
            rb = reg_read(operands)

    SP += 1
    mem[SP] = rb
    _log(3, 'stack push({:3x}): {:2x}'.format(SP, mem[SP]))

def _b(operands):
    global PC
    PC = fetch() | fetch() << 8

def _lt(operands):
    global ZF
    (imm, rb) = get_imm(operands)
    if not imm:
        rb = reg_read(operands)
    ra = reg_read(operands, True)
    ZF = ra < rb

def _xor(operands):
    (imm, rb) = get_imm(operands)
    if not imm:
        rb = reg_read(operands)
    ra = reg_read(operands, True)
    reg_write(operands, ra ^ rb)

def _inc(operands):
    ra = reg_read(operands, True)
    reg_write(operands, ra + 1)

def _call(operands):
    pass

def _pop(operands):
    global SP, PC, pcl
    if operands & 7 == 7:
        pcl = mem[SP]
    elif operands & 6 == 6:
        PC = pcl | mem[SP] << 8
    else:
        reg_write(operands, mem[SP])

    _log(3, 'stack pop({:3x}): {:2x}'.format(SP, mem[SP]))
    SP -= 1

def _bzf(operands):
    global PC
    tmp = fetch() | fetch() << 8
    if ZF:
       PC = tmp

def _and(operands):
    (imm, rb) = get_imm(operands)
    if not imm:
        rb = reg_read(operands)
    ra = reg_read(operands, True)
    reg_write(operands, ra & rb)

def _nor(operands):
    (imm, rb) = get_imm(operands)
    if not imm:
        rb = reg_read(operands)
    ra = reg_read(operands, True)
    reg_write(operands, ~(ra | rb))

def _dec(operands):
    ra = reg_read(operands, True)
    reg_write(operands, ra - 1)

def _halt(operands):
    global HF
    HF = 1

def _ret(operands):
    pass

fops = {
        0x80:_nop, 0x88:_mov,  0x90:_push, 0x98:_pop,
        0xa0:_ld,  0xa8:_st,   0xb0:_b,    0xb8:_bzf,
        0x00:_eq,  0x08:_gt,   0x10:_lt,   0x18:_and,
        0x20:_or,  0x30:_xor,  0x38:_nor,
        0x40:_add, 0x48:_sub,
        0x60:_shl, 0x68:_shr,
        0xf8:_halt
       }

def decode():
    op = fetch()
    _log(3, 'decode: {:b}'.format(op))
    ins = op & 0xf8
    for k,v in ops.items(): # dirty
        if v == ins: _log(1, Style.BRIGHT + Fore.WHITE + '{0:x}: {1}'.format(PC-1, k))
    fops[ins](op & 7)
    _log(2, Fore.GREEN + '  r0 = {:2x}\n  r1 = {:2x}\n  pc = {:4x}\n  sp = {:4x}\n  zf = {:b}\n'.format(R0, R1, PC, SP, ZF))

NUM_INS = 500000
AVE_CLK_PER_INS = 5
def exec():
    import time, functools
    ins_ctr = 0
    start = time.clock()
    while PC != eof and HF == 0:
        ins_ctr += 1
        decode()
        if ins_ctr % NUM_INS == 0:
            ins_ctr = 0
            if args.s != None:
                print('{:.2f} KHz'.format(NUM_INS*4/(time.clock() - start)/1000))
            start = time.clock()

# load code into mem
i = 0
while True:
    b = args.file.read(1)
    if len(b) == 0: break
    mem[0x1000+i] = int.from_bytes(b, byteorder='little')
    i += 1
eof = PC + i

exec()

_log(0, Style.DIM + Fore.GREEN + 'Simulation done.')
