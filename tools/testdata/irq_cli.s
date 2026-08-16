; CLI must leave the timer pending and not take the vector.
main:
	mov r0, #<handler
	st $0012, r0
	mov r0, #>handler
	st $0013, r0
	mov r0, #2
	st $f201, r0
	cli
	tmr0 #1
	ld r0, $f200
	st $2000, r0
	halt

handler:
	mov r0, #0xee
	st $2000, r0
	halt
