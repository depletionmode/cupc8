opcodes =
        {
            'nop':0x80,     'mov':0x88,     'push':0x90,    'pop':0x98,
            'ld':0xa0,      'st':0xa8,      'b':0xb0,       'bne':0xb8,
            'eq':0x00,      'gt':0x08,      'lt':0x10,      'and':0x18,
            'or':0x20,      'not':0x28,     'xor':0x30,     'nor':0x38,
            'add':0x40,     'sub':0x48,     'inc':0x50,     'dec':0x58,
            'shl':0x60,     'shr':0x68
        }

registers = [ 'r0', 'r1' ]

def __convert_assembly_ins(ins):
    # mov r0, r1
    op, operands = ins.split(' ', 1)
    operand1, operand2 = operands.split(',')
    operand2 = operand.lstrip()

