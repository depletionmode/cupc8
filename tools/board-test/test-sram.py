# MicroPython script to test sram chip

import pyb

# pins Y1-8 - data
# pins X1-12,17-20 - address
# pin X22 - !we

WRITE_DELAY_MS = 1

# flash red led on error
def err():
	print("[!] err")
	led = pyb.LED(1)
	while True:
		led.toggle()
		pyb.delay(200)


def __read_pin(prefix, number):
	pin = pyb.Pin('{}{}'.format(prefix, number), pyb.Pin.IN, pyb.Pin.PULL_UP)
	return pin.value()

def __write_pin(prefix, number, val_bit):
	pin = pyb.Pin('{}{}'.format(prefix, number), pyb.Pin.OUT_PP)
	if val_bit & 1 == 1: pin.high()
	else: pin.low()

# write byte to address
def __write(addr, val):
	for i in range(1,9):
		__write_pin('Y', i, val >> (i-1))

	for i in range(1,13):
		__write_pin('X', i, addr >> (i-1))

	for i in range(17,21):
		__write_pin('X', i, addr >> 12 >> (i-1))

	__write_pin('X', 22, 0)
	pyb.delay(WRITE_DELAY_MS)
	__write_pin('X', 22, 1)

# read byte from address
def __read(addr):
	for i in range(1,13):
		__write_pin('X', i, addr >> (i-1))

	for i in range(17,21):
		__write_pin('X', i, addr >> 12 >> (i-1))

	# in theory we need to wait >55ns here but not adding delay as hopefully MicroPython is slow enough...

	val = 0

	for i in range(1,8):
		val |= __read_pin('Y', i) << (i-1)

	return val

def __test_data_bus():
	print("[+] Data bus")
	led = pyb.LED(2)
	led.on()

	for i in range(8):
		__write(i, 1 << i)

	for i in range(8):
		if __read(i) != 1 << i: err()

	led.off()

def __test_address_bus():
	print("[+] Address bus")
	led = pyb.LED(3)
	led.on()

	for i in range(16):
		__write(1 << i, i)

	for i in range(16):
		if __read(1 << i) != i: err()

	led.off()

def __test_Xk(num_bytes):
	print("[+] {}K test".format(num_bytes))
	led = pyb.LED(4)
	led.on()

	for i in range(num_bytes*1024):
		__write(i, i % 256)

	for i in range(num_bytes*1024):
		if __read(i) != i % 256: err()

	led.off()

# run tests
print("Testing SRAM...")
__test_data_bus()
__test_address_bus()
__test_Xk(1)

