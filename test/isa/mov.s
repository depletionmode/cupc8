; SIM-002 MOV: every Ra/Rb combination and both formats (manual 3.4)
main:
;@ r0=00 r1=00 sp=0100 z=0 i=0
	mov r0, #0x12
	mov r1, #0x34
;@ r0=12 r1=34
	mov r0, r1
;@ r0=34 r1=34
	mov r1, #0x56
	mov r1, r0
;@ r0=34 r1=34
	mov r0, #0x78
	mov r0, r0
	mov r1, r1
;@ r0=78 r1=34
	mov r1, #255
	nop
;@ r0=78 r1=ff z=0
	halt
