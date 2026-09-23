; SIM-002 CLI STI, WAI with I=0 (a NOP), TMR0/TMR1 set and stopped, NOP.
main:
;@ i=0
	sti
;@ i=1
	cli
;@ i=0
	wai
	nop
;@ r0=00 r1=00 i=0
	mov r0, #5
	tmr0 r0
	tmr1 #200
	tmr0 #0
	tmr1 #0
;@ r0=05 i=0
	halt
