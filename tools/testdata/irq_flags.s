; IRET restores Z. Handler clears Z; return must still take BZF.
main:
	mov r0, #<handler
	st $0012, r0
	mov r0, #>handler
	st $0013, r0
	mov r0, #2
	st $f201, r0
	eq r0, r0
	sti
	tmr0 #1
	bzf .ok
	mov r0, #0xee
	st $2000, r0
	halt
.ok:
	mov r0, #0xaa
	st $2000, r0
	halt

handler:
	push r0
	mov r0, #2
	st $f200, r0
	pop r0
	mov r0, #1
	eq r0, #0
	pop f
	pop pcl
	pop pch
