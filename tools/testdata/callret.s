; Call/return via push pch/pcl + pop pcl/pch.
func:
	mov r0, #0x77
	mov r1, #0x88
	pop pcl
	pop pch

nested:
	push pch
	push pcl
	b func
	add r0, #1
	pop pcl
	pop pch

main:
	mov r0, #0
	mov r1, #0
	push pch
	push pcl
	b func
	st $2000, r0		; 0x77
	st $2001, r1		; 0x88

	push pch
	push pcl
	b nested
	st $2002, r0		; 0x78
	halt
