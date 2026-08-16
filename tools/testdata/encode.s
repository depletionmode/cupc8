; Known encodings, main is first so they sit at $1003.
main:
	nop
	mov r0, #0x42
	mov r1, r0
	push r0
	pop r1
	eq r0, #1
	add r0, #1
	ld r0, $2000
	st $2000, r1
	b main
	bzf main
	halt
