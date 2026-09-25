; Keyboard driver: the IO card (doc/hardware/io-card.md).
;
; The card holds a FIFO of keys and pulls IRQ_n low while it is not empty, so
; the kernel sleeps in WAI instead of spinning. Keys are ASCII, with $ff
; meaning "nothing waiting". The wait polls the card whenever its line is
; asserted (SLOT_IRQ, $f202, the live level), so a key is never missed
; between a poll and the WAI; the chipset's tick (irq.s) wakes the WAI
; every 50 ms, which bounds that.

%define SLOT_TABLE $0002
%define KEYB_CFG_DIV2 16

keyb_spi: resb 1
keyb_tmp: resb 1
keyb_try: resb 1
keyb_bit: resb 1			; the keyboard's bit in SLOT_IRQ
keyb_term: resb 1			; 1 while the terminal waits for a line (API_RUN is looked at)

keyb_init:
	mov r0, #0xff
	st [keyb_spi], r0
	xor r0, r0
	st [keyb_tmp], r0
	st [keyb_bit], r0
	st [keyb_term], r0
.scan:
	ld r0, [keyb_tmp]
	ld r1, SLOT_TABLE+r0
	eq r1, #2				; card type 2 is the IO card
	bzf .found
	ld r0, [keyb_tmp]
	add r0, #1
	st [keyb_tmp], r0
	lt r0, #6
	bzf .scan
	b .done					; no keyboard fitted
.found:
	ld r1, [keyb_tmp]
	mov r0, #1
	shl r0, r1
	st [keyb_bit], r0
	ld r0, [keyb_tmp]
	shl r0, #4
	st [keyb_spi], r0
	mov r1, #KEYB_CFG_DIV2
	st $f10f+r0, r1

	; let the card raise IRQ_n while it has keys
	push pch
	push pcl
	b keyb_cs_on
	mov r0, #0xf2			; IRQ_EN
	push pch
	push pcl
	b keyb_send
	mov r0, #1
	push pch
	push pcl
	b keyb_send
	push pch
	push pcl
	b keyb_cs_off
.done:
	pop pcl
	pop pch

keyb_send:
	st [keyb_tmp], r0
	ld r0, [keyb_spi]
	ld r1, [keyb_tmp]
	st $f100+r0, r1
	mov r1, #1
	st $f102+r0, r1
.spi_wait:					; SPI_RX is only valid once SPI_STAT says done
	ld r1, $f103+r0
	eq r1, #0
	bzf .spi_wait
	ld r1, $f101+r0
	st [keyb_tmp], r1
	ld r0, [keyb_tmp]
	pop pcl
	pop pch

keyb_cs_on:
	ld r0, [keyb_spi]
	mov r1, #1
	st $f104+r0, r1
	pop pcl
	pop pch

keyb_cs_off:
	ld r0, [keyb_spi]
	mov r1, #0
	st $f104+r0, r1
	pop pcl
	pop pch

; r0 = the next key, or $ff when the FIFO is empty
keyb_poll:
	ld r0, [keyb_spi]
	eq r0, #0xff
	bzf .none

	push pch				; GETKEY
	push pcl
	b keyb_cs_on
	mov r0, #0x00
	push pch
	push pcl
	b keyb_send
	push pch
	push pcl
	b keyb_cs_off

	mov r0, #0				; READ tries so far
	st [keyb_try], r0
.read:
	push pch				; READ frame - status, RESP_LEN, then the key
	push pcl
	b keyb_cs_on
	mov r0, #0xfe
	push pch
	push pcl
	b keyb_send
	mov r0, #0
	push pch
	push pcl
	b keyb_send
	eq r0, #0				; RESP_LEN $00 - not ready yet, end the frame and retry (slot.md)
	bzf .not_ready
	mov r0, #0
	push pch
	push pcl
	b keyb_send
	st [keyb_tmp], r0
	push pch
	push pcl
	b keyb_cs_off
	ld r0, [keyb_tmp]
	b .done
.not_ready:
	push pch
	push pcl
	b keyb_cs_off
	ld r0, [keyb_try]
	add r0, #1
	st [keyb_try], r0
	eq r0, #0				; 256 tries (well past the card's 5 ms) - give up, no key
	bzf .none
	b .read
.none:
	mov r0, #0xff
.done:
	pop pcl
	pop pch

; wait for a key and return it in r0. While the terminal waits (keyb_term),
; a program the PC left at $7000 (API_RUN = 1) is run instead: sys_run,
; which never comes back here (sys_restart takes the terminal back).
keyb_read_char:
	push pch
	push pcl
	b keyb_poll
	eq r0, #0xff
	bzf .wait
	b .done
.wait:
	; sleep until an IRQ - the IO card's while it has keys, or the tick
	wai
	ld r0, [keyb_term]
	eq r0, #0
	bzf .key
	ld r0, API_RUN
	eq r0, #1
	bzf .run
	b .key
.run:
	b sys_run
.key:
	ld r0, $f202			; the keyboard's line, live
	ld r1, [keyb_bit]
	and r0, r1
	eq r0, #0
	bzf .wait
	b keyb_read_char
.done:
	pop pcl
	pop pch
