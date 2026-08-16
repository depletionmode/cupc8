; GPO is the store at $f000.
main:
	mov r0, #0xa5
	st $f000, r0
	ld r1, $f000
	st $2000, r1
	halt
