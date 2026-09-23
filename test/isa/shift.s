; SIM-002 SHL/SHR, register and immediate. Results are 8 bits: bits shifted
; out are lost, and a count of 8 or more gives 0.
main:
	mov r0, #0x81
	shl r0, #1
;@ r0=02
	shr r0, #1
;@ r0=01
	mov r1, #3
	shl r0, r1
;@ r0=08 r1=03
	shr r0, r1
;@ r0=01
	mov r0, #0xff
	shl r0, #0
;@ r0=ff
	shr r0, #7
;@ r0=01
	mov r0, #0xff
	shl r0, #8
;@ r0=00
	mov r0, #0xff
	shr r0, #9
;@ r0=00
	mov r1, #255
	mov r0, #1
	shl r0, r1
;@ r0=00 r1=ff
	mov r1, #0x40
	shr r1, r1
;@ r1=00
	mov r1, #2
	shl r1, r1
;@ r1=08
	mov r0, #0x80
	mov r1, #7
	shr r0, r1
;@ r0=01
	shl r1, r0
;@ r1=0e
	halt
