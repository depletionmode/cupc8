#!/usr/bin/env python3
with open('rom0.bin', 'rb') as f:
    s = ''
    i = 0
    for d in f.read():
        if i % 16 == 0:
            s += '\n'
        s += 'x"%.2x", ' % d
        i += 1
    print(s[:-2]) # cut final comma nad newline
