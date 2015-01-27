#!/usr/bin/env python3

import struct
import sys

def write_ram(s, addr, data):
    print('Writing...');
    data = bytearray(5) + data
    struct.pack_into('>BHH', data, 0, 61, len(data)-5, addr)
    import time
    for d in data:
        time.sleep(0.3)
        b = bytearray(1)
        b[0] = d
        s.write(b)
        print('.',end='')
        sys.stdout.flush()
    print('\nDone');

def read_ram(s, addr, size):
    print('Reading...');
    data = bytearray(5)
    struct.pack_into('>BHH', data, 0, 43, size, addr)
    import time
    for d in data:
        time.sleep(0.3)
        b = bytearray(1)
        b[0] = d
        s.write(b)
    data = bytearray(size)
    for i in range(size):
        data[i] = ord(s.read())
        print('.',end='')
        sys.stdout.flush()
    print('\nDone');
    return data

import hashlib
def write_and_verify(s, addr, data):
    write_ram(s, addr, data)
    data2 = read_ram(s, addr, len(data))
    if hashlib.sha256(data).digest() == hashlib.sha256(data2).digest():
        return True
    return False

def write_file(s, addr, filename):
    with open(filename, 'rb') as f:
        data = f.read()
        res = write_and_verify(s, addr, data)
        if res:
            print("Wrote {} bytes successfully".format(len(data)))
            return True
        else:
            print("Failed!")
            return False

import sys
addr = 0
if len(sys.argv) > 3:
    addr = int(sys.argv[3], 0)
device = sys.argv[1]
import serial
s = serial.Serial(port=device, baudrate=115200)
#s = serial.Serial(port=device, baudrate=9600)
#q = bytearray(1)
#q[0] = ord('?')
#s.write(q)
#print(s.readline())
#print(s.readline())
#print(s.readline())
for i in range(100):
    print('{}:'.format(i*5))
    r = write_file(s, addr+5*i, sys.argv[2])
    if not r: break
s.close()
