; ALU immediate + overflow/underflow. Results packed at $2000.
main:
	mov r0, #10
	add r0, #5
	st $2000, r0		; 15

	mov r1, #7
	add r0, r1
	st $2001, r0		; 22

	mov r0, #255
	add r0, #2
	st $2002, r0		; 1

	mov r0, #10
	sub r0, #3
	st $2003, r0		; 7

	mov r0, #1
	sub r0, #2
	st $2004, r0		; 255

	mov r0, #0xf0
	and r0, #0x3c
	st $2005, r0		; 0x30

	mov r0, #0x0f
	or r0, #0xf0
	st $2006, r0		; 0xff

	mov r0, #0xff
	xor r0, #0x0f
	st $2007, r0		; 0xf0

	mov r0, #0
	nor r0, #0
	st $2008, r0		; 0xff

	mov r0, #0x0f
	nor r0, #0xf0
	st $2009, r0		; 0

	mov r0, #1
	shl r0, #4
	st $200a, r0		; 16

	mov r0, #0x80
	shl r0, #1
	st $200b, r0		; 0

	mov r0, #0x80
	shr r0, #4
	st $200c, r0		; 8

	mov r0, #1
	shr r0, #1
	st $200d, r0		; 0

	mov r0, #0x55
	mov r1, r0
	nop
	st $200e, r1		; 0x55
	halt
