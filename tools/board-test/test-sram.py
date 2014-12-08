# MicroPython script to test sram chip

import pyb

# pins Y1-8 - data
# pins X1-12,Y9-12 - address
# pin X22 - !we

# flash red led on error
def err():
        print("[!] err")
        led = pyb.LED(1)
        while True:
                led.toggle()
                pyb.delay(200)


def __read_pin(prefix, number):
        pin = pyb.Pin('{}{}'.format(prefix, number), pyb.Pin.IN, pyb.Pin.PULL_UP)
        #print("[-] read pin {}{}: {})".format(prefix, number, pin.value()))
        return pin.value()

def __write_pin(prefix, number, val_bit):
        #print("[-] write pin {}{}: {})".format(prefix, number, val_bit))
        pin = pyb.Pin('{}{}'.format(prefix, number), pyb.Pin.OUT_PP)
        if val_bit & 1 == 1: pin.high()
        else: pin.low()

# write byte to address
def __write(addr, val):
        for i in range(1,9):
                __write_pin('Y', i, val >> (i-1))

        for i in range(1,13):
                __write_pin('X', i, addr >> (i-1))

        for i in range(9,13):
                __write_pin('Y', i, (addr >> 12) >> (i-9))

        __write_pin('X', 22, 0)
#       pyb.delay(1)  # interpreter is slow so time low >55ns
        __write_pin('X', 22, 1)

# read byte from address
def __read(addr):
        for i in range(1,13):
                __write_pin('X', i, addr >> (i-1))

        for i in range(9,13):
                __write_pin('Y', i, (addr >> 12) >> (i-9))

        val = 0

        for i in range(1,9):
                val |= __read_pin('Y', i) << (i-1)

        return val

def __test_data_bus():
        print("[+] Data bus")
        led = pyb.LED(2)
        led.on()

        err_ = False

        for i in range(1,9):
                __write(i, 1 << i-1)

        for i in range(1,9):
                if __read(i) != 1 << i-1: print(" -> Issue with data pin {}!".format(i)); err_ = True;

        if err_: err()

        print(" -> OK")

def __test_address_bus():
        print("[+] Address bus")
        led = pyb.LED(3)
        led.on()

        err_ = False

        for i in range(16):
                __write(1 << i, i)

        for i in range(16):
                if __read(1 << i) != i: print(" -> Issue with address pin {}!".format(i)); err_ = True;

        if err_: err()

        print(" -> OK")

def __test_Xk(num_bytes):
        print("[+] {}K test".format(num_bytes))

        num_bytes*=1024

        led = pyb.LED(4)
        led.on()

        for i in range(num_bytes):
                __write(i, i % 256)

        for i in range(num_bytes):
                if __read(i) != i % 256: err()

        print(" -> OK")

def __test_xmega():
        print("[+] XMEGA")

        led = pyb.LED(4)
        led.on()

        for i in range(16):
#            print(__read(1<<i))
            if __read(1<<i) != i: err()

        print(" -> OK")

# run tests
print("Testing SRAM...")
pyb.delay(3000)
__test_xmega()
__test_data_bus()
__test_address_bus()
#__test_Xk(64)
print("DONE!")

while True:
    pyb.delay(60)
    pyb.LED(2).toggle()
    pyb.delay(60)
    pyb.LED(3).toggle()
    pyb.delay(60)
    pyb.LED(4).toggle()
