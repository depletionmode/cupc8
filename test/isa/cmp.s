; SIM-002 EQ GT LT, register (all Ra/Rb) and immediate. Z = the comparison,
; unsigned; ALU operations leave Z alone.
main:
	mov r0, #5
	mov r1, #5
	eq r0, r1
;@ z=1
	add r0, #1
;@ r0=06 z=1
	eq r0, r1
;@ z=0
	gt r0, r1
;@ z=1
	gt r1, r0
;@ z=0
	lt r1, r0
;@ z=1
	lt r0, r1
;@ z=0
	eq r1, r1
;@ z=1
	gt r0, r0
;@ z=0
	eq r0, r0
	lt r1, r1
;@ z=0
	eq r0, #6
;@ z=1
	eq r1, #6
;@ z=0
	lt r0, #0xff
;@ z=1
	gt r0, #0xff
;@ z=0
	mov r1, #0x80
	gt r1, #0x7f
;@ z=1
	lt r1, #0x7f
;@ z=0
	gt r1, #0x80
	nop
;@ z=0
	lt r1, #0x81
;@ z=1
	sub r1, #1
	and r1, #0
;@ r1=00 z=1
	halt
