; ALU does not clear ZF. After a true EQ, ADD must leave ZF set.
main:
	mov r0, #1
	eq r0, #1
	add r0, #1
	bzf still
	mov r0, #0xee
	st $2000, r0
	halt
still:
	mov r0, #0xaa
	st $2000, r0
	halt
