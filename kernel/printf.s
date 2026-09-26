; routines for printing text

; print_ascii_char is gpu.s's gpu_putc

rs_msg_addr: resb 2
rs_i: resb 1
; a line from the keyboard, echoed, into the buffer at r0 (high), r1 (low):
; up to 78 characters, a CR and a 0; rs_i = the characters' count
read_string:
;
;	; first store string address in memory
	st [rs_msg_addr], r1
	st [rs_msg_addr+1], r0

	; loop through string until <enter>
    xor r1, r1
    st [rs_i], r1
.loop:
	push pch
	push pcl
	b keyb_read_char
	eq r0, #10
	bzf .done
	eq r0, #13
	bzf .done
	eq r0, #8				; Backspace (DEL too) takes the last character back
	bzf .erase
	eq r0, #127
	bzf .erase
  ; buffers are 80 bytes: 78 characters, then the CR and the terminator
  ld r1, [rs_i]
  eq r1, #78
  bzf .loop
  std [rs_msg_addr]+r1, r0
    push pch
    push pcl
    b print_ascii_char
    ld r1, [rs_i]
    add r1, #1
    st [rs_i], r1
    b .loop
.erase:
	ld r1, [rs_i]
	eq r1, #0				; nothing typed, nothing to take back
	bzf .loop
	sub r1, #1
	st [rs_i], r1
	; back, space, back, so the character goes from the screen too
	mov r0, #8
	push pch
	push pcl
	b print_ascii_char
	mov r0, #32
	push pch
	push pcl
	b print_ascii_char
	mov r0, #8
	push pch
	push pcl
	b print_ascii_char
	b .loop
.done:
    ld r1, [rs_i]
  mov r0, #13
  std [rs_msg_addr]+r1, r0
  add r1, #1
  xor r0, r0
  std [rs_msg_addr]+r1, r0
    pop pcl
    pop pch

; dump_char_rom dumped the C64 font through the old pixel path; gone with it

str_printuint16:
	pop pcl
	pop pch

ps_msg_addr: resb 2
ps_i: resb 1
str_printstr:
print_string:
	; r0 - high address of string
	; r1 = low address of string
;
;	; first store string address in memory
	st [ps_msg_addr], r1
	st [ps_msg_addr+1], r0

	; loop through string until null terminator
    xor r1, r1
;    st [posx], r1
;    st [posy], r1
    st [ps_i], r1
.loop:
    ldd r0, [ps_msg_addr]+r1
    eq r0, #0
    bzf .done
    push pch
    push pcl
    b print_ascii_char
    ld r1, [ps_i]
    add r1, #1
    st [ps_i], r1
    b .loop
.done:
    pop pcl
    pop pch

; print_char rendered glyphs pixel by pixel; the graphics card does it now

;cd_end: resb 1
;fill_screen_pixels:
;    ; [testing routine]
;    ; fill screen with pixels (slow)
;
;    xor r1, r1
;    st [posx], r1
;    st [posy], r1
;.draw_pixel:
;    push #255
;
;    ld r1, [posy]
;    push r1     ; y
;
;    ld r1, [posx]
;    push r1     ; x
;
;    push pch
;    push pcl
;    b st7735_draw_pixel
;
;    ld r1, [posx]
;    add r1, #1
;    st [posx], r1
;    eq r1, #0   ; 256
;    bzf .next
;    b .draw_pixel
;.next:
;    xor r1, r1
;    st [posx], r1
;
;    ld r1, [posy]
;    add r1, #1
;    st [posy], r1
;    eq r1, #255
;    bzf .done
;    b .draw_pixel
;.done:
;    pop pcl
;    pop pch
;
; clearing the screen is the graphics card's CLS (API_CLS; BASIC's clr)

str_len_ptr: resb 2
str_len:
	st [str_len_ptr], r1
	st [str_len_ptr+1], r0

	xor r0, r0
.loop:
	ldd r1, [str_len_ptr]+r0
	eq r1, #0
	bzf .done
	add r0, #1
	b .loop

.done:
	pop pcl
	pop pch
