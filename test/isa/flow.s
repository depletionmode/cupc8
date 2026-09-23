; SIM-002 B, BZF taken and not taken, and a call/return through PUSH pch/pcl
; and POP pcl/pch (manual 3.4, "Special register operands").
main:
	mov r0, #0
	b skip1
	mov r0, #0xee
skip1:
;@ r0=00
	eq r0, #1
	bzf skip2
	mov r0, #0x11
skip2:
;@ r0=11
	eq r0, #0x11
	bzf skip3
	mov r0, #0x22
skip3:
;@ r0=11
	push pch
	push pcl
	b sub1
ret1:
;@ r0=33 sp=0100
	halt
sub1:
;@ sp=0102 m0100=hi(ret1) m0101=lo(ret1)
	mov r0, #0x33
	pop pcl
	pop pch
