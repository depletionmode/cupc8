; Graphics card driver (doc/hardware/gpu-protocol.md).
;
; Replaces the old ILI9340 pixel path: the card keeps the text buffer, the
; cursor and the font, so printing a character is one two-byte frame.
;
; The console is the first graphics card in the slot table the boot ROM left
; at $0002-$0007. Its SPI register offset (slot * 16) is kept in gpu_spi;
; $ff means "no console", and every entry point then does nothing.

%define SLOT_TABLE $0002
%define GPU_CFG_DIV2 16

gpu_spi: resb 1
gpu_char: resb 1
gpu_tmp: resb 1
gpu_args: resb 8

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

; print the character in r0
gpu_putc:
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

clr_screen:
	ld r0, [gpu_spi]
	eq r0, #0xff
	bzf .none
	push pch
	push pcl
	b gpu_cs_on
	mov r0, #0x02			; CLS
	push pch
	push pcl
	b gpu_send
	mov r0, #0x07			; light grey on black
	push pch
	push pcl
	b gpu_send
	push pch
	push pcl
	b gpu_cs_off
.none:
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
