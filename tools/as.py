#!/usr/bin/env python3

opcodes = {
            'nop':0x80,     'mov' :0x88,     'push':0x90,     'pop':0x98,
            'ld' :0xa0,     'st'  :0xa8,     'b'   :0xb0,     'bzf':0xb8,
            'eq' :0x00,     'gt'  :0x08,     'lt'  :0x10,     'and':0x18,
            'or' :0x20,     'xor' :0x30,    'nor':0x38,
            'add':0x40,     'sub' :0x48,
            'shl':0x60,     'shr' :0x68
          }

registers = [ 'r0', 'r1' ]

bss = {}
data = {}
data_buf = bytearray()
unresolved_fcns = {}
defines = {}
first_pass = True
labels = {}

base = 0x1000
data_base = 0x2000
bss_base = 0x3000

def __ins_hacks(ins):
    # need to hack syntax to allow decoding to work properly
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

    # deal with comment
    if ins.lstrip()[0] == ';':
        return bytearray()

    imm = None
    addr = None

    mach_code = bytearray(1)

    tokens = ins.split(' ', 1)
    ins = tokens[0]

    # get opcode for ins
    ins = opcodes[ins]

    if len(tokens) > 1:
        operands = tokens[1].split(',')
        op1 = operands[0].strip()

        # op1 - reg/addr/fcn/imm
        if op1[0] == '#':
            ins |= 1 << 2
            imm = int(op1[1:])
            if imm > 0xff:
                raise Exception("Imm out of range")
            mach_code.append(imm)
        elif op1[0] == '$':
            pos = op1.find('+')
            if pos > -1:  # address register offset
                ins |= 1 << 2
                ins |= __get_reg_value(op1[pos+1:])
            else: pos = None
            addr = int(op1[1:pos], 16)
            if addr > 0xffff:
                raise Exception('Addr out of range')
            # little endian
            mach_code.append(addr & 0xff);
            mach_code.append(addr >> 8);
        elif op1[0] == '.':
            if not op1[1:] in labels:
                # label not yet resolved?
                if not first_pass:
                    raise Exception('Function {} not found'.format(op1[1:]))
                mach_code.append(0)
                mach_code.append(0)
            else:
                addr = labels[op1[1:]] + base

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
                pos = op2.find('+')
                if pos > -1:  # address register offset
                    ins |= 1 << 2
                    ins |= __get_reg_value(op2[pos+1:], True)
                else: pos = None
                addr = int(op2[1:pos], 16)
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
    global defines
    for k, v in defines.items():
        l = l.replace(k, v)
    return l

def __assemble(filename):
    global labels
    global first_pass
    global bss,data
    global data_buf
    mach_code = bytearray(3)
    offset = 3 #leave 3 bytes for branch to entry point
    bss = {}
    data = {}
    data_offset = data_base
    bss_offset = bss_base
    data_buf = bytearray()
    first = True

    with open(filename, 'r') as f:
        fcn_name = ''
        for l in f.readlines():
            l = l.lstrip()
            #print(l)

            #deal with blank lines
            if len(l) == 0: continue

            # deal with comments alone on line
            if l[0] == ';': continue

            # .bss
            if l.find('resb') > -1:
                toks = l.split()
                bss[toks[0][:-1]] = (bss_offset, int(toks[2]))
                bss_offset += int(toks[2])
                continue

            # .data
            if l.find('db') > -1:
                toks = l.split(' ', 2)
                data_b = toks[2].split(',')
                data_c = bytearray(len(data_b))
                for i in range(len(data_b)):
                    d = data_b[i].strip()
                    data_c[i] = int(d)
                    
                data[toks[0]] = (data_offset, data_c)
                data_buf += data_c
                data_offset += len(data_c)
                continue

            # variables
            start = l.find('[')
            if start > -1:
                end = l.find(']')
                var = l[start+1:end]
                try:
                    toks = var.split('+')
                    val = bss.get(toks[0], None)
                    if val == None:
                        val = data[toks[0]][0]
                    else:
                        val = val[0]
                    if len(toks) > 1:
                        if int(toks[1]) >= bss[toks[0]][1]:
                            raise Exception('Variable {} expression out of bounds!'.format(toks[0]))
                        val += int(toks[1])
                    l = l.replace('[{}]'.format(var), '${:x}'.format(val))
                except:
                    raise Exception('Variable {} not found in .bss or .data!'.format(toks[0]))


            # defines
            if l[:7] == '%define':
                toks = l.split(' ', 2)
                defines[toks[1]] = toks[2].strip()
                continue

            # perform replacements
            l = __replace_defines(l)

            #  start of new label
            if l.find(':') > 0 and l.find(': resb') < 0:
                if first_pass:
                    labels[l[:l.find(':')]] = offset
                continue

            code = __convert_assembly_ins(l[:l.find(';')])
            mach_code += code
            offset += len(code)

    first_pass = False
    return offset, mach_code

if __name__ == "__main__":
    import sys
    args = sys.argv[1:]

    if len(args) < 1:
        raise Exception('Invalid input/output files')

    offset, mach_code = __assemble(args[0])
    offset, mach_code = __assemble(args[0]) # ulgy hack for bad label lookup logic

    entry_point = 'main'
    if not entry_point in labels:
        raise Exception('No entry point found')

    outf = '{}.o'.format(args[0].split('.')[0])
    if len(args) == 2: outf = args[1]

#    for k,v in labels.items():
#        print(k, v)

    with open(outf, 'wb') as f:
        mach_code[0] = 0xb0
        mach_code[1] = (labels[entry_point] + base) & 0xff
        mach_code[2] = (labels[entry_point] + base) >> 8

        # pass until .data
        padding = bytearray(data_base - len(mach_code) - base)
        buf = mach_code + padding + data_buf
        f.write(buf)

    print('{} -> {} - {} bytes'.format(args[0], outf, len(buf)))
