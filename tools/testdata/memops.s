; Direct and indexed load/store.
main:
	mov r0, #0xab
	st $2100, r0
	xor r0, r0
	ld r0, $2100
	st $2000, r0		; 0xab

	mov r0, #5
	mov r1, #0xcd
	st $2100+r0, r1
	xor r1, r1
	ld r1, $2100+r0
	st $2001, r1		; 0xcd

	; confirm raw address
	ld r0, $2105
	st $2002, r0		; 0xcd

	mov r0, #0x12
	st $21ff, r0
	ld r1, $21ff
	st $2003, r1		; 0x12
	halt
