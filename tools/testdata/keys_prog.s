; SIM-014: a program for $7000 that prints the byte API_GETKEY gives for each
; key as <hh> (two hex digits), and ends at q. test/sim/test_cli.py types the
; keys with no character (arrows, Home, End, PgUp, PgDn, Insert, Delete,
; F1-F12) at it with --type, tools/simtest.nim by their HID usages.

key db 0

main:
	push pch
	push pcl
	b API_GETKEY
	st [key], r0
	eq r0, #113			; q
	bzf .end
	mov r0, #60			; <
	push pch
	push pcl
	b API_PUTC
	ld r0, [key]
	shr r0, #4
	push pch
	push pcl
	b hexdigit
	ld r0, [key]
	and r0, #15
	push pch
	push pcl
	b hexdigit
	mov r0, #62			; >
	push pch
	push pcl
	b API_PUTC
	b main
.end:
	pop pcl
	pop pch

; print the hex digit r0 (0-15)
hexdigit:
	lt r0, #10
	bzf .num
	add r0, #7			; A-F
.num:
	add r0, #48
	b API_PUTC			; it returns to our caller
