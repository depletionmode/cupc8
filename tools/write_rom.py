#!/usr/bin/env python3

import serial
import sys
import struct
import binascii
import time

def send(s, data):
    for b in data:
        ba = bytearray(1)
        ba[0] = b
        s.write(ba)
        time.sleep(0.01)

with open(sys.argv[1], 'rb') as f:
    addr = int(sys.argv[2], 0)
    data = f.read()
    ser = serial.Serial(port='/dev/ttyACM0', baudrate=115200,parity = serial.PARITY_NONE,
    stopbits = serial.STOPBITS_ONE,
    bytesize = serial.EIGHTBITS)
    if ser.isOpen():
        hdr = struct.pack('<HH', addr, len(data))
        print(binascii.hexlify(hdr))
        send(ser, hdr)
        time.sleep(1)
        ack = ser.read(4)
        print(binascii.hexlify(ack))
        
        print(binascii.hexlify(data));
        send(ser, data)
        if ser.read(1)[0] != 0x00:
            raise Exception('Verification failed!')
        ser.close()
        print('Flash of {} bytes to {} succeeded!'.format(len(data), addr));
