; WAI until keyboard IRQ, then read the char over SPI and store it.
main:
	mov r0, #<handler
	st $0010, r0
	mov r0, #>handler
	st $0011, r0
	mov r0, #1
	st $f201, r0
	sti
	wai
	mov r1, #2
	mov r0, #255
	st $f120, r0
	mov r0, #1
	st $f122, r0
	ld r0, $f121
	st $2000, r0
	halt

handler:
	push r0
	mov r0, #1
	st $f200, r0
	pop r0
	pop f
	pop pcl
	pop pch
