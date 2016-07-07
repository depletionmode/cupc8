#!/usr/bin/env python3

import serial
import sys
import struct

with open(sys.argv[1], 'rb') as f:
    addr = int(sys.argv[2], 0)
    data = f.read()
    ser = serial.Serial(port='/dev/ttyACM0', baudrate=9600)
    if ser.isOpen():
        s_addr = struct.pack('<H', addr)
        ser.write(s_addr)
        if ser.read(1)[0] != 0xff:
            raise Exception('TX failed: address!')
        print('.')
        s_len = struct.pack('<H', len(data))
        ser.write(s_len)
        if ser.read(1)[0] != 0xff:
            raise Exception('TX failed: len!')
        print('.')
        ser.write(data)
        if ser.read(1)[0] != 0xff:
            raise Exception('TX failed: data!')
        print('.')
        if ser.read(1)[0] != 0x00:
            raise Exception('Verification failed!')
        print('.')
        ser.close()
        print('Flash of {} bytes to ${} succeeded!'.format(len(data), addr));
