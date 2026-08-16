; Push/pop register and immediate; swap via stack.
main:
	mov r0, #0x11
	mov r1, #0x22
	push r0
	push r1
	pop r0
	pop r1
	st $2000, r0		; 0x22
	st $2001, r1		; 0x11

	push #0xaa
	pop r0
	st $2002, r0		; 0xaa

	push #10
	push #20
	pop r1
	pop r0
	st $2003, r0		; 10
	st $2004, r1		; 20
	halt
