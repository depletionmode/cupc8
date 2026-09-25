; SIM-010's pacing load: timer 0 wakes the CPU from WAI every 50
; instructions, for ever. The interactive simulator must still run at about
; 1 MHz (guest time level with the host clock), not a millisecond's sleep
; per WAI. Its own handler, so it does not depend on the kernel's timers.

main:
	mov r0, #<tick
	st $0012, r0
	mov r0, #>tick
	st $0013, r0
	ld r0, $f201
	mov r1, #2
	or r0, r1
	st $f201, r0
	tmr0 #50
	sti
.sleep:
	wai
	b .sleep

tick:
	push r0
	tmr0 #50
	mov r0, #2
	st $f200, r0
	pop r0
	pop f
	pop pcl
	pop pch
