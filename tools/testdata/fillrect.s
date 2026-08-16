; 2x1 white rectangle at (10,20) through the real ili9340 SPI path
main:
	; CASET
	xor r0, r0
	st $f000, r0
	mov r0, #0x2a
	st $f100, r0
	mov r0, #1
	st $f102, r0
	mov r0, #1
	st $f000, r0
	xor r0, r0
	st $f100, r0
	mov r0, #1
	st $f102, r0
	mov r0, #10
	st $f100, r0
	mov r0, #1
	st $f102, r0
	xor r0, r0
	st $f100, r0
	mov r0, #1
	st $f102, r0
	mov r0, #12
	st $f100, r0
	mov r0, #1
	st $f102, r0

	; PASET
	xor r0, r0
	st $f000, r0
	mov r0, #0x2b
	st $f100, r0
	mov r0, #1
	st $f102, r0
	mov r0, #1
	st $f000, r0
	xor r0, r0
	st $f100, r0
	mov r0, #1
	st $f102, r0
	mov r0, #20
	st $f100, r0
	mov r0, #1
	st $f102, r0
	xor r0, r0
	st $f100, r0
	mov r0, #1
	st $f102, r0
	mov r0, #21
	st $f100, r0
	mov r0, #1
	st $f102, r0

	; RAMWR + two RGB565 white pixels
	xor r0, r0
	st $f000, r0
	mov r0, #0x2c
	st $f100, r0
	mov r0, #1
	st $f102, r0
	mov r0, #1
	st $f000, r0
	mov r0, #0xff
	st $f100, r0
	mov r0, #1
	st $f102, r0
	mov r0, #0xff
	st $f100, r0
	mov r0, #1
	st $f102, r0
	mov r0, #0xff
	st $f100, r0
	mov r0, #1
	st $f102, r0
	mov r0, #0xff
	st $f100, r0
	mov r0, #1
	st $f102, r0
	halt
