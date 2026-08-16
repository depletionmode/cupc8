; .bss and .data via [name] / [name+off].
val: resb 1
pair: resb 2

msg db 65, 66, 67

main:
	mov r0, #0x42
	st [val], r0
	xor r0, r0
	ld r0, [val]
	st $2000, r0		; 0x42

	mov r0, #0x11
	st [pair], r0
	mov r0, #0x22
	st [pair+1], r0
	ld r1, [pair]
	st $2001, r1		; 0x11
	ld r1, [pair+1]
	st $2002, r1		; 0x22

	ld r0, [msg]
	st $2003, r0		; 'A'
	ld r0, [msg+1]
	st $2004, r0		; 'B'
	ld r0, [msg+2]
	st $2005, r0		; 'C'
	halt
