; Double-indirect LDD/STD through a pointer at $2200.
main:
	mov r0, #0x00
	st $2200, r0
	mov r0, #0x21
	st $2201, r0		; pointer to $2100

	mov r0, #0xcd
	std $2200, r0
	xor r0, r0
	ldd r0, $2200
	st $2000, r0		; 0xcd
	ld r1, $2100
	st $2001, r1		; 0xcd

	; indexed: pointer is at $2200 + r1, r1=0
	mov r1, #0
	mov r0, #0x5a
	std $2200+r1, r0
	xor r0, r0
	ldd r0, $2200+r1
	st $2002, r0		; 0x5a
	halt
