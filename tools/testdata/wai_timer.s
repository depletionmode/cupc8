; Timer 0 armed with 200, then WAI: parked, the CPU counts the timer once a
; turn of 3 clocks (cpu.vhd: tick, settle, check), 4 counts a microsecond,
; so the handler runs 198 turns (TMR0 and WAI count it as they retire),
; 594 clocks, 49.5 us later.
main:
	mov r0, #<handler
	st $0012, r0
	mov r0, #>handler
	st $0013, r0
	mov r0, #2
	st $f201, r0
	sti
	tmr0 #200
	wai
	mov r0, #0x55
	st $2000, r0
	halt

handler:
	mov r0, #2
	st $f200, r0
	pop f
	pop pcl
	pop pch
