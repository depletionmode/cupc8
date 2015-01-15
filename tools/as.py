opcodes = {
            'nop':0x80,     'mov':0x88,     'push':0x90,     'pop':0x98,
            'ld' :0xa0,     'st' :0xa8,     'b'   :0xb0,     'bne':0xb8,
            'eq' :0x00,     'gt' :0x08,     'lt'  :0x10,     'and':0x18,
            'or' :0x20,     'not':0x28,     'xor' :0x30,     'nor':0x38,
            'add':0x40,     'sub':0x48,     'inc' :0x50,     'dec':0x58,
            'shl':0x60,     'shr':0x68,     'call':0xc0,     'ret':0xc1
          }

registers = [ 'r0', 'r1' ]

functions = {}
defines = {}
first_pass = True

base = 0x1000

def __ins_hacks(ins):
    # need to hack syntax to allow decoding to work properly
    #dst_ops = ['push','st']
    dst_ops = ['push']
    tokens = ins.split(' ')
    if tokens[0] in dst_ops:
        return '{} ?, {}'.format(tokens[0], tokens[1])
    else:
        return ins

def __get_reg_value(reg, second_op=False):
    if reg == 'r0': return 0
    elif reg == 'r1':
        if second_op: return 2
        else: return 1
    elif reg == 'pch': return 6
    elif reg == 'pcl': return 7
    else: raise Exception("Invalid operand register")

def __convert_assembly_ins(ins):
    ins = __ins_hacks(ins.strip())

    #print(ins)

    # deal with comment
    if ins.lstrip()[0] == ';':
        return bytearray()

    imm = None
    addr = None

    mach_code = bytearray(1)

    tokens = ins.split(' ', 1)
    #print(tokens)
    ins = tokens[0]

    # get opcode for ins
    ins = opcodes[ins]

    if len(tokens) > 1:
        operands = tokens[1].split(',')
        op1 = operands[0].strip()

        # op1 - reg/addr/fcn/imm
        if op1[0] == '#':
            ins |= 1 << 2;
            imm = int(op1[1:])
            if imm > 0xff:
                raise Exception("Imm out of range")
            mach_code.append(imm)
        elif op1[0] == '$':
            addr = int(op1[1:], 16)
            if addr > 0xffff:
                raise Exception('Addr out of range')
            # little endian
            mach_code.append(addr & 0xff);
            mach_code.append(addr >> 8);
        elif op1[0] == '.':
            if not op1[1:] in functions:
                raise Exception('Function {} not found'.format(op1[1:]))

            addr = functions[op1[1:]][0] + base

            mach_code.append(addr & 0xff);
            mach_code.append(addr >> 8);
        elif op1[0] == '?': # dirty hack to allow diry hacks to work
            pass
        else:
            ins |= __get_reg_value(op1)

        if len(operands) > 1:
            op2 = operands[1].strip()

            # 0p2 - reg/imm/addr
            if op2[0] == '#':
                ins |= 1 << 2;
                imm = int(op2[1:])
                if imm > 0xff:
                    raise Exception("Imm out of range")
                mach_code.append(imm)
            elif op2[0] == '$':
                addr = int(op2[1:], 16)
                if addr > 0xffff:
                    raise Exception('Addr out of range')
                # little endian
                mach_code.append(addr & 0xff);
                mach_code.append(addr >> 8);
            else:
                ins |= __get_reg_value(op2, True)

    mach_code[0] = ins;

    return mach_code

def __replace_defines(l):
    for k, v in defines:
	l = ins.replace(k, v)
    return l

if __name__ == "__main__":
    import sys
    args = sys.argv[1:]

    if len(args) < 1:
        raise Exception('Invalid input/output files')

    mach_code = bytearray()
    offset = 3 #leave 3 bytes for branch to entry point
    entry_point = 'main'
    first = True

    with open(args[0], 'r') as f:
        fcn_name = ''
        for l in f.readlines():
            l = l.lstrip()

            #deal with blank lines
            if len(l) == 0: continue

            # deal with comments alone on line
            if l[0] == ';': continue

            # defines
            if l[0] == '%':
                toks = l.split(' ')
                defines[toks[1]] = toks[2]
                continue

            # perform replacements
            l = __replace_defines(l)

            #  start of new function
            if l.find(':') > 0:
                if not first:
                    functions[fcn_name] = (offset,mach_code)
                    offset += len(mach_code)
                    mach_code = bytearray()
                first = False
                fcn_name = l[:l.find(':')]
                continue

            mach_code += __convert_assembly_ins(l[:l.find(';')])

        functions[fcn_name] = (offset,mach_code)
        offset += len(mach_code)

    if not entry_point in functions:
        raise Exception('No entry point found')

    outf = '{}.o'.format(args[0].split('.')[0])
    if len(args) == 2: outf = args[1]

    with open(outf, 'wb') as f:
        import struct
        mach_code = bytearray(offset)
        vw = memoryview(mach_code)
        for k, v in functions.items():
            struct.pack_into(str(len(v[1])) + 's', vw, v[0], v[1])

        mach_code[0] = 0xb0
        mach_code[1] = (functions[entry_point][0] + base) & 0xff
        mach_code[2] = (functions[entry_point][0] + base) >> 8

        f.write(mach_code)

    print('{} -> {} - {} bytes'.format(args[0], outf, len(mach_code)))
