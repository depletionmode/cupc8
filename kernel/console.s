; The USB console (doc/proposals/usb-console.md): the terminal's text also
; goes to CON_OUT, and keys come from CON_IN as well as the IO card. The
; system card moves both rings to and from a PC while its console port is
; open, and sets HOST in CON_FLAGS then. Each side writes only its own index,
; after the data: the kernel CON_OUT_HEAD and CON_IN_TAIL, the card the
; other two. Without a system card nothing reads the rings, HOST stays clear
; and the output is simply dropped when the ring is full.

%define CON_OUT_HEAD $6f22
%define CON_OUT_TAIL $6f23
%define CON_IN_HEAD $6f24
%define CON_IN_TAIL $6f25
%define CON_FLAGS $6f26
%define CON_OUT $6f40
%define CON_IN $6fc0

; boot: RAM is junk at power-on. Zero the four indices and CON_FLAGS; the
; card sets HOST again on its next poll if a PC has the port open.
con_init:
	xor r0, r0
	st CON_OUT_HEAD, r0
	st CON_OUT_TAIL, r0
	st CON_IN_HEAD, r0
	st CON_IN_TAIL, r0
	st CON_FLAGS, r0
	pop pcl
	pop pch

; put the character in r0 into CON_OUT (r0 kept). A full ring: with HOST set
; the card is draining it (every 2 ms), so wait; without, drop the character.
; A PC that keeps the port open but stops reading must not hold the terminal:
; a ring full for 500 ms (MS_COUNT in 4 ms steps, so 496-504) marks the PC
; stuck (con_stuck = CON_OUT_TAIL | $80) and the character is dropped, as are
; the next ones while the tail stays there; once the PC reads (the tail
; moves) the kernel waits again.
con_char: resb 1
con_waited: resb 1			; this character has started a wait
con_t: resb 1				; ... at this time, in 4 ms steps
con_stuck: resb 1			; 0, or the stuck tail | $80

con_putc:
	st [con_char], r0
	xor r0, r0
	st [con_waited], r0
.again:
	ld r0, CON_OUT_HEAD
	add r0, #1
	and r0, #0x7f
	ld r1, CON_OUT_TAIL
	and r1, #0x7f
	eq r0, r1
	bzf .full
	ld r1, CON_OUT_HEAD
	and r1, #0x7f
	ld r0, [con_char]
	st CON_OUT+r1, r0			; the byte first,
	add r1, #1
	and r1, #0x7f
	st CON_OUT_HEAD, r1			; then the index that covers it
.done:
	ld r0, [con_char]
	pop pcl
	pop pch
.full:
	ld r0, CON_FLAGS
	and r0, #1
	eq r0, #0
	bzf .done				; no PC reading, drop it
	ld r0, CON_OUT_TAIL
	or r0, #0x80
	ld r1, [con_stuck]
	eq r0, r1
	bzf .done				; stuck and still not reading, drop it
	xor r0, r0
	st [con_stuck], r0			; (it read since, so wait again)
	ld r0, $f206				; r0 = now in 4 ms steps (MS_COUNT0 first,
	shr r0, #2				; it latches MS_COUNT1)
	mov r1, r0
	ld r0, $f207
	shl r0, #6
	or r0, r1
	ld r1, [con_waited]
	eq r1, #0
	bzf .start
	ld r1, [con_t]
	sub r0, r1
	lt r0, #125
	bzf .again				; under 500 ms, keep waiting
	ld r0, CON_OUT_TAIL
	or r0, #0x80
	st [con_stuck], r0
	b .done
.start:
	st [con_t], r0
	mov r0, #1
	st [con_waited], r0
	b .again

; r0 = the next key from CON_IN, or $ff if none (a $ff byte from the PC is
; dropped, as it would read as "no key")
con_getc:
	ld r0, CON_IN_TAIL
	and r0, #0x3f
	ld r1, CON_IN_HEAD
	and r1, #0x3f
	eq r0, r1
	bzf .none
	ld r1, CON_IN+r0
	add r0, #1
	and r0, #0x3f
	st CON_IN_TAIL, r0			; the byte is ours, the card may reuse its slot
	mov r0, r1
	pop pcl
	pop pch
.none:
	mov r0, #0xff
	pop pcl
	pop pch
