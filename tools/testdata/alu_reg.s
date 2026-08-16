; ALU register-register forms. Results at $2000.
main:
	mov r0, #20
	mov r1, #30
	xor r0, r1
	st $2000, r0		; 10

	mov r0, #0xaa
	mov r1, #0x0f
	and r0, r1
	st $2001, r0		; 0x0a

	mov r0, #0xa0
	mov r1, #0x0b
	or r0, r1
	st $2002, r0		; 0xab

	mov r0, #50
	mov r1, #8
	sub r0, r1
	st $2003, r0		; 42

	mov r0, #3
	mov r1, #5
	add r0, r1
	st $2004, r0		; 8

	mov r0, #1
	mov r1, #3
	shl r0, r1
	st $2005, r0		; 8

	mov r0, #0x40
	mov r1, #2
	shr r0, r1
	st $2006, r0		; 0x10

	mov r0, #0x0f
	mov r1, #0xf0
	nor r0, r1
	st $2007, r0		; 0

	mov r0, #0x12
	mov r1, #0x12
	xor r0, r1
	st $2008, r0		; 0

	halt
