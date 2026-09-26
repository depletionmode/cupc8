; gfxdemo- the graphics card's modes through the kernel API
; (doc/hardware/gpu-protocol.md, doc/proposals/kernel-api.md).
;
; 1. TEXT mode- the 16 colours, as text and as colour swatches.
; 2. GFX mode (320 x 240, 256 colours)- the whole palette as a 16 x 16 grid
;    (the VGA colours, the colour cube, the grey ramp).
; 3. GFX mode- a starburst of lines, nested rectangles and 8x8 text.
; A key moves on each time. On the e-ink card the colours show as greys.
;
; Build- python3 tools/mkprg.py examples/gfxdemo/gfxdemo.s -o build/GFXDEMO.PRG
; Run- exec "GFXDEMO.PRG"

msg_t1 db "CUPC/8 in colour "
msg_blk db "        "
msg_key db "\nPress a key for GFX mode (320 x 240, 256 colours) ..."
msg_pal db "THE 256-COLOUR PALETTE"
msg_art db "CUPC/8 GFX 320x240 256 COLOURS"
msg_bye db "\nThat was TEXT and GFX mode. Back to the terminal.\n"

i: resb 1
row: resb 1
col: resb 1
colour: resb 1
xl: resb 1
xh: resb 1
y: resb 1
wl: resb 1
wh: resb 1
h: resb 1

main:
	; ---------------------------------------------------------- 1. TEXT colours
	xor r0, r0
	push pch
	push pcl
	b API_CLS
	xor r0, r0
	st [i], r0
.text_row:
	ld r0, [i]				; the colour as the foreground, on black
	eq r0, #0
	bzf .grey_on_black		; black on black would not show
	b .set_fg
.grey_on_black:
	mov r0, #8
.set_fg:
	push pch
	push pcl
	b API_ATTR
	mov r0, #<[msg_t1]
	mov r1, #>[msg_t1]
	push pch
	push pcl
	b puts
	ld r0, [i]				; and as a swatch- the colour as the background
	shl r0, #4
	push pch
	push pcl
	b API_ATTR
	mov r0, #<[msg_blk]
	mov r1, #>[msg_blk]
	push pch
	push pcl
	b puts
	mov r0, #7
	push pch
	push pcl
	b API_ATTR
	mov r0, #10
	push pch
	push pcl
	b API_PUTC
	ld r0, [i]
	add r0, #1
	st [i], r0
	eq r0, #16
	bzf .text_done
	b .text_row
.text_done:
	mov r0, #<[msg_key]
	mov r1, #>[msg_key]
	push pch
	push pcl
	b puts
	push pch
	push pcl
	b API_GETKEY

	; ---------------------------------------------------------- 2. the palette
	mov r0, #1
	push pch
	push pcl
	b API_GFX_MODE
	xor r0, r0
	st [colour], r0
	st [y], r0
	st [row], r0
.pal_row:
	xor r0, r0
	st [xl], r0
	st [xh], r0
	st [col], r0
.pal_col:
	ld r0, [xl]
	st $6f00, r0
	ld r0, [xh]
	st $6f01, r0
	ld r0, [y]
	st $6f02, r0
	mov r0, #20
	st $6f03, r0				; w 20
	xor r0, r0
	st $6f04, r0
	mov r0, #15
	st $6f05, r0				; h 15
	ld r0, [colour]
	st $6f06, r0
	push pch
	push pcl
	b API_GFX_FILL_RECT
	ld r0, [colour]
	add r0, #1
	st [colour], r0
	ld r0, [xl]				; x + 20, carrying into the high byte
	add r0, #20
	st [xl], r0
	lt r0, #20
	bzf .x_carry
	b .x_next
.x_carry:
	ld r0, [xh]
	add r0, #1
	st [xh], r0
.x_next:
	ld r0, [col]
	add r0, #1
	st [col], r0
	eq r0, #16
	bzf .pal_next_row
	b .pal_col
.pal_next_row:
	ld r0, [y]
	add r0, #15
	st [y], r0
	ld r0, [row]
	add r0, #1
	st [row], r0
	eq r0, #16
	bzf .pal_title
	b .pal_row
.pal_title:
	mov r0, #72
	mov r1, #112
	push pch
	push pcl
	b title_pal
	push pch
	push pcl
	b API_GETKEY

	; ---------------------------------------------------------- 3. line art
	xor r0, r0
	push pch
	push pcl
	b API_CLS
	; a starburst from the centre to the top and bottom edges
	mov r0, #16
	st [colour], r0
	xor r0, r0
	st [xl], r0
	st [xh], r0
	st [col], r0
.burst:
	xor r0, r0
	st [y], r0
	push pch
	push pcl
	b burst_line
	mov r0, #239
	st [y], r0
	push pch
	push pcl
	b burst_line
	ld r0, [colour]
	add r0, #6
	st [colour], r0
	ld r0, [xl]
	add r0, #20
	st [xl], r0
	lt r0, #20
	bzf .b_carry
	b .b_next
.b_carry:
	ld r0, [xh]
	add r0, #1
	st [xh], r0
.b_next:
	ld r0, [col]
	add r0, #1
	st [col], r0
	eq r0, #17
	bzf .rects
	b .burst

	; nested rectangles- each 8 in and 6 down from the last
.rects:
	xor r0, r0
	st [xl], r0
	st [y], r0
	st [i], r0
	mov r0, #0x40
	st [wl], r0				; w 320 = $140
	mov r0, #1
	st [wh], r0
	mov r0, #240
	st [h], r0
	mov r0, #196
	st [colour], r0
.rect:
	ld r0, [xl]
	st $6f00, r0
	xor r0, r0
	st $6f01, r0
	ld r0, [y]
	st $6f02, r0
	ld r0, [wl]
	st $6f03, r0
	ld r0, [wh]
	st $6f04, r0
	ld r0, [h]
	st $6f05, r0
	ld r0, [colour]
	st $6f06, r0
	push pch
	push pcl
	b API_GFX_RECT
	ld r0, [xl]
	add r0, #8
	st [xl], r0
	ld r0, [y]
	add r0, #6
	st [y], r0
	ld r0, [h]
	sub r0, #12
	st [h], r0
	ld r0, [colour]
	add r0, #1
	st [colour], r0
	ld r0, [wl]				; w - 16, borrowing from the high byte
	lt r0, #16
	bzf .w_borrow
	b .w_sub
.w_borrow:
	ld r1, [wh]
	sub r1, #1
	st [wh], r1
.w_sub:
	ld r0, [wl]
	sub r0, #16
	st [wl], r0
	ld r0, [i]
	add r0, #1
	st [i], r0
	eq r0, #8
	bzf .art_title
	b .rect
.art_title:
	mov r0, #40
	mov r1, #116
	push pch
	push pcl
	b title_art
	push pch
	push pcl
	b API_GETKEY

	; ---------------------------------------------------------- back to TEXT
	xor r0, r0
	push pch
	push pcl
	b API_GFX_MODE
	mov r0, #7
	push pch
	push pcl
	b API_ATTR
	mov r0, #7
	push pch
	push pcl
	b API_CLS
	mov r0, #<[msg_bye]
	mov r1, #>[msg_bye]
	push pch
	push pcl
	b puts
	pop pcl
	pop pch

; a line from the centre (160, 120) to (xh:xl, y) in the current colour
burst_line:
	mov r0, #160
	st $6f00, r0
	xor r0, r0
	st $6f01, r0
	mov r0, #120
	st $6f02, r0
	ld r0, [xl]
	st $6f03, r0
	ld r0, [xh]
	st $6f04, r0
	ld r0, [y]
	st $6f05, r0
	ld r0, [colour]
	st $6f06, r0
	push pch
	push pcl
	b API_GFX_LINE
	pop pcl
	pop pch

; 8x8 text at x = r0, y = r1, white on black
title_pal:
	st [xl], r0
	st [y], r1
	mov r0, #<[msg_pal]
	st $6f06, r0
	mov r0, #>[msg_pal]
	st $6f07, r0
	b title
title_art:
	st [xl], r0
	st [y], r1
	mov r0, #<[msg_art]
	st $6f06, r0
	mov r0, #>[msg_art]
	st $6f07, r0
title:
	ld r0, [xl]
	st $6f00, r0
	xor r0, r0
	st $6f01, r0
	ld r0, [y]
	st $6f02, r0
	mov r0, #15
	st $6f03, r0				; fg white
	xor r0, r0
	st $6f04, r0				; bg black
	push pch
	push pcl
	b API_GFX_TEXT8
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
