; hello- a small native CUPC/8 program for trying the loader and the API
; (doc/proposals/kernel-api.md). Prints a banner, the API version, a
; triangle of stars, then steps a light across the GPO LEDs ($f000) once a
; second, showing the same pattern on screen, until a key is pressed.
;
; Build (kernel/api.inc first, loaded at $7000, with the C8P header)-
;   python3 tools/mkprg.py examples/hello/hello.s -o build/HELLO.PRG
; Run- `exec "HELLO.PRG"` from the SD card, or cupc8.py run build/HELLO.PRG.

msg_hi db "\nHello from a native CUPC/8 program!\nAPI version "
msg_tri db "\n\n"
; line_a is CR and "LEDs [" as numbers: the assembler has no \r in strings
msg_leds db "\nThe LEDs step once a second. Press a key to stop.\n"
line_a db 13, 76, 69, 68, 115, 32, 91, 0
line_b db "]  seconds "
pat db 1, 2, 4, 8, 16, 32, 64, 128, 64, 32, 16, 8, 4, 2
msg_got db "\nYou pressed '"
msg_bye db "'. Back to the terminal.\n"

row: resb 1
col: resb 1
key: resb 1
idx: resb 1
bits: resb 1
nbit: resb 1
secs: resb 1
num: resb 1
dig: resb 1
waits: resb 1

main:
	mov r0, #<[msg_hi]
	mov r1, #>[msg_hi]
	push pch
	push pcl
	b puts

	; the API version as one digit
	push pch
	push pcl
	b API_VERSION
	add r0, #48
	push pch
	push pcl
	b API_PUTC

	mov r0, #<[msg_tri]
	mov r1, #>[msg_tri]
	push pch
	push pcl
	b puts

	; rows 1-8, each with that many stars
	mov r0, #1
	st [row], r0
.row:
	xor r0, r0
	st [col], r0
.star:
	mov r0, #42
	push pch
	push pcl
	b API_PUTC
	ld r0, [col]
	add r0, #1
	st [col], r0
	ld r1, [row]
	eq r0, r1
	bzf .row_done
	b .star
.row_done:
	mov r0, #10
	push pch
	push pcl
	b API_PUTC
	ld r0, [row]
	add r0, #1
	st [row], r0
	eq r0, #9
	bzf .ask
	b .row

.ask:
	mov r0, #<[msg_leds]
	mov r1, #>[msg_leds]
	push pch
	push pcl
	b puts
	xor r0, r0
	st [idx], r0
	st [secs], r0

.tick:
	; the pattern to the LEDs, and to the screen as * and .
	ld r0, [idx]
	ld r1, [pat]+r0
	st $f000, r1				; GPO
	st [bits], r1
	mov r0, #<[line_a]
	mov r1, #>[line_a]
	push pch
	push pcl
	b puts
	mov r0, #8
	st [nbit], r0
.bit:
	ld r0, [bits]
	gt r0, #127
	bzf .one
	mov r0, #46
	b .put
.one:
	mov r0, #42
.put:
	push pch
	push pcl
	b API_PUTC
	ld r0, [bits]
	shl r0, #1
	st [bits], r0
	ld r0, [nbit]
	sub r0, #1
	st [nbit], r0
	eq r0, #0
	bzf .bits_done
	b .bit
.bits_done:
	mov r0, #<[line_b]
	mov r1, #>[line_b]
	push pch
	push pcl
	b puts
	ld r0, [secs]
	push pch
	push pcl
	b print3

	; a second, as ten waits of 100 ms with a look at the keyboard after each
	mov r0, #10
	st [waits], r0
.wait:
	mov r0, #100
	xor r1, r1
	push pch
	push pcl
	b API_WAIT_MS
	push pch
	push pcl
	b API_POLLKEY
	eq r0, #255
	bzf .no_key
	b .stop
.no_key:
	ld r0, [waits]
	sub r0, #1
	st [waits], r0
	eq r0, #0
	bzf .next
	b .wait
.next:
	ld r0, [secs]
	add r0, #1
	st [secs], r0
	ld r0, [idx]
	add r0, #1
	st [idx], r0
	eq r0, #14
	bzf .wrap
	b .tick
.wrap:
	xor r0, r0
	st [idx], r0
	b .tick

.stop:
	st [key], r0
	xor r0, r0
	st $f000, r0				; LEDs off
	mov r0, #<[msg_got]
	mov r1, #>[msg_got]
	push pch
	push pcl
	b puts
	ld r0, [key]
	push pch
	push pcl
	b API_PUTC
	mov r0, #<[msg_bye]
	mov r1, #>[msg_bye]
	push pch
	push pcl
	b puts

	; return to the terminal (as API_EXIT would)
	pop pcl
	pop pch

; print the NUL-terminated string at r1 (high), r0 (low)
puts:
	st $6f00, r0			; API_ARGS
	st $6f01, r1
	push pch
	push pcl
	b API_PUTS
	pop pcl
	pop pch

; print r0 as three decimal digits
print3:
	st [num], r0
	mov r0, #48
	st [dig], r0
.hundreds:
	ld r0, [num]
	gt r0, #99
	bzf .sub100
	b .h_out
.sub100:
	sub r0, #100
	st [num], r0
	ld r0, [dig]
	add r0, #1
	st [dig], r0
	b .hundreds
.h_out:
	ld r0, [dig]
	push pch
	push pcl
	b API_PUTC
	mov r0, #48
	st [dig], r0
.tens:
	ld r0, [num]
	gt r0, #9
	bzf .sub10
	b .t_out
.sub10:
	sub r0, #10
	st [num], r0
	ld r0, [dig]
	add r0, #1
	st [dig], r0
	b .tens
.t_out:
	ld r0, [dig]
	push pch
	push pcl
	b API_PUTC
	ld r0, [num]
	add r0, #48
	push pch
	push pcl
	b API_PUTC
	pop pcl
	pop pch

