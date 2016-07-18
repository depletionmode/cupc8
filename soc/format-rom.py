#!/usr/bin/env python3
s = ''
with open('rom0.bin', 'rb') as f:
    i = 0
    for d in f.read():
        if i % 16 == 0:
            s += '\n'
        s += 'x"%.2x", ' % d
        i += 1
    s = s[:-2]


l = ''
with open('rom.vhd', 'rt') as f:
    lines = f.readlines()
    state = 0
    for i in lines:
        if i.find('ROMCODE') >= 0:
            if state == 0:
                l += '--ROMCODE'
                l += s + '\n'
            state ^= 1
        if state == 0:
            l += i

with open('rom.vhd', 'wt') as f:
    f.write(l);

#print(l)
