; Timer 0 falls due as POP pcl retires. The IRQ must wait for the POP pch
; after it: taken between the two, its frame would go over the popped byte
; and the handler's POP pcl would replace pcl, so the return would go astray.
main:
	mov r0, #<handler
	st $0012, r0
	mov r0, #>handler
	st $0013, r0
	mov r0, #2
	st $f201, r0
	sti
	tmr0 #5
	push pch
	push pcl
	b func
	mov r0, #0x55
	st $2000, r0
	halt

func:
	pop pcl
	pop pch

handler:
	mov r0, #2
	st $f200, r0
	mov r0, #0x11
	st $2001, r0
	pop f
	pop pcl
	pop pch
