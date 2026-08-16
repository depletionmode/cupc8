; tiny program: write 0x42 to $2000 via r0, then halt
main:
	mov r0, #0x42
	st $2000, r0
	halt
