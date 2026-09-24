; CUPC/8 boot ROM (doc/hardware/memory-map.md, "Boot chain").
;
; Assembled to $e000 and stored at ROM offset $00000, so it runs in place from
; the fixed window after reset (the image begins with `b main`). It tests RAM,
; probes the slots, prints a banner on a graphics card if one is fitted, then
; copies the kernel out of the ROM into RAM and jumps to it.
;
; POST codes go to the GPO LEDs; a failure halts with an error code.
;
; Registers are scarce (r0, r1), so all state is in RAM at $0f00-$0f1f - the
; top of the stack region, which the boot ROM's own stack never reaches. The
; RAM test therefore covers $0100-$0eff and $1000-$dfff.
;
; Build - tools/as.py rom/boot.s boot.bin 0xe000,0xe600,0x0f00

; Boot variables (a trailing comment would become part of the value, so the
; layout is documented here) -
;   $0f00 V_PTR   2  RAM test cursor        $0f0e V_SUM   running checksum
;   $0f02 V_END   2  RAM test end           $0f0f V_SPI   current SPI offset
;   $0f04 V_START 2  RAM test start         $0f10 V_CON   console SPI offset
;   $0f06 V_SRC   2  ROM / string pointer    $0f11 V_DEV  slot being probed
;   $0f08 V_DST   2  RAM write pointer      $0f12 V_CHAR  character for putc
;   $0f0a V_LEN   2  bytes left to copy     $0f13 V_TMP
;   $0f0c V_ENTRY 2  kernel entry           $0f14 V_TYPE  card type from IDENT
;                                           $0f15 V_TRY   READ retries left

%define GPO $f000
%define ROM_BANK $f204
%define SLOT_TABLE $0002

%define V_PTR $0f00
%define V_PTR_H $0f01
%define V_END $0f02
%define V_END_H $0f03
%define V_START $0f04
%define V_START_H $0f05
%define V_SRC $0f06
%define V_SRC_H $0f07
%define V_DST $0f08
%define V_DST_H $0f09
%define V_LEN $0f0a
%define V_LEN_H $0f0b
%define V_ENTRY $0f0c
%define V_ENTRY_H $0f0d
%define V_SUM $0f0e
%define V_SPI $0f0f
%define V_CON $0f10
%define V_DEV $0f11
%define V_CHAR $0f12
%define V_TMP $0f13
%define V_TYPE $0f14
%define V_TRY $0f15

; strings (defined before use - the assembler resolves data symbols in pass 1)
msg_banner db "CUPC/8 boot\n"
msg_nokernel db "no kernel in ROM\n"
msg_toobig db "kernel too large\n"
msg_badsum db "kernel checksum bad\n"

main:
	mov r0, #0x01
	st GPO, r0

; --------------------------------------------------------------- POST $02 RAM
	mov r0, #0x02
	st GPO, r0

	; The stack page is tested first, with no subroutine calls - a call here
	; would put a return address in the very bytes under test.
	mov r1, #0x55
	b page_pattern_inline
page_after_55:
	mov r1, #0xaa
	b page_pattern_inline
page_after_aa:

	; the rest of RAM, address-in-address at stride 16 (calls are safe now,
	; the stack page is below both ranges)
	mov r0, #<$0200
	st V_START, r0
	mov r0, #>$0200
	st V_START_H, r0
	mov r0, #<$0f00
	st V_END, r0
	mov r0, #>$0f00
	st V_END_H, r0
	push pch
	push pcl
	b ram_range

	mov r0, #<$1000
	st V_START, r0
	mov r0, #>$1000
	st V_START_H, r0
	mov r0, #<$e000
	st V_END, r0
	mov r0, #>$e000
	st V_END_H, r0
	push pch
	push pcl
	b ram_range

; ------------------------------------------------------------- POST $04 slots
	mov r0, #0x04
	st GPO, r0

	mov r0, #0xff
	st V_CON, r0
	mov r0, #0
	st V_DEV, r0
.probe_loop:
	push pch
	push pcl
	b probe_slot
	ld r0, V_DEV
	add r0, #1
	st V_DEV, r0
	lt r0, #6
	bzf .probe_loop

; ------------------------------------------------------------ POST $08 banner
	mov r0, #0x08
	st GPO, r0

	ld r0, V_CON
	eq r0, #0xff
	bzf .no_console
	push pch
	push pcl
	b console_init
	mov r0, #<[msg_banner]
	st V_SRC, r0
	mov r0, #>[msg_banner]
	st V_SRC_H, r0
	push pch
	push pcl
	b puts
.no_console:

; ------------------------------------------------------------ POST $10 header
	mov r0, #0x10
	st GPO, r0

	mov r0, #1					; the kernel image starts at ROM $00800 (bank 1)
	st ROM_BANK, r0

	ld r0, $e800
	eq r0, #67					; 'C'
	bzf .m1
	b err_magic
.m1:
	ld r0, $e801
	eq r0, #85					; 'U'
	bzf .m2
	b err_magic
.m2:
	ld r0, $e802
	eq r0, #80					; 'P'
	bzf .m3
	b err_magic
.m3:
	ld r0, $e803
	eq r0, #56					; '8'
	bzf .m4
	b err_magic
.m4:
	ld r0, $e804
	eq r0, #1					; header version
	bzf .hdr_sum
	b err_magic

.hdr_sum:
	mov r0, #0					; bytes $e800-$e80d must sum to zero
	st V_SUM, r0
	mov r0, #0
.sum_loop:
	st V_TMP, r0
	ld r1, $e800+r0
	ld r0, V_SUM
	add r0, r1
	st V_SUM, r0
	ld r0, V_TMP
	add r0, #1
	lt r0, #14
	bzf .sum_loop
	ld r0, V_SUM
	eq r0, #0
	bzf .hdr_ok
	b err_magic
.hdr_ok:

	ld r0, $e806				; load address
	st V_DST, r0
	ld r0, $e807
	st V_DST_H, r0
	ld r0, $e808				; length
	st V_LEN, r0
	ld r0, $e809
	st V_LEN_H, r0
	ld r0, $e80a				; entry
	st V_ENTRY, r0
	ld r0, $e80b
	st V_ENTRY_H, r0

	ld r0, $e807				; load + length must stay below $e000
	ld r1, $e809
	add r0, r1
	lt r0, #0xe0
	bzf .size_ok
	b err_size
.size_ok:

; -------------------------------------------------------------- POST $20 copy
	mov r0, #0x20
	st GPO, r0

	mov r0, #<$e810				; the body starts at ROM $00810
	st V_SRC, r0
	mov r0, #>$e810
	st V_SRC_H, r0
	mov r0, #0
	st V_SUM, r0

.copy_loop:
	ld r0, V_LEN				; done when the length is zero
	ld r1, V_LEN_H
	or r0, r1
	eq r0, #0
	bzf .copy_done

	ldd r0, V_SRC
	std V_DST, r0
	ld r1, V_SUM
	add r1, r0
	st V_SUM, r1

	push pch
	push pcl
	b inc_src
	push pch
	push pcl
	b inc_dst
	push pch
	push pcl
	b dec_len

	ld r0, V_SRC_H				; past the banked window? next bank
	eq r0, #0xf0
	bzf .next_bank
	b .copy_loop
.next_bank:
	mov r0, #>$e800
	st V_SRC_H, r0
	ld r0, ROM_BANK
	add r0, #1
	st ROM_BANK, r0
	b .copy_loop
.copy_done:

; ------------------------------------------------------------ POST $40 verify
	mov r0, #0x40
	st GPO, r0

	mov r0, #1
	st ROM_BANK, r0
	ld r0, $e80c				; expected body checksum
	ld r1, V_SUM
	eq r0, r1
	bzf .sum_ok
	b err_checksum
.sum_ok:

; ---------------------------------------------------------------- POST $80 go
	mov r0, #0x80
	st GPO, r0
	ld r0, V_ENTRY_H
	push r0
	ld r0, V_ENTRY
	push r0
	pop pcl
	pop pch						; into the kernel

; ---------------------------------------------------------------------- errors
err_magic:
	mov r0, #<[msg_nokernel]
	st V_SRC, r0
	mov r0, #>[msg_nokernel]
	st V_SRC_H, r0
	mov r0, #0x90
	b fail

err_size:
	mov r0, #<[msg_toobig]
	st V_SRC, r0
	mov r0, #>[msg_toobig]
	st V_SRC_H, r0
	mov r0, #0x91
	b fail

err_checksum:
	mov r0, #<[msg_badsum]
	st V_SRC, r0
	mov r0, #>[msg_badsum]
	st V_SRC_H, r0
	mov r0, #0xa0
	b fail

err_ram:
	mov r0, #0x82				; RAM is broken - LEDs only
	st GPO, r0
	cli
	halt

; show the message in V_SRC (if a console is present) and halt with code r0
fail:
	st V_TMP, r0
	ld r0, V_CON
	eq r0, #0xff
	bzf .halt
	push pch
	push pcl
	b puts
.halt:
	ld r0, V_TMP
	st GPO, r0
	cli
	halt

; Walking-bit test of the stack page $0100-$01ff with the pattern in r1.
; Uses no stack - it is the stack page being tested - so it returns by
; branching to a fixed label chosen by V_TMP.
page_pattern_inline:
	st V_TMP, r1
	mov r0, #0
	st V_DEV, r0
.write:
	ld r0, V_DEV
	ld r1, V_TMP
	st $0100+r0, r1
	add r0, #1
	st V_DEV, r0
	eq r0, #0
	bzf .verify
	b .write
.verify:
	mov r0, #0
	st V_DEV, r0
.read:
	ld r0, V_DEV
	ld r1, $0100+r0
	ld r0, V_TMP
	eq r0, r1
	bzf .next
	b err_ram
.next:
	ld r0, V_DEV
	add r0, #1
	st V_DEV, r0
	eq r0, #0
	bzf .done
	b .read
.done:
	ld r0, V_TMP
	eq r0, #0x55
	bzf page_after_55
	b page_after_aa

; ----------------------------------------------------------------- RAM test
; V_START..V_END, stride 16 - write (lo xor hi) everywhere, then verify.
ram_range:
	ld r0, V_START
	st V_PTR, r0
	ld r0, V_START_H
	st V_PTR_H, r0
.fill:
	ld r0, V_PTR
	ld r1, V_PTR_H
	xor r0, r1
	std V_PTR, r0
	push pch
	push pcl
	b step16
	push pch
	push pcl
	b at_end
	eq r0, #0
	bzf .fill

	ld r0, V_START
	st V_PTR, r0
	ld r0, V_START_H
	st V_PTR_H, r0
.check:
	ldd r0, V_PTR
	st V_TMP, r0
	ld r0, V_PTR
	ld r1, V_PTR_H
	xor r0, r1
	ld r1, V_TMP
	eq r0, r1
	bzf .ok
	b err_ram
.ok:
	push pch
	push pcl
	b step16
	push pch
	push pcl
	b at_end
	eq r0, #0
	bzf .check
	pop pcl
	pop pch

; V_PTR += 16
step16:
	ld r0, V_PTR
	add r0, #16
	st V_PTR, r0
	eq r0, #0
	bzf .carry
	b .done
.carry:
	ld r0, V_PTR_H
	add r0, #1
	st V_PTR_H, r0
.done:
	pop pcl
	pop pch

; r0 = 1 when V_PTR has reached V_END
at_end:
	ld r0, V_PTR_H
	ld r1, V_END_H
	eq r0, r1
	bzf .hi_same
	mov r0, #0
	b .done
.hi_same:
	ld r0, V_PTR
	ld r1, V_END
	eq r0, r1
	bzf .yes
	mov r0, #0
	b .done
.yes:
	mov r0, #1
.done:
	pop pcl
	pop pch

; ------------------------------------------------------------- 16-bit helpers
inc_src:
	ld r0, V_SRC
	add r0, #1
	st V_SRC, r0
	eq r0, #0
	bzf .carry
	b .done
.carry:
	ld r0, V_SRC_H
	add r0, #1
	st V_SRC_H, r0
.done:
	pop pcl
	pop pch

inc_dst:
	ld r0, V_DST
	add r0, #1
	st V_DST, r0
	eq r0, #0
	bzf .carry
	b .done
.carry:
	ld r0, V_DST_H
	add r0, #1
	st V_DST_H, r0
.done:
	pop pcl
	pop pch

dec_len:
	ld r0, V_LEN
	eq r0, #0
	bzf .borrow
	sub r0, #1
	st V_LEN, r0
	b .done
.borrow:
	mov r0, #0xff
	st V_LEN, r0
	ld r0, V_LEN_H
	sub r0, #1
	st V_LEN_H, r0
.done:
	pop pcl
	pop pch

; ------------------------------------------------------------------- SPI / cards
; exchange r1 with the device at offset V_SPI; result in r1
spi_xfer:
	ld r0, V_SPI
	st $f100+r0, r1
	mov r1, #1
	st $f102+r0, r1
.spi_wait:					; SPI_RX is only valid once SPI_STAT says done
	ld r1, $f103+r0
	eq r1, #0
	bzf .spi_wait
	ld r1, $f101+r0
	pop pcl
	pop pch

cs_on:
	ld r0, V_SPI
	mov r1, #1
	st $f104+r0, r1
	pop pcl
	pop pch

cs_off:
	ld r0, V_SPI
	mov r1, #0
	st $f104+r0, r1
	pop pcl
	pop pch

; busy-wait at least 5 ms: 7 x 256 inner loops, ~0.87 ms each at 12 MHz
; (measured in the whole-machine emulator: 24 passes took 20.8 ms)
wait_5ms:
	mov r0, #7
	st V_TMP, r0
.outer:
	mov r0, #0
.inner:
	add r0, #1
	lt r0, #0xff
	bzf .inner
	ld r0, V_TMP
	sub r0, #1
	st V_TMP, r0
	eq r0, #0
	bzf .done
	b .outer
.done:
	pop pcl
	pop pch

; probe slot V_DEV - IDENT then a READ frame; fill in the slot table
probe_slot:
	ld r0, V_DEV
	shl r0, #4					; SPI register offset = slot * 16
	st V_SPI, r0
	mov r1, #16					; SPI_CFG = clk_div 2 (3 MHz), mode 0 (slot.md, probe step 1)
	st $f10f+r0, r1

	push pch
	push pcl
	b cs_on
	mov r1, #0xf0				; IDENT
	push pch
	push pcl
	b spi_xfer
	push pch
	push pcl
	b cs_off
	push pch
	push pcl
	b wait_5ms					; slot.md - the card needs >= 5 ms to answer
	mov r0, #20					; then up to 20 more tries, 5 ms apart
	st V_TRY, r0

.read:
	push pch
	push pcl
	b cs_on
	mov r1, #0xfe				; READ
	push pch
	push pcl
	b spi_xfer
	mov r1, #0					; RESP_LEN
	push pch
	push pcl
	b spi_xfer
	eq r1, #0					; $00 - not ready yet, end the frame and retry (slot.md)
	bzf .not_ready
	mov r1, #0					; card type
	push pch
	push pcl
	b spi_xfer
	st V_TYPE, r1
	mov r1, #0					; fw major
	push pch
	push pcl
	b spi_xfer
	mov r1, #0					; fw minor
	push pch
	push pcl
	b spi_xfer
	mov r1, #0					; signature
	push pch
	push pcl
	b spi_xfer
	st V_TMP, r1
	push pch
	push pcl
	b cs_off

	ld r0, V_TMP				; a card answers with $c8
	eq r0, #0xc8
	bzf .present
	mov r1, #0
	b .store
.not_ready:
	push pch
	push pcl
	b cs_off
	ld r0, V_TRY
	sub r0, #1
	st V_TRY, r0
	eq r0, #0
	bzf .gave_up
	push pch
	push pcl
	b wait_5ms
	b .read
.gave_up:
	mov r1, #0					; never answered - an empty slot
	b .store
.present:
	ld r1, V_TYPE
	eq r1, #1					; the first graphics card becomes the console
	bzf .maybe_console
	b .store
.maybe_console:
	ld r0, V_CON
	eq r0, #0xff
	bzf .take_console
	b .store
.take_console:
	ld r0, V_SPI
	st V_CON, r0
	ld r1, V_TYPE
.store:
	ld r0, V_DEV
	st SLOT_TABLE+r0, r1
	pop pcl
	pop pch

; put the console in TEXT mode
console_init:
	ld r0, V_CON
	st V_SPI, r0
	push pch
	push pcl
	b cs_on
	mov r1, #0x01				; MODE
	push pch
	push pcl
	b spi_xfer
	mov r1, #0					; TEXT
	push pch
	push pcl
	b spi_xfer
	push pch
	push pcl
	b cs_off
	pop pcl
	pop pch

; print the character in V_CHAR on the console
putc:
	ld r0, V_CON
	st V_SPI, r0
	push pch
	push pcl
	b cs_on
	mov r1, #0x10				; PUTC
	push pch
	push pcl
	b spi_xfer
	ld r1, V_CHAR
	push pch
	push pcl
	b spi_xfer
	push pch
	push pcl
	b cs_off
	pop pcl
	pop pch

; print the zero-terminated string at V_SRC
puts:
	ldd r0, V_SRC
	eq r0, #0
	bzf .done
	st V_CHAR, r0
	push pch
	push pcl
	b putc
	push pch
	push pcl
	b inc_src
	b puts
.done:
	pop pcl
	pop pch

