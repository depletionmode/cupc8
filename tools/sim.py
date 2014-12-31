# cpu simulator

import sys, argparse

parser = argparse.ArgumentParser(prog='python3 sim.py', description='Simulate CUPCake CPU.')
parser.add_argument('file', help='binary code file to execute', type=argparse.FileType('rb'))
parser.add_argument('-v', help='verbosity [-v ins, -vv reg, -vvv fetch+decode]', action='count')
args = parser.parse_args()

from colorama import init, Style, Back, Fore
init()

PC = 0x1000
SP = 0x0100
R0 = 0
R1 = 0
ZF = 0

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
        'ld' :0xa0, 'st' :0xa8, 'b' :0xb0, 'bne':0xb8,
        'eq' :0x00, 'gt' :0x08, 'lt' :0x10, 'and':0x18,
        'or' :0x20, 'not':0x28, 'xor' :0x30, 'nor':0x38,
        'add':0x40, 'sub':0x48, 'inc' :0x50, 'dec':0x58,
        'shl':0x60, 'shr':0x68, 'call':0xc0, 'ret':0xc1
      }

def _nop(operands):
    pass

def _ld(operands):
    v = mem[fetch() | fetch() << 8]
    reg_write(operands, v)

def _eq(operands):
    pass

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
    mem[addr] = reg_read(operands)
    # mmu
    if addr == 0xf000:  # gpo
        _log(0, Fore.RED + Style.BRIGHT + 'GPO: {0:8b}'.format(mem[addr]))

def _gt(operands):
    pass

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
    (imm, rb) = get_imm(operands)
    if not imm:
        rb = reg_read(operands)
    SP += 1
    mem[SP] = rb

def _b(operands):
    # todo currently fetch and nop
    fetch()
    fetch()

def _lt(operands):
    pass

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
    reg_write(operands, mem[SP])
    SP -= 1

def _bne(operands):
    pass

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

def _ret(operands):
    pass

fops = {
        0x80:_nop, 0x88:_mov, 0x90:_push, 0x98:_pop,
        0xa0:_ld,  0xa8:_st,  0xb0:_b,    0xb8:_bne,
        0x00:_eq,  0x08:_gt,  0x10:_lt,   0x18:_and,
        0x20:_or,  0x28:_not, 0x30:_xor,  0x38:_nor,
        0x40:_add, 0x48:_sub, 0x50:_inc,  0x58:_dec,
        0x60:_shl, 0x68:_shr, 0xc0:_call, 0xc1:_ret
       }

def decode():
    op = fetch()
    _log(3, 'decode: {:b}'.format(op))
    ins = op & 0xf8
    for k,v in ops.items(): # dirty
        if v == ins: _log(1, Style.BRIGHT + Fore.WHITE + '{0:x}: {1}'.format(PC-1, k))
    fops[ins](op & 7)
    _log(2, Fore.GREEN + '  r0 = {:2x}\n  r1 = {:2x}\n  pc = {:4x}\n  sp = {:4x}\n  zf = {:b}\n'.format(R0, R1, PC, SP, ZF))

def exec():
    while PC != eof:
        decode()

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