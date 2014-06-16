opcodes = {
            'nop':0x80,     'mov':0x88,     'push':0x90,    'pop':0x98,
            'ld':0xa0,      'st':0xa8,      'b':0xb0,       'bne':0xb8,
            'eq':0x00,      'gt':0x08,      'lt':0x10,      'and':0x18,
            'or':0x20,      'not':0x28,     'xor':0x30,     'nor':0x38,
            'add':0x40,     'sub':0x48,     'inc':0x50,     'dec':0x58,
            'shl':0x60,     'shr':0x68
          }

registers = [ 'r0', 'r1' ]

def __get_reg_value(reg):
    if reg == 'r0': return 0
    elif reg == 'r1': return 1
    else: raise Exception("Invalid operand register")

def __convert_assembly_ins(ins):
    ins = ins.strip()

    #print(ins)

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
        
        # op1 - reg/addr
        if op1[0] == '$':
            addr = int(op1[1:], 16)
            if addr > 0xffff:
                raise Exception('Addr out of range')
            # little endian
            mach_code.append(addr & 0xff);
            mach_code.append(addr >> 8);
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
                ins |= __get_reg_value(op2) << 1

    mach_code[0] = ins;

    return mach_code

if __name__ == "__main__":
    import sys
    args = sys.argv[1:]
    
    if len(args) < 2:
        raise Exception('Invalid input/output files')

    mach_code = bytearray()

    with open(args[0], 'r') as f:
        for l in f.readlines():
            mach_code += __convert_assembly_ins(l)

    with open(args[1], 'wb') as f:
        f.write(mach_code)

    print('{} -> {} - {} bytes'.format(args[0], args[1], len(mach_code)))
