; gfxdemo- the graphics card's modes through the kernel API
; (doc/hardware/gpu-protocol.md, doc/proposals/kernel-api.md).
;
; 1. TEXT mode- the 16 colours, as text and as colour swatches.
; 2. GFX mode (320 x 240, 256 colours)- the whole palette as a 16 x 16 grid
;    (the VGA colours, the colour cube, the grey ramp).
; 3. GFX mode- a starburst of lines, nested rectangles and 8x8 text.
; 4. The e-ink card's native mode 2 (the panel's 648 x 480 or 800 x 480 in
;    four greys)- four grey bars, a fan of lines, 8 x 16 text. On HDMI it
;    says so and skips it.
; A key moves on each time. On the e-ink card the colours show as greys:
; after drawing stages 2, 3 and 4 it asks for a greyscale refresh (the TEXT
; stage is left to the card's automatic refresh). API_EINK_STATUS tells the
; cards apart (0 on e-ink, $ff on HDMI, which it sends nothing).
;
; Build- python3 tools/mkprg.py examples/gfxdemo/gfxdemo.s -o build/GFXDEMO.PRG
; Run- exec "GFXDEMO.PRG"

msg_t1 db "CUPC/8 in colour "
msg_blk db "        "
msg_key db "\nPress a key for GFX mode (320 x 240, 256 colours) ..."
msg_pal db "THE 256-COLOUR PALETTE"
msg_art db "CUPC/8 GFX 320x240 256 COLOURS"
msg_bye db "\nThat was TEXT and GFX mode. Back to the terminal.\n"
msg_skip db "\nStage 4, the e-ink card's native 4-grey mode, is e-ink only: skipped."
msg_bye2 db "\nThat was TEXT, GFX and the e-ink card's mode 2. Back to the terminal.\n"
msg_n2 db "E-INK NATIVE 4 GREYS"
msg_g0 db "0 BLACK"
msg_g1 db "1 DARK "
msg_g2 db "2 LIGHT"
msg_g3 db "3 WHITE"
bar_x db 8, 0, 168, 0, 72, 1, 232, 1

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
eink: resb 1			; 1 on the e-ink card
xo: resb 1				; mode 2: the 640-pixel picture's left edge on the panel
tpl: resb 1
tph: resb 1

main:
	; which card (EPD_STATUS: only the e-ink card answers)
	push pch
	push pcl
	b API_EINK_STATUS
	mov r1, #1
	eq r0, #0
	bzf .card
	xor r1, r1
.card:
	st [eink], r1

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
	b grey_refresh
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
	b grey_refresh
	push pch
	push pcl
	b API_GETKEY

	; ---------------------------------------------------------- 4. mode 2
	ld r0, [eink]
	eq r0, #0
	bzf .back
	push pch
	push pcl
	b native

	; ---------------------------------------------------------- back to TEXT
.back:
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
	ld r0, [eink]
	eq r0, #0
	bzf .hdmi
	mov r0, #<[msg_bye2]
	mov r1, #>[msg_bye2]
	b .bye
.hdmi:
	mov r0, #<[msg_skip]
	mov r1, #>[msg_skip]
	push pch
	push pcl
	b puts
	mov r0, #<[msg_bye]
	mov r1, #>[msg_bye]
.bye:
	push pch
	push pcl
	b puts
	pop pcl
	pop pch

; e-ink: a greyscale refresh, to show the GFX greys as greys (HDMI: nothing)
grey_refresh:
	ld r0, [eink]
	eq r0, #0
	bzf .done
	mov r0, #3
	push pch
	push pcl
	b API_EINK_REFRESH
.done:
	pop pcl
	pop pch

; stage 4, on the e-ink card: mode 2, the panel's own pixels in greys 0-3;
; the picture is 640 wide, centred (xo 4 on the 648 x 480 panel, 80 on the
; 800 x 480). Then a greyscale refresh and a key.
native:
	mov r0, #2
	push pch
	push pcl
	b API_GFX_MODE				; cleared to white
	mov r0, #4
	st [xo], r0
	mov r0, #0xbc				; (700, 0) is on the 800 x 480 panel only
	st $6f00, r0
	mov r0, #2
	st $6f01, r0
	xor r0, r0
	st $6f02, r0
	st $6f03, r0
.ask:
	push pch
	push pcl
	b API_GFX2_GETPIXEL			; (it waits behind a refresh, so ask again)
	eq r0, #0
	bzf .asked
	b .ask
.asked:
	eq r1, #3
	bzf .wide
	b .bars
.wide:
	mov r0, #80
	st [xo], r0

	; the four grey bars, 144 x 200 at y 56, and their names under them
.bars:
	xor r0, r0
	st [i], r0
.bar:
	ld r0, [i]
	shl r0, #1
	ld r1, [bar_x]+r0
	st [xl], r1
	add r0, #1
	ld r1, [bar_x]+r0
	st [xh], r1
	push pch
	push pcl
	b bar_at
	mov r0, #144
	st $6f04, r0
	xor r0, r0
	st $6f05, r0
	st $6f07, r0
	mov r0, #200
	st $6f06, r0
	ld r0, [i]
	st $6f08, r0
	push pch
	push pcl
	b API_GFX2_FILL_RECT
	push pch
	push pcl
	b bar_at					; a black outline (the white bar has only that)
	mov r0, #144
	st $6f04, r0
	xor r0, r0
	st $6f05, r0
	st $6f07, r0
	st $6f08, r0
	mov r0, #200
	st $6f06, r0
	push pch
	push pcl
	b API_GFX2_RECT
	ld r0, [xl]					; the name, 16 in and under the bar
	add r0, #16
	st [xl], r0
	push pch
	push pcl
	b bar_at
	mov r0, #8
	st $6f02, r0				; y 264
	mov r0, #1
	st $6f03, r0
	xor r0, r0
	st $6f04, r0				; black
	mov r0, #0xff
	st $6f05, r0				; on the white, transparent
	ld r0, [i]
	shl r0, #3					; msg_g0 .. msg_g3 are 8 bytes apart
	mov r1, #<[msg_g0]
	add r0, r1
	st $6f07, r0
	lt r0, r1					; carried
	mov r0, #>[msg_g0]
	bzf .carry
	b .name
.carry:
	add r0, #1
.name:
	st $6f08, r0
	push pch
	push pcl
	b API_GFX2_TEXT16
	ld r0, [i]
	add r0, #1
	st [i], r0
	eq r0, #4
	bzf .fan
	b .bar

	; a fan of lines from (320, 470) to (0, 296), (40, 296) ... (640, 296),
	; in greys 0, 1, 2 in turn
.fan:
	xor r0, r0
	st [i], r0
	st [col], r0
	st [xl], r0
	st [xh], r0
.line:
	mov r0, #0x40				; 320
	mov r1, #1
	push pch
	push pcl
	b add_xo
	st $6f00, r0
	st $6f01, r1
	mov r0, #0xd6				; 470
	st $6f02, r0
	mov r0, #1
	st $6f03, r0
	ld r0, [xl]
	ld r1, [xh]
	push pch
	push pcl
	b add_xo
	st $6f04, r0
	st $6f05, r1
	mov r0, #0x28				; 296
	st $6f06, r0
	mov r0, #1
	st $6f07, r0
	ld r0, [col]
	st $6f08, r0
	push pch
	push pcl
	b API_GFX2_LINE
	ld r0, [col]				; the next grey, 0 1 2 0 ...
	add r0, #1
	eq r0, #3
	bzf .grey0
	b .grey
.grey0:
	xor r0, r0
.grey:
	st [col], r0
	ld r0, [xl]					; x + 40
	add r0, #40
	st [xl], r0
	lt r0, #40
	bzf .l_carry
	b .l_next
.l_carry:
	ld r0, [xh]
	add r0, #1
	st [xh], r0
.l_next:
	ld r0, [i]
	add r0, #1
	st [i], r0
	eq r0, #17
	bzf .title
	b .line

	; the title, 20 characters centred at the top
.title:
	mov r0, #240
	xor r1, r1
	push pch
	push pcl
	b add_xo
	st $6f00, r0
	st $6f01, r1
	mov r0, #16
	st $6f02, r0
	xor r0, r0
	st $6f03, r0
	st $6f04, r0				; black
	mov r0, #0xff
	st $6f05, r0				; transparent
	mov r0, #<[msg_n2]
	st $6f07, r0
	mov r0, #>[msg_n2]
	st $6f08, r0
	push pch
	push pcl
	b API_GFX2_TEXT16
	push pch
	push pcl
	b grey_refresh
	push pch
	push pcl
	b API_GETKEY
	pop pcl
	pop pch

; API_ARGS[0..3] = (xh:xl + xo, 56)
bar_at:
	ld r0, [xl]
	ld r1, [xh]
	push pch
	push pcl
	b add_xo
	st $6f00, r0
	st $6f01, r1
	mov r0, #56
	st $6f02, r0
	xor r0, r0
	st $6f03, r0
	pop pcl
	pop pch

; r1:r0 += xo
add_xo:
	push r1
	ld r1, [xo]
	add r0, r1
	lt r0, r1					; carried
	pop r1
	bzf .carry
	pop pcl
	pop pch
.carry:
	add r1, #1
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
