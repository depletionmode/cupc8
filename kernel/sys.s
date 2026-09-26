; The kernel API's routines (the jump table is api.s; doc/proposals/kernel-api.md)
; and running programs: `exec "NAME"` from the storage card, and API_RUN, the
; PC's `cupc8.py run`.
;
; Each routine's comment is its contract. Calls that return a code set r0
; (0 ok) and API_ERR. Every call may change r0, r1 and API_ARGS.

; ============================================================ group 0: system

; API_VERSION - r0 = 1, the version of this API
api_version:
	mov r0, #1
	pop pcl
	pop pch

; API_EXIT - end the program: back to the terminal, which resets its stack
; and prompts, as when the program returns from $7000. Never returns.
api_exit:
	b sys_restart

; API_BLOCK - r0, r1 = the API block's address ($6f00; low, high)
api_block:
	xor r0, r0
	mov r1, #0x6f
	pop pcl
	pop pch

; API_SLOTS - r0, r1 = the slot table's address ($0002; low, high): six
; bytes, the card type in slots 1-6 (slot.md, IDENT; 0 empty)
api_slots:
	mov r0, #2
	xor r1, r1
	pop pcl
	pop pch

; ============================================================ group 1: console
; The graphics card's TEXT mode, 80 x 30 (gpu-protocol.md). With no graphics
; card these do nothing, and the ones that answer give r0 = $ff.

; API_PUTC - print the character in r0 (PUTC: CR, LF, BS, TAB and FF act)
api_putc:
	b gpu_putc

; API_PUTS - print the NUL-terminated string at the pointer in API_ARGS[0..1]
api_puts:
	ld r1, API_ARGS
	ld r0, $6f01
	b print_string

; API_GETKEY - wait for a key; r0 = the key (ASCII). Waits for ever with no
; keyboard.
api_getkey:
	b keyb_read_char

; API_POLLKEY - r0 = the next key, or $ff if none is waiting
api_pollkey:
	b keyb_poll

; API_CLS - clear the screen with r0: the attribute in TEXT mode, the colour
; in GFX. The cursor goes to 0,0.
api_cls:
	mov r1, #0x02
	b api_gpu1

; API_GOTOXY - the cursor to column r0 (0-79), row r1 (0-29)
api_gotoxy:
	st API_ARGS, r0
	st $6f01, r1
	mov r0, #0x12
	mov r1, #2
	b gpu_cmd

; API_GETXY - r0 = 0, API_ARGS[0..1] = the cursor's column and row, r1 = the
; column; or r0 = $ff (no answer)
api_getxy:
	mov r0, #0x18
	b api_query0

; API_ATTR - the attribute for what is printed next: r0, the background in
; the high nibble and the foreground in the low (VGA colours; $07 at reset)
api_attr:
	b gpu_attr

; API_CURSOR - the cursor: r0 = 0 off, 1 underline, 2 block
api_cursor:
	mov r1, #0x14
	b api_gpu1

; API_SCROLL - scroll the text up r0 lines
api_scroll:
	mov r1, #0x15
	b api_gpu1

; API_CLEOL - clear from the cursor to the end of its line
api_cleol:
	mov r0, #0x16
	mov r1, #0
	b gpu_cmd

; API_POKE - write one cell, the cursor unchanged: API_ARGS[0..3] = column,
; row, character, attribute
api_poke:
	mov r0, #0x17
	mov r1, #4
	b gpu_cmd

; command r1 with the argument r0
api_gpu1:
	st API_ARGS, r0
	mov r0, r1
	mov r1, #1
	b gpu_cmd

; command r0, no arguments, its answer into API_ARGS; r0 = 0 and r1 = the
; answer's first byte, or r0 = $ff
api_query0:
	mov r1, #0
; the same with the r1 bytes at API_ARGS as its arguments
api_query:
	push pch
	push pcl
	b gpu_query
	ld r1, API_ARGS
	b api_ret

; ============================================================ group 2: graphics
; GFX mode, 320 x 240 in 256 colours (gpu-protocol.md). The arguments are the
; protocol's, in API_ARGS: an x16 is two bytes, low first; y8 and colours one
; byte. Drawing is clipped to the screen.

; API_GFX_MODE - r0 = 0 TEXT, 1 GFX, 2 the e-ink card's native mode
; (eink-card.md: the panel's own resolution in 4 greys, the API_GFX2 entries
; draw in it); clears that mode's picture. r0 = 0, or $ff for mode 2 on HDMI
; (INFO says it is not e-paper: nothing is sent, the mode stays)
api_gfx_mode:
	eq r0, #2
	bzf .native
.send:
	mov r1, #0x01
	push pch
	push pcl
	b api_gpu1
	xor r0, r0
	b api_ret
.native:
	ld r1, [gpu_kind]
	eq r1, #EINK_KIND
	bzf .send
	mov r0, #0xff
	b api_ret

; API_GFX_PIXEL - API_ARGS = x16, y8, colour
api_gfx_pixel:
	mov r0, #0x20
	mov r1, #4
	b gpu_cmd

; API_GFX_FILL_RECT - API_ARGS = x16, y8, w16, h8, colour
api_gfx_fill_rect:
	mov r0, #0x21
	b api_gpu7

; API_GFX_RECT - a 1-pixel outline; API_ARGS as API_GFX_FILL_RECT
api_gfx_rect:
	mov r0, #0x22
	b api_gpu7

; API_GFX_LINE - both ends drawn; API_ARGS = x0_16, y0_8, x1_16, y1_8, colour
api_gfx_line:
	mov r0, #0x23
api_gpu7:
	mov r1, #7
	b gpu_cmd

; API_GFX_PALETTE - API_ARGS = index, r, g, b (8 bits each)
api_gfx_palette:
	mov r0, #0x03
	mov r1, #4
	b gpu_cmd

; API_GFX_PALETTE_RESET - the default palette back
api_gfx_palette_reset:
	mov r0, #0x04
	mov r1, #0
	b gpu_cmd

; API_GFX_TEXT8 - 8x8 text, no wrapping: API_ARGS = x16, y8, fg, bg ($ff
; transparent); API_ARGS[6..7] = a pointer to the NUL-terminated text (at
; most 255 characters). The kernel puts the length in API_ARGS[5].
api_gfx_text8:
	ld r1, $6f06
	ld r0, $6f07
	push pch
	push pcl
	b str_len
	st $6f05, r0
	mov r0, #0x6f
	st [gpu_src+1], r0
	xor r0, r0
	st [gpu_src], r0
	mov r0, #0x26
	mov r1, #6
	push pch
	push pcl
	b gpu_cmd_open
	eq r0, #0
	bzf .text
	pop pcl
	pop pch
.text:
	xor r1, r1
.loop:
	ld r0, $6f05
	eq r1, r0
	bzf .end
	push r1
	ldd r0, $6f06+r1
	push pch
	push pcl
	b gpu_send
	pop r1
	add r1, #1
	b .loop
.end:
	push pch
	push pcl
	b gpu_cs_off
	pop pcl
	pop pch

; API_GFX_VSCROLL - scroll the picture up API_ARGS[0] rows (down if
; negative), the rows uncovered in colour API_ARGS[1]
api_gfx_vscroll:
	mov r0, #0x27
	mov r1, #2
	b gpu_cmd

; API_GFX_GETPIXEL - API_ARGS = x16, y8; r0 = 0 and r1 = the pixel's
; colour, or r0 = $ff
api_gfx_getpixel:
	mov r0, #0x28
	mov r1, #3
	b api_query

; API_GFX_VSYNC - r0 = 0 and r1 = frames shown since the card's power-on,
; mod 256 (60 a second on HDMI), or r0 = $ff
api_gfx_vsync:
	mov r0, #0x07
	b api_query0

; ------------------------------------------------------------ mode 2
; The e-ink card's native mode (API_GFX_MODE 2; eink-card.md, $40-$49): the
; panel's own resolution, 648 x 480 or 800 x 480, 2 bits a pixel: grey 0
; black, 1 dark grey, 2 light grey, 3 white. The arguments are the card's, in
; API_ARGS: x16, y16, w16, h16 are two bytes, low first (positions signed);
; g is a grey 0-3 (any other: the card draws nothing). Drawing is clipped to
; the panel. They return r0 = 0, or $ff on HDMI (INFO says it is not
; e-paper), which is sent nothing. In modes 0 and 1 the card ignores them.

; API_GFX2_PIXEL - API_ARGS = x16, y16, g
api_gfx2_pixel:
	mov r0, #0x40
	mov r1, #5
	b api_eink_cmd

; API_GFX2_FILL_RECT - API_ARGS = x16, y16, w16, h16, g
api_gfx2_fill_rect:
	mov r0, #0x41
	b api_eink9

; API_GFX2_RECT - a 1-pixel outline; API_ARGS as API_GFX2_FILL_RECT
api_gfx2_rect:
	mov r0, #0x42
	b api_eink9

; API_GFX2_LINE - both ends drawn; API_ARGS = x0_16, y0_16, x1_16, y1_16, g
api_gfx2_line:
	mov r0, #0x43
api_eink9:
	mov r1, #9
; command r0 with the r1 bytes at API_ARGS, on e-paper only
api_eink_cmd:
	push r0
	ld r0, [gpu_kind]
	eq r0, #EINK_KIND
	pop r0
	bzf .eink
	mov r0, #0xff
	b api_ret
.eink:
	push pch
	push pcl
	b gpu_cmd
	xor r0, r0
	b api_ret

; API_GFX2_VSCROLL - scroll the picture up API_ARGS[0..1] rows (a signed
; 16-bit dy: down if negative), the rows uncovered in grey API_ARGS[2]
api_gfx2_vscroll:
	mov r0, #0x48
	mov r1, #3
	b api_eink_cmd

; API_GFX2_GETPIXEL - API_ARGS = x16, y16; r0 = 0 and r1 = the pixel's grey
; (0 off the panel or outside mode 2), or r0 = $ff
api_gfx2_getpixel:
	ld r0, [gpu_kind]
	eq r0, #EINK_KIND
	bzf .eink
	mov r0, #0xff
	b api_ret
.eink:
	mov r0, #0x49
	mov r1, #4
	b api_query

; API_GFX2_TEXT16 - the 8 x 16 TEXT font anywhere: API_ARGS = x16, y16, fg,
; bg (a grey, or $ff transparent); API_ARGS[7..8] = a pointer to the
; NUL-terminated text (at most 255 characters). The kernel puts the length
; in API_ARGS[6].
api_gfx2_text16:
	mov r0, #0x46
	b api_eink_text

; API_GFX2_TEXT8 - the 8 x 8 font; API_ARGS as API_GFX2_TEXT16
api_gfx2_text8:
	mov r0, #0x47
api_eink_text:
	push r0
	ld r0, [gpu_kind]
	eq r0, #EINK_KIND
	bzf .eink
	pop r0
	mov r0, #0xff
	b api_ret
.eink:
	ld r1, $6f07
	ld r0, $6f08
	push pch
	push pcl
	b str_len
	st $6f06, r0
	shr r0, #6				; the frame, 8 + length bytes, in 64s (rounded up, and 1 over)
	add r0, #2
	push pch
	push pcl
	b gpu_wait_free
	mov r0, #0x6f
	st [gpu_src+1], r0
	xor r0, r0
	st [gpu_src], r0
	pop r0
	mov r1, #7
	push pch
	push pcl
	b gpu_cmd_open
	xor r1, r1
.loop:
	ld r0, $6f06
	eq r1, r0
	bzf .end
	push r1
	ldd r0, $6f07+r1
	push pch
	push pcl
	b gpu_send
	pop r1
	add r1, #1
	b .loop
.end:
	push pch
	push pcl
	b gpu_cs_off
	xor r0, r0
	b api_ret

blit_n: resb 2				; picture bytes still to send
blit_op: resb 1
blit_hdr: resb 1			; the arguments before the pointer

; API_GFX2_BLIT1 - a 1-bit picture: API_ARGS = x16, y16, w16, h16, fg, bg
; (a grey, or $ff transparent); API_ARGS[10..11] = a pointer to its
; ceil(w/8) x h bytes, rows top first, the most significant bit the
; leftmost pixel. w is at most 1020, and the frame (11 bytes and the
; picture) at most 8128 bytes: otherwise nothing is sent and r0 = $fe (send
; a big picture in several).
api_gfx2_blit1:
	mov r0, #0x44
	mov r1, #10
	st [blit_op], r0
	st [blit_hdr], r1
	mov r1, #7				; ceil(w / 8)
	mov r0, #3
	b api_eink_blit

; API_GFX2_BLIT2 - a 2-bit picture: API_ARGS = x16, y16, w16, h16;
; API_ARGS[8..9] = a pointer to its ceil(w/4) x h bytes, rows top first,
; the leftmost pixel in bits 7-6. Limits as API_GFX2_BLIT1 (the frame is 9
; bytes and the picture).
api_gfx2_blit2:
	mov r0, #0x45
	mov r1, #8
	st [blit_op], r0
	st [blit_hdr], r1
	mov r1, #3				; ceil(w / 4)
	mov r0, #2
; the picture's bytes a row: (w + r1) >> r0
api_eink_blit:
	push r0
	ld r0, [gpu_kind]
	eq r0, #EINK_KIND
	bzf .eink
	pop r0
	mov r0, #0xff
	b api_ret
.eink:
	ld r0, $6f05			; w at most 1020 ($3fc), so a row is at most 255 bytes
	gt r0, #3
	bzf .big_pop
	eq r0, #3
	bzf .w3
	b .w_ok
.w3:
	ld r0, $6f04
	gt r0, #0xfc
	bzf .big_pop
.w_ok:
	ld r0, $6f04
	add r0, r1
	st [n_a], r0
	lt r0, r1
	ld r0, $6f05
	bzf .carry
	b .row
.carry:
	add r0, #1
.row:
	st [n_a+1], r0
	mov r1, #8
	pop r0					; the shift
	sub r1, r0
	push r0
	ld r0, [n_a+1]
	shl r0, r1				; the high byte's part
	pop r1
	st [n_a+1], r0
	ld r0, [n_a]
	shr r0, r1
	ld r1, [n_a+1]
	or r0, r1
	st [blit_n], r0			; the row's bytes, 0-255
	; h at most 8117 / row, so the picture fits one frame
	st [n_b], r0
	xor r0, r0
	st [n_b+1], r0
	mov r0, #0xb5			; 8117
	st [n_a], r0
	mov r0, #0x1f
	st [n_a+1], r0
	push pch
	push pcl
	b n16_udiv				; a row of 0 bytes - $ffff
	ld r0, $6f07
	ld r1, [n_a+1]
	gt r0, r1
	bzf .big
	eq r0, r1
	bzf .h_hi
	b .fits
.h_hi:
	ld r0, $6f06
	ld r1, [n_a]
	gt r0, r1
	bzf .big
.fits:
	ld r0, [blit_n]
	st [n_a], r0
	xor r0, r0
	st [n_a+1], r0
	ld r0, $6f06
	st [n_b], r0
	ld r0, $6f07
	st [n_b+1], r0
	push pch
	push pcl
	b n16_mul
	ld r0, [n_a]
	st [blit_n], r0
	ld r0, [n_a+1]
	st [blit_n+1], r0
	; room for the frame (1 + header + picture bytes) in the card's FIFO
	ld r0, [blit_n]
	ld r1, [blit_hdr]
	add r1, #64				; + 63, rounded up
	add r0, r1
	st [n_a], r0
	lt r0, r1
	ld r0, [blit_n+1]
	bzf .c2
	b .units
.c2:
	add r0, #1
.units:
	shl r0, #2				; (bytes + 64) >> 6
	ld r1, [n_a]
	shr r1, #6
	or r0, r1
	push pch
	push pcl
	b gpu_wait_free
	mov r0, #0x6f
	st [gpu_src+1], r0
	xor r0, r0
	st [gpu_src], r0
	ld r0, [blit_op]
	ld r1, [blit_hdr]
	push pch
	push pcl
	b gpu_cmd_open
	ld r1, [blit_hdr]		; the picture, from the pointer after the arguments
	ld r0, API_ARGS+r1
	st [gpu_src], r0
	add r1, #1
	ld r0, API_ARGS+r1
	st [gpu_src+1], r0
.byte:
	ld r0, [blit_n]
	ld r1, [blit_n+1]
	or r0, r1
	eq r0, #0
	bzf .sent
	ldd r0, [gpu_src]
	push pch
	push pcl
	b gpu_send
	ld r0, [gpu_src]
	add r0, #1
	st [gpu_src], r0
	eq r0, #0
	bzf .src_hi
	b .count
.src_hi:
	ld r0, [gpu_src+1]
	add r0, #1
	st [gpu_src+1], r0
.count:
	ld r0, [blit_n]
	eq r0, #0
	sub r0, #1
	st [blit_n], r0
	bzf .n_hi
	b .byte
.n_hi:
	ld r0, [blit_n+1]
	sub r0, #1
	st [blit_n+1], r0
	b .byte
.sent:
	push pch
	push pcl
	b gpu_cs_off
	xor r0, r0
	b api_ret
.big_pop:
	pop r0
.big:
	mov r0, #0xfe
	b api_ret

; ============================================================ group 3: e-ink
; The e-paper graphics card (eink-card.md; kernel/eink.s). On HDMI these do
; nothing and give r0 = $ff.

; API_EINK_AUTO - the refresh policy from API_ARGS[0..5]: on (0/1), idle10,
; full_after, cap10, full_kind, sleep_s (AUTO then AUTO_EXT). r0 = 0 or $ff
api_eink_auto:
	mov r1, #6
.in:
	eq r1, #0
	bzf .send
	sub r1, #1
	ld r0, API_ARGS+r1
	st [eink_cfg]+r1, r0
	b .in
.send:
	push pch
	push pcl
	b eink_auto
	b api_ret

; API_EINK_GET - API_ARGS[0..5] = the policy (AUTO_GET), in API_EINK_AUTO's
; order; r0 = 0, or $ff with $ff there
api_eink_get:
	push pch
	push pcl
	b eink_get
	push r0
	mov r1, #6
.out:
	eq r1, #0
	bzf .done
	sub r1, #1
	ld r0, [eink_cfg]+r1
	st API_ARGS+r1, r0
	b .out
.done:
	pop r0
	b api_ret

; API_EINK_STATUS - API_ARGS[0..2] = busy, dirty, partials (EPD_STATUS);
; r0 = 0, or $ff with $ff there
api_eink_status:
	push pch
	push pcl
	b eink_status
	push r0
	mov r1, #3
.out:
	eq r1, #0
	bzf .done
	sub r1, #1
	ld r0, [eink_st]+r1
	st API_ARGS+r1, r0
	b .out
.done:
	pop r0
	b api_ret

; API_EINK_REFRESH - refresh the panel now: r0 = 0 partial, 1 fast full,
; 2 clean full, 3 greyscale full (REFRESH). r0 = 0 or $ff
api_eink_refresh:
	push pch
	push pcl
	b eink_refresh
	ld r0, [gpu_kind]
	eq r0, #EINK_KIND
	bzf .ok
	mov r0, #0xff
	b api_ret
.ok:
	xor r0, r0
	b api_ret

; ============================================================ group 4: storage
; Files on the storage card (storage-card.md; kernel/storage.s). Names are
; 8.3, NUL-terminated. Handles 0-3; the terminal's SAVE, LOAD and exec use 0.
; r0 = 0 or an error - the card's ($01 no SD card, $03 not found, $05 full,
; $06 write-protected, $08 bad name, $0a too many open ...), or the
; kernel's ($0b no answer, $0c no storage card, $0d writing refused on a USB
; source under 3 A).

; API_ST_INFO - API_ARGS[0..10] = media, err, flags, free32, total32 (KB)
api_st_info:
	push pch
	push pcl
	b st_info
; the card's answer (st_rlen bytes, at most 31) into API_ARGS with a 0
; after it, if r0 = 0
api_st_answer:
	eq r0, #0
	bzf .copy
	b api_ret
.copy:
	ld r1, [st_rlen]
	lt r1, #32
	bzf .fits
	mov r1, #31
.fits:
	xor r0, r0
	st API_ARGS+r1, r0
.loop:
	eq r1, #0
	bzf .done
	sub r1, #1
	ld r0, [st_rbuf]+r1
	st API_ARGS+r1, r0
	b .loop
.done:
	xor r0, r0
	b api_ret

; API_ST_OPEN - open the file named at the pointer in API_ARGS[0..1] as
; handle r0, mode r1 - 0 read, 1 write (created, or emptied), 2 append
api_st_open:
	st [st_h], r0
	st [st_mode], r1
	push pch
	push pcl
	b api_st_name
	push pch
	push pcl
	b st_open
	b api_ret

; API_ST_READ - up to r1 bytes (at most 128) from handle r0 into the buffer
; at the pointer in API_ARGS[0..1]; r1 = the bytes read (fewer than asked at
; the end of the file)
api_st_read:
	st [st_h], r0
	push pch
	push pcl
	b api_st_n
	push pch
	push pcl
	b st_read
	eq r0, #0
	bzf .copy
	b api_ret
.copy:
	xor r1, r1
.loop:
	ld r0, [st_n]
	eq r1, r0
	bzf .done
	ld r0, [st_rbuf+1]+r1
	std API_ARGS+r1, r0
	add r1, #1
	b .loop
.done:
	xor r0, r0
	b api_ret

; API_ST_WRITE - r1 bytes (at most 128) from the buffer at the pointer in
; API_ARGS[0..1] to handle r0
api_st_write:
	st [st_h], r0
	push pch
	push pcl
	b api_st_n
	xor r1, r1
.loop:
	ld r0, [st_n]
	eq r1, r0
	bzf .send
	ldd r0, API_ARGS+r1
	st [st_buf]+r1, r0
	add r1, #1
	b .loop
.send:
	push pch
	push pcl
	b st_write
	b api_ret

; API_ST_CLOSE - close handle r0, which writes out what is left
api_st_close:
	st [st_h], r0
	push pch
	push pcl
	b st_close
	b api_ret

; API_ST_SEEK - handle r0 to byte API_ARGS[0..3] (32 bits, low first)
api_st_seek:
	st [st_h], r0
	ld r0, API_ARGS
	st [st_pos], r0
	ld r0, $6f01
	st [st_pos+1], r0
	ld r0, $6f02
	st [st_pos+2], r0
	ld r0, $6f03
	st [st_pos+3], r0
	push pch
	push pcl
	b st_seek
	b api_ret

; API_ST_DIR_FIRST, API_ST_DIR_NEXT - the first / next entry of the root
; directory: API_ARGS = size32, attributes, name length, name, 0; r0 = $ff
; after the last one
api_st_dir_first:
	push pch
	push pcl
	b st_dir_first
	b api_st_answer

api_st_dir_next:
	push pch
	push pcl
	b st_dir_next
	b api_st_answer

; API_ST_DELETE - delete the file named at the pointer in API_ARGS[0..1]
api_st_delete:
	push pch
	push pcl
	b api_st_name
	push pch
	push pcl
	b st_delete
	b api_ret

; API_ST_RENAME - rename the file named at the pointer in API_ARGS[0..1] to
; the name at the pointer in API_ARGS[2..3]
api_st_rename:
	push pch
	push pcl
	b api_st_name
	xor r1, r1
.loop:
	ldd r0, $6f02+r1
	st [st_name2]+r1, r0
	eq r0, #0
	bzf .named
	add r1, #1
	eq r1, #13
	bzf .cut
	b .loop
.cut:
	xor r0, r0
	st [st_name2]+r1, r0
.named:
	push pch
	push pcl
	b st_rename
	b api_ret

; the name at the pointer in API_ARGS[0..1] into st_name (one longer than
; 12 characters is cut at 13, which the card refuses)
api_st_name:
	xor r1, r1
.loop:
	ldd r0, API_ARGS+r1
	st [st_name]+r1, r0
	eq r0, #0
	bzf .done
	add r1, #1
	eq r1, #13
	bzf .cut
	b .loop
.cut:
	xor r0, r0
	st [st_name]+r1, r0
.done:
	pop pcl
	pop pch

; r1, at most 128, into st_n
api_st_n:
	gt r1, #128
	bzf .cap
	b .set
.cap:
	mov r1, #128
.set:
	st [st_n], r1
	pop pcl
	pop pch

; ============================================================ group 6: timers
; The kernel's clock is the chipset's millisecond counter (MS_COUNT,
; $f206-$f209, memory-map.md): exact, from the 12 MHz clock. Reading
; MS_COUNT0 latches the other three bytes, so a read that starts with it is
; one value.

tim_left: resb 2			; API_WAIT_MS - steps of the counter still to see
tim_last: resb 1			;   MS_COUNT0 when last looked at

; API_TICKS - API_ARGS[0..3] = ms since power-on (32 bits, low first);
; r0 = 0. Interrupts are on afterwards.
api_ticks:
	cli
	ld r0, $f206			; MS_COUNT0 first- it latches the rest
	st API_ARGS, r0
	ld r0, $f207
	st $6f01, r0
	ld r0, $f208
	st $6f02, r0
	ld r0, $f209
	st $6f03, r0
	sti
	xor r0, r0
	b api_ret

; API_WAIT_MS - wait r0 + 256 x r1 ms (0 returns at once); r0 = 0. It
; watches the millisecond counter: to its next step, then that many more, so
; the wait is more than N ms and at most N + 1. The CPU is busy meanwhile;
; interrupts are left as they were.
api_wait_ms:
	st [tim_left], r0
	st [tim_left+1], r1
	or r0, r1
	eq r0, #0
	bzf .done
	ld r0, $f206
	st [tim_last], r0
.sync:
	ld r0, $f206
	ld r1, [tim_last]
	eq r0, r1
	bzf .sync
	st [tim_last], r0
.wait:
	ld r0, $f206			; r1 = the steps since the last look (mod 256)
	ld r1, [tim_last]
	st [tim_last], r0
	sub r0, r1
	mov r1, r0
	ld r0, [tim_left+1]
	eq r0, #0
	bzf .low
	ld r0, [tim_left]		; 256 or more to go- tim_left - r1
	lt r0, r1
	bzf .borrow
	b .sub
.borrow:
	ld r0, [tim_left+1]
	sub r0, #1
	st [tim_left+1], r0
	ld r0, [tim_left]
.sub:
	sub r0, r1
	st [tim_left], r0
	b .wait
.low:
	ld r0, [tim_left]		; done once r1 reaches what is left
	gt r0, r1
	bzf .more
	b .done
.more:
	sub r0, r1
	st [tim_left], r0
	b .wait
.done:
	xor r0, r0
	b api_ret

; ============================================================ running programs
; A program is a flat binary for $7000 (tools/mkprg.py), up to 28 KB (to
; $dfff). It is called at $7000 with interrupts on. It returns (pop pcl /
; pop pch) or calls API_EXIT, and the terminal prompts again with its stack
; reset. The console is left as the program left it.
;
; A program file on the storage card starts with a header - "C8P", then
; version 1 - and the body follows it. exec "NAME" runs any other file as a
; BASIC program (LOAD, then RUN).

sys_sp: resb 2				; the terminal's stack pointer at its prompt
sys_ptr: resb 2				; exec - where this chunk's byte 0 goes
sys_end: resb 2
sys_skip: resb 1			; exec - header bytes at the start of this chunk

sys_s_usage db "\nEXEC \"NAME\"\n"
sys_s_header db "\nbad program header\n"
sys_s_big db "\nprogram too big\n"

; sys_sp = the caller's stack pointer (before its call). No instruction reads
; SP, but a push writes the byte at SP: from $0100 (the stack's bottom) up,
; the address that takes two different pushed markers is SP.
sys_mark:
	cli
	xor r0, r0
	st [sys_sp], r0
	mov r0, #1
	st [sys_sp+1], r0
.probe:
	push #0xa5
	pop r0
	ldd r0, [sys_sp]
	eq r0, #0xa5
	bzf .maybe
.next:
	ld r0, [sys_sp]
	add r0, #1
	st [sys_sp], r0
	eq r0, #0
	bzf .carry
	b .probe
.carry:
	ld r0, [sys_sp+1]
	add r0, #1
	st [sys_sp+1], r0
	b .probe
.maybe:
	push #0x5a
	pop r0
	ldd r0, [sys_sp]
	eq r0, #0x5a
	bzf .found
	b .next
.found:
	ld r0, [sys_sp]			; less this call's return address
	sub r0, #2
	st [sys_sp], r0
	lt r0, #0xfe
	bzf .done
	ld r0, [sys_sp+1]
	sub r0, #1
	st [sys_sp+1], r0
.done:
	sti
	pop pcl
	pop pch

; back to the terminal's prompt: pop until SP is sys_sp again (the same
; probe), the interrupt vectors planted again (a program may have changed
; them), then the prompt
sys_restart:
	cli
.probe:
	push #0xa5
	pop r0
	ldd r0, [sys_sp]
	eq r0, #0xa5
	bzf .maybe
.drop:
	pop r0
	b .probe
.maybe:
	push #0x5a
	pop r0
	ldd r0, [sys_sp]
	eq r0, #0x5a
	bzf .there
	b .drop
.there:
	xor r0, r0
	st API_RUN, r0
	push pch
	push pcl
	b irq_setup
	b term_do.loop

; run the program at $7000. API_RUN is 2 while it runs (cupc8.py run then
; refuses to write over it), 0 again at the prompt.
sys_run:
	xor r0, r0
	st [keyb_term], r0
	st API_ERR, r0
	mov r0, #2
	st API_RUN, r0
	push pch
	push pcl
	b $7000
	b sys_restart

; the terminal's exec "NAME"
sys_cmd_exec:
	push pch
	push pcl
	b ub_get_name
	eq r0, #0
	bzf .usage
	xor r0, r0
	st [st_h], r0
	st [st_mode], r0
	push pch
	push pcl
	b st_open
	eq r0, #0
	bzf .opened
	b .error
.opened:
	mov r0, #0xfc			; the 4 header bytes fall before $7000
	st [sys_ptr], r0
	mov r0, #0x6f
	st [sys_ptr+1], r0
	mov r0, #4
	st [sys_skip], r0
	push pch
	push pcl
	b sys_chunk
	eq r0, #0
	bzf .header
	b .close_error
.header:
	ld r0, [st_n]
	lt r0, #3
	bzf .basic
	ld r0, [st_rbuf+1]
	eq r0, #67				; C
	bzf .c
	b .basic
.c:
	ld r0, [st_rbuf+2]
	eq r0, #56				; 8
	bzf .c8
	b .basic
.c8:
	ld r0, [st_rbuf+3]
	eq r0, #80				; P
	bzf .c8p
	b .basic
.c8p:
	ld r0, [st_n]
	lt r0, #4
	bzf .bad_header
	ld r0, [st_rbuf+4]
	eq r0, #1				; version 1
	bzf .copy
	b .bad_header
.copy:
	ld r0, [sys_ptr]		; sys_end = sys_ptr + st_n, at most $e000
	ld r1, [st_n]
	add r0, r1
	st [sys_end], r0
	lt r0, r1
	ld r1, [sys_ptr+1]
	bzf .carry
	b .end_hi
.carry:
	add r1, #1
.end_hi:
	st [sys_end+1], r1
	gt r1, #0xe0
	bzf .big
	eq r1, #0xe0
	bzf .at_e0
	b .fits
.at_e0:
	ld r0, [sys_end]
	eq r0, #0
	bzf .fits
	b .big
.fits:
	ld r1, [sys_skip]
.byte:
	ld r0, [st_n]
	eq r1, r0
	bzf .copied
	ld r0, [st_rbuf+1]+r1
	std [sys_ptr]+r1, r0
	add r1, #1
	b .byte
.copied:
	ld r0, [sys_end]
	st [sys_ptr], r0
	ld r0, [sys_end+1]
	st [sys_ptr+1], r0
	xor r0, r0
	st [sys_skip], r0
	ld r0, [st_n]
	eq r0, #128				; a short chunk is the end of the file
	bzf .more
	push pch
	push pcl
	b st_close
	eq r0, #0
	bzf .run
	b .error
.run:
	b sys_run
.more:
	push pch
	push pcl
	b sys_chunk
	eq r0, #0
	bzf .copy
	b .close_error
.basic:
	push pch
	push pcl
	b st_close
	push pch
	push pcl
	b ub_load_file
	eq r0, #0
	bzf .run_basic
	b .error
.run_basic:
	b term_cmd_run
.bad_header:
	push pch
	push pcl
	b st_close
	mov r0, #>[sys_s_header]
	mov r1, #<[sys_s_header]
	b .print
.big:
	push pch
	push pcl
	b st_close
	mov r0, #>[sys_s_big]
	mov r1, #<[sys_s_big]
	b .print
.usage:
	mov r0, #>[sys_s_usage]
	mov r1, #<[sys_s_usage]
.print:
	push pch
	push pcl
	b str_printstr
	b .done
.close_error:
	push r0
	push pch
	push pcl
	b st_close
	pop r0
.error:
	push pch
	push pcl
	b st_print_err
.done:
	pop pcl
	pop pch

; the next 128 bytes of handle 0 into st_rbuf+1 (st_n = how many); r0 = error
sys_chunk:
	mov r0, #128
	st [st_n], r0
	b st_read
