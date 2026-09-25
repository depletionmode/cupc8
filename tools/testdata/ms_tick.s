; SIM-013: the chipset's millisecond counter and tick (memory-map.md) in
; sim.nim. Parked in WAI with only the tick unmasked; its handler (the SPI
; vector, CPU line 3) keeps IRQ_PEND and the counter, and after the second
; tick the program halts.
main:
	mov r0, #<handler
	st $0016, r0
	mov r0, #>handler
	st $0017, r0
	ld r0, $f206
	st $2000, r0
	ld r0, $f207
	st $2001, r0
	mov r0, #0x10
	st $f201, r0
	sti
.loop:
	wai
	ld r0, $2005
	eq r0, #2
	bzf .done
	b .loop
.done:
	halt

handler:
	push r0
	ld r0, $f200
	st $2004, r0
	mov r0, #0x18
	st $f200, r0
	ld r0, $f206
	st $2002, r0
	ld r0, $f207
	st $2003, r0
	ld r0, $2005
	add r0, #1
	st $2005, r0
	pop r0
	pop f
	pop pcl
	pop pch
