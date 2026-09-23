; SIM-002 PUSH (register, immediate) and POP (r0, r1, f). SP points to the
; next free byte: a push writes [SP] then SP+1, a pop is SP-1 then [SP].
main:
;@ sp=0100
	mov r0, #0xa1
	push r0
;@ sp=0101 m0100=a1
	push #0xb2
;@ sp=0102 m0101=b2
	mov r1, #0xc3
	push r1
;@ sp=0103 m0102=c3
	pop r0
;@ r0=c3 sp=0102
	pop r1
;@ r1=b2 sp=0101
	pop r0
;@ r0=a1 sp=0100
	push #0x03
	pop f
;@ z=1 i=1 sp=0100
	push #0x00
	pop f
;@ z=0 i=0
	push #0x02
	pop f
;@ z=0 i=1
	push #0x01
	pop f
;@ z=1 i=0
	halt
