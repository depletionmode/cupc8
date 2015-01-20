#!/usr/bin/env python3

import serial
import os

device='/dev/ttyUSB0'
if len(os.argv) > 2):
	device = os.argv[2]

s = serial.Serial(port=device, baudrate=9600)

s.open()

if s.isOpen():
	print('[+] serial device {} opened'.format(device))

	binfile = os.argv[1]

	data = ''
	with open(binfile, 'rb') as f:
		data = f.read()

	print('[+] read {} bytes from {}'.format(len(data), binfile))

	size = len(data)
	offset = 0x1000

	print('[-] writing to RAM...')
	s.write('=')	# write to ram
	s.write(size >> 8 & 0xff)
	s.write(size & 0xff)
	s.write(offset >> 8 & 0xff)
	s.write(offset & 0xff)
	for d in data:
		print('.', end='')
		s.write(d)
	print('[+] write done')

	print('[-] verifying...')
	s.write('+')	# write to ram
	s.write(size >> 8 & 0xff)
	s.write(size & 0xff)
	s.write(offset >> 8 & 0xff)
	s.write(offset & 0xff)
	for d in data:
		print('.', end='')
		if d != s.read():
			print('[!]' verification failed)
	print('[+] verification passed')

	s.close()
else:
	print('[!]' failed to open serial device {}'.format(device))
