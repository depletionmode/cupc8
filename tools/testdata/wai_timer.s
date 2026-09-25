; Timer 0 armed with 200, then WAI: parked, the CPU counts the timer every
; 3 clocks (cpu.vhd: tick, settle, check), 4 counts a microsecond, so the
; handler runs 50 of the sim's microsecond steps later, not 200.
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
