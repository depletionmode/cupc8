; KRN-011: API_EXIT from deep inside a program, with bytes left on the
; stack: the terminal takes over with its stack as it was.

main:
	push #1
	push #2
	push #3
	push pch
	push pcl
	b deeper
	halt

deeper:
	push #4
	mov r0, #0x5a
	st $be00, r0
	push pch
	push pcl
	b API_EXIT
	mov r0, #0xee			; never
	st $be00, r0
	halt
