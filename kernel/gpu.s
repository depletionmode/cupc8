; Graphics card driver (doc/hardware/gpu-protocol.md).
;
; Replaces the old ILI9340 pixel path: the card keeps the text buffer, the
; cursor and the font, so printing a character is one two-byte frame.
;
; The console is the first graphics card in the slot table the boot ROM left
; at $0002-$0007. Its SPI register offset (slot * 16) is kept in gpu_spi;
; $ff means "no console", and every entry point then does nothing.
; gpu_kind (kernel/eink.s) says which graphics card it is, from INFO.

%define SLOT_TABLE $0002
%define GPU_CFG_DIV2 16

gpu_spi: resb 1
gpu_char: resb 1
gpu_tmp: resb 1
gpu_args: resb 8
gpu_tries: resb 1
gpu_n: resb 1
gpu_i: resb 1

gpu_init:
	mov r0, #0xff
	st [gpu_spi], r0
	xor r0, r0
	st [gpu_tmp], r0
.scan:
	ld r0, [gpu_tmp]
	ld r1, SLOT_TABLE+r0
	eq r1, #1				; card type 1 is graphics
	bzf .found
	ld r0, [gpu_tmp]
	add r0, #1
	st [gpu_tmp], r0
	lt r0, #6
	bzf .scan
	b .done					; no graphics card fitted
.found:
	ld r0, [gpu_tmp]
	shl r0, #4				; SPI register offset
	st [gpu_spi], r0
	mov r1, #GPU_CFG_DIV2
	st $f10f+r0, r1			; SPI config for this device

	push pch
	push pcl
	b gpu_cs_on
	mov r0, #0x01			; MODE
	push pch
	push pcl
	b gpu_send
	mov r0, #0				; TEXT
	push pch
	push pcl
	b gpu_send
	push pch
	push pcl
	b gpu_cs_off
	push pch
	push pcl
	b gpu_info
.done:
	pop pcl
	pop pch

; INFO: which graphics card the console is. gpu_kind = its first response
; byte (0 HDMI, 1 e-paper), or $ff if it never answers (READ polled 255 times)
gpu_info:
	mov r0, #0xff
	st [gpu_kind], r0
	mov r0, #0x08			; INFO
	mov r1, #0
	push pch
	push pcl
	b gpu_query
	eq r0, #0
	bzf .answered
	b .done
.answered:
	ld r0, API_ARGS
	st [gpu_kind], r0
.done:
	pop pcl
	pop pch

; ------------------------------------------------------------ any command
; (the kernel API's console and graphics calls, sys.s)

; command r0 with the r1 bytes at API_ARGS as its arguments
gpu_cmd:
	st [gpu_char], r0
	mov r0, #0x6f
	st [gpu_src+1], r0
	xor r0, r0
	st [gpu_src], r0
	ld r0, [gpu_char]
; command r0 with the r1 bytes at gpu_src
gpu_cmd_from:
	push pch
	push pcl
	b gpu_cmd_open
	eq r0, #0
	bzf .close
	b .none
.close:
	push pch
	push pcl
	b gpu_cs_off
.none:
	pop pcl
	pop pch

; the same, but the frame is left open (CS on) for more bytes. r0 = 0, or $ff
; with no console (nothing sent, CS untouched)
gpu_cmd_open:
	st [gpu_char], r0
	st [gpu_n], r1
	ld r0, [gpu_spi]
	eq r0, #0xff
	bzf .none
	push pch
	push pcl
	b gpu_cs_on
	ld r0, [gpu_char]
	push pch
	push pcl
	b gpu_send
	xor r1, r1
	st [gpu_i], r1
.loop:
	ld r1, [gpu_i]
	ld r0, [gpu_n]
	eq r1, r0
	bzf .sent
	ldd r0, [gpu_src]+r1
	add r1, #1
	st [gpu_i], r1
	push pch
	push pcl
	b gpu_send
	b .loop
.sent:
	xor r0, r0
	b .done
.none:
	mov r0, #0xff
.done:
	pop pcl
	pop pch

; command r0 with the r1 bytes at API_ARGS, then its answer into API_ARGS
gpu_query:
	st [gpu_char], r0
	mov r0, #0x6f
	st [gpu_src+1], r0
	xor r0, r0
	st [gpu_src], r0
	ld r0, [gpu_char]
; command r0 with the r1 bytes at gpu_src, then its answer into gpu_src. r0 =
; 0 and r1 = its length, or r0 = $ff (no console, or READ said "not ready"
; 255 times)
gpu_query_from:
	push pch
	push pcl
	b gpu_cmd_from
	ld r0, [gpu_spi]
	eq r0, #0xff
	bzf .fail
	xor r0, r0
	st [gpu_tries], r0
.poll:
	push pch
	push pcl
	b gpu_cs_on
	mov r0, #0xfe			; READ, the status byte comes back
	push pch
	push pcl
	b gpu_send
	xor r0, r0				; RESP_LEN, 0 = not ready yet
	push pch
	push pcl
	b gpu_send
	eq r0, #0
	bzf .again
	st [gpu_n], r0
	xor r1, r1
	st [gpu_i], r1
.byte:
	ld r1, [gpu_i]
	ld r0, [gpu_n]
	eq r1, r0
	bzf .got
	xor r0, r0
	push pch
	push pcl
	b gpu_send
	ld r1, [gpu_i]
	std [gpu_src]+r1, r0
	add r1, #1
	st [gpu_i], r1
	b .byte
.got:
	push pch
	push pcl
	b gpu_cs_off
	xor r0, r0
	ld r1, [gpu_n]
	b .done
.again:
	push pch
	push pcl
	b gpu_cs_off
	ld r0, [gpu_tries]
	add r0, #1
	st [gpu_tries], r0
	eq r0, #0xff
	bzf .fail
	b .poll
.fail:
	mov r0, #0xff
.done:
	pop pcl
	pop pch

; wait until the console's FIFO has room for a frame of r0 x 64 bytes
; (gpu-protocol.md: FREE, the status byte, in 64s), asking with $FF frames
; (slot.md: never an opcode, so nothing is queued; a NOP would fill the FIFO
; while an e-ink REFRESH holds it). A frame over 64 bytes checks first: the
; card drops one that does not fit. With no console, at once.
gpu_wait_free:
	st [gpu_n], r0
	ld r0, [gpu_spi]
	eq r0, #0xff
	bzf .done
.poll:
	push pch
	push pcl
	b gpu_cs_on
	mov r0, #0xff
	push pch
	push pcl
	b gpu_send
	and r0, #0x7f
	push r0
	push pch
	push pcl
	b gpu_cs_off
	pop r0
	ld r1, [gpu_n]
	lt r0, r1
	bzf .poll
.done:
	pop pcl
	pop pch

; exchange r0 with the console; result in r0
gpu_send:
	st [gpu_tmp], r0
	ld r0, [gpu_spi]
	ld r1, [gpu_tmp]
	st $f100+r0, r1
	mov r1, #1
	st $f102+r0, r1
.spi_wait:					; SPI_RX is only valid once SPI_STAT says done
	ld r1, $f103+r0
	eq r1, #0
	bzf .spi_wait
	ld r1, $f101+r0
	st [gpu_tmp], r1
	ld r0, [gpu_tmp]
	pop pcl
	pop pch

gpu_cs_on:
	ld r0, [gpu_spi]
	mov r1, #1
	st $f104+r0, r1
	pop pcl
	pop pch

gpu_cs_off:
	ld r0, [gpu_spi]
	mov r1, #0
	st $f104+r0, r1
	pop pcl
	pop pch

; print the character in r0 (and mirror it to the USB console, console.s)
gpu_putc:
	push pch
	push pcl
	b con_putc
	st [gpu_char], r0
	ld r0, [gpu_spi]
	eq r0, #0xff
	bzf .none
	push pch
	push pcl
	b gpu_cs_on
	mov r0, #0x10			; PUTC
	push pch
	push pcl
	b gpu_send
	ld r0, [gpu_char]
	push pch
	push pcl
	b gpu_send
	push pch
	push pcl
	b gpu_cs_off
.none:
	pop pcl
	pop pch

; set the text attribute in r0
gpu_attr:
	st [gpu_char], r0
	ld r0, [gpu_spi]
	eq r0, #0xff
	bzf .none
	push pch
	push pcl
	b gpu_cs_on
	mov r0, #0x13			; ATTR
	push pch
	push pcl
	b gpu_send
	ld r0, [gpu_char]
	push pch
	push pcl
	b gpu_send
	push pch
	push pcl
	b gpu_cs_off
.none:
	pop pcl
	pop pch

; ---------------------------------------------------------------- compatibility
; the terminal and BASIC call these

print_ascii_char:
	push pch
	push pcl
	b gpu_putc
	pop pcl
	pop pch

print_ascii_char_inverse:
	st [gpu_char], r0
	mov r0, #0x70			; black on light grey
	push pch
	push pcl
	b gpu_attr
	ld r0, [gpu_char]
	push pch
	push pcl
	b gpu_putc
	mov r0, #0x07
	push pch
	push pcl
	b gpu_attr
	pop pcl
	pop pch

; FILL_RECT with the old stack ABI - callers push colour, h, w, y, x
gpu_fill_rect:
	pop r0
	st [gpu_args], r0		; return address low
	pop r0
	st [gpu_args+1], r0		; return address high
	pop r0
	st [gpu_args+2], r0		; x
	pop r0
	st [gpu_args+3], r0		; y
	pop r0
	st [gpu_args+4], r0		; w
	pop r0
	st [gpu_args+5], r0		; h
	pop r0
	st [gpu_args+6], r0		; colour

	ld r0, [gpu_spi]
	eq r0, #0xff
	bzf .none
	push pch
	push pcl
	b gpu_cs_on
	mov r0, #0x21			; FILL_RECT
	push pch
	push pcl
	b gpu_send
	ld r0, [gpu_args+2]		; x low
	push pch
	push pcl
	b gpu_send
	mov r0, #0				; x high
	push pch
	push pcl
	b gpu_send
	ld r0, [gpu_args+3]		; y
	push pch
	push pcl
	b gpu_send
	ld r0, [gpu_args+4]		; w low
	push pch
	push pcl
	b gpu_send
	mov r0, #0				; w high
	push pch
	push pcl
	b gpu_send
	ld r0, [gpu_args+5]		; h
	push pch
	push pcl
	b gpu_send
	ld r0, [gpu_args+6]		; colour
	push pch
	push pcl
	b gpu_send
	push pch
	push pcl
	b gpu_cs_off
.none:
	ld r0, [gpu_args+1]
	push r0
	ld r0, [gpu_args]
	push r0
	pop pcl
	pop pch
