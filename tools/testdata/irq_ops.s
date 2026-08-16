; Encodings sit at $1003. cli/sti/pop f/wai, then tmr0 #3, tmr1 r0.
main:
	cli
	sti
	pop f
	wai
	tmr0 #3
	tmr1 r0
	halt
