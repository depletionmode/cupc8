#!/usr/bin/env python3

import sys, struct

VER_MAJ = 1
VER_MIN = 0

metadata = bytearray(256)
metadata[0] = VER_MAJ
metadata[1] = VER_MIN
struct.pack_into('<H', metadata, 254, 0xf00d)

#fake some files
struct.pack_into('<10sHHBB', metadata, 8, b'testfile00', 10, 512, 0, 1)
struct.pack_into('<10sHHBB', metadata, 8+16, b'testfile01', 10, 512, 0, 0)
struct.pack_into('<10sHHBB', metadata, 8+32, b'testfile02', 64*1024-1, 1024, 0, 1)

img = sys.argv[1]

with open(img, 'wb') as f:
    f.write(metadata)

