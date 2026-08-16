; Unconditional branch skips the fail store.
main:
	b skip
	mov r0, #0xee
	st $2000, r0
	halt
skip:
	mov r0, #0xaa
	st $2000, r0
	; ZF clear: bzf must not take
	mov r1, #1
	eq r1, #2
	bzf bad
	mov r1, #0x11
	st $2001, r1
	halt
bad:
	mov r1, #0xee
	st $2001, r1
	halt
