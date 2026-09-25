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

con_char: resb 1

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
con_putc:
	st [con_char], r0
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
