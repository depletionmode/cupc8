; #< / #> split a 16-bit address into bytes, then STD through it.
main:
	mov r0, #<$2300
	st $2200, r0
	mov r0, #>$2300
	st $2201, r0
	mov r0, #0x99
	std $2200, r0
	ld r1, $2300
	st $2000, r1		; 0x99
	ldd r0, $2200
	st $2001, r0		; 0x99
	halt
