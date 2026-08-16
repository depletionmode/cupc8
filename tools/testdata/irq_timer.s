; Timer 0 interrupt writes $aa to $2000. Must not fall through to $ee.
main:
	mov r0, #<handler
	st $0012, r0
	mov r0, #>handler
	st $0013, r0
	mov r0, #2
	st $f201, r0
	sti
	tmr0 #2
	wai
	mov r0, #0xee
	st $2000, r0
	halt

handler:
	mov r0, #0xaa
	st $2000, r0
	halt
