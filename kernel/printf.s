; routines for printing text

; global variables
mem_p_dst: resb 2
mem_p_src: resb 2

; print_ascii_char / print_ascii_char_inverse now live in gpu.s

g_echo_char: resb 1
set_echo_char:
	st [g_echo_char], r0
    pop pcl
    pop pch

rs_msg_addr: resb 2
rs_i: resb 1
read_string:
	; r0 - high address of string
	; r1 = low address of string
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
	; check if echo
	ld r1, [g_echo_char]
	eq r1, #1
	bzf .echo
	b .cont
.echo:
    push pch
    push pcl
    b print_ascii_char
.cont:
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
	ld r1, [g_echo_char]
	eq r1, #1
	bzf .erase_echo
	b .loop
.erase_echo:				; back, space, back, so the character goes from the screen too
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

str_uint_rem: resb 1
str_uint_buf: resb 5
str_printuint8:
	xor r1, r1
	gt r0, #0
	bzf .gt0
	mov r1, #48
	st [str_uint_buf], r1
	mov r1, #1
	b .done

.gt0:
.loop:
	eq r0, #0
	bzf .done
	push r1		; idx

	mov r1, r0	; num
	push r1
	mov r1, #10
	push pch
	push pcl
	b math_div
	mov r0, r1
	pop r1		; num
	st [str_uint_rem], r0
	mov r0, r1

	ld r1, [str_uint_rem]
	gt r1, #9
	bzf .gt9
	add r1, #48
	b .after_gt9
.gt9:
	sub r1, #10
	add r1, #97
.after_gt9:
	st [str_uint_rem], r1
	pop r1		; idx
	push r0		; num
	ld r0, [str_uint_rem]
	st [str_uint_buf]+r1, r0
	pop r0		; num
	push r1
	mov r1, #10
	push pch
	push pcl
	b math_div
	pop r1
	add r1, #1
	b .loop

.done:
	xor r0, r0
	st [str_uint_buf]+r1, r0
	mov r0, #>[str_uint_buf]
	mov r1, #<[str_uint_buf]
	push pch
	push pcl
	b str_reverse
	mov r0, #>[str_uint_buf]
	mov r1, #<[str_uint_buf]
	push pch
	push pcl
	b str_printstr
	pop pcl
	pop pch

str_printuint16:
	pop pcl
	pop pch

str_printstr:
	push pch
	push pcl
	b print_string
	pop pcl
	pop pch

ps_msg_addr: resb 2
ps_i: resb 1
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
; clr_screen is now the graphics card's CLS (gpu.s)

str_int_addr: resb 2
; the decimal number at the pointer r0 (high), r1 (low): r0 = its low byte,
; r1 = its high byte (16 bits, wrapping; 0 if it does not start with a digit)
str_atoi:
	st [str_int_addr], r1
	st [str_int_addr+1], r0
	xor r1, r1
	st [n_a], r1
	st [n_a+1], r1
.loop:
	ldd r0, [str_int_addr]+r1
	lt r0, #48
	bzf .done
	gt r0, #57
	bzf .done
	push r1
	sub r0, #48
	push r0
	push pch				; n_a * 10 - (n_a * 2) + (n_a * 2) * 4
	push pcl
	b n16_shl1
	ld r0, [n_a]
	st [n_b], r0
	ld r0, [n_a+1]
	st [n_b+1], r0
	push pch
	push pcl
	b n16_shl1
	push pch
	push pcl
	b n16_shl1
	push pch
	push pcl
	b n16_add
	pop r0					; + the digit
	st [n_b], r0
	xor r0, r0
	st [n_b+1], r0
	push pch
	push pcl
	b n16_add
	pop r1
	add r1, #1
	b .loop
.done:
	ld r0, [n_a]
	ld r1, [n_a+1]
	pop pcl
	pop pch

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

str_cmp_ptr0: resb 2
str_cmp_set:
	st [str_cmp_ptr0], r1
	st [str_cmp_ptr0+1], r0

	pop pcl
	pop pch

str_cmp_mismatch: resb 1
str_cmp_pos: resb 1
str_cmp_ptr1: resb 2
str_cmp:
	st [str_cmp_ptr1], r1
	st [str_cmp_ptr1+1], r0

	xor r1, r1
	st [str_cmp_pos], r1
.loop:
	ld r1, [str_cmp_pos]
	ldd r0, [str_cmp_ptr0]+r1
	ldd r1, [str_cmp_ptr1]+r1
  sub r1, r0
  st [str_cmp_mismatch], r1
  gt r1, #0
  bzf .done
	eq r0, #0
	bzf .done

	ld r1, [str_cmp_pos]
  add r1, #1
  st [str_cmp_pos], r1
  b .loop

.done:
	ld r0, [str_cmp_mismatch]
	pop pcl
	pop pch

str_cpy_pc: resb 2
str_cpy_len: resb 1
str_cpy:
	; args on stack:
	;  src >> 8
    ;  src
	;  dst >> 8
	;  dst
	pop r0
	pop r1
	st [str_cpy_pc], r0
	st [str_cpy_pc+1], r1

	pop r0
	st [mem_p_src+1], r0
	pop r1
	st [mem_p_src], r1
	pop r0
	st [mem_p_dst+1], r0
	pop r1
	st [mem_p_dst], r1

	ld r1, [mem_p_dst]
	push r1
	ld r0, [mem_p_dst+1]
	push r0

	ld r1, [mem_p_src]
	push r1
	ld r0, [mem_p_src+1]
	push r0

	push pch
	push pcl
	b str_len
	st [str_cpy_len], r0

	push pch
	push pcl
	b mem_cpy

  xor r0, r0
	ld r1, [str_cpy_len]
  std [mem_p_dst]+r1, r0
.done:
	ld r0, [str_cpy_pc]
	ld r1, [str_cpy_pc+1]
	push r1
	push r0
	ld r0, [str_cpy_len]	; return length of string copied
	pop pcl
	pop pch

mem_cpy_pc: resb 2
mem_cpy:
	; length in r0
	; args on stack:
	;  src >> 8
    ;  src
	;  dst >> 8
	;  dst

	; save pc
	pop r1
	st [mem_cpy_pc], r1
	pop r1
	st [mem_cpy_pc+1], r1

	pop r1
	st [mem_p_src+1], r1
	pop r1
	st [mem_p_src], r1

	pop r1
	st [mem_p_dst+1], r1
	pop r1
	st [mem_p_dst], r1

	push r0
.loop:
	pop r0
	eq r0, #0
	bzf .done
	push r0
	mov r1, r0
	sub r1, #1
	ldd r0, [mem_p_src]+r1
	std [mem_p_dst]+r1, r0
	pop r0
	sub r0, #1
	push r0
	b .loop

.done:
	; restore pc
	ld r1, [mem_cpy_pc+1]
	push r1
	ld r1, [mem_cpy_pc]
	push r1

	pop pcl
	pop pch

str_rev_i: resb 1
str_rev_ptr: resb 2
str_reverse:
	st [str_rev_ptr], r1
	st [str_rev_ptr+1], r0

	xor r0, r0
	st [str_rev_i], r0
.loop0:
	ldd r1, [str_rev_ptr]+r0
	eq r1, #0
	bzf .loop1
	push r1
	add r0, #1
	b .loop0

.loop1:
	eq r0, #0
	bzf .done
	pop r1
	push r0
	ld r0, [str_rev_i]
	std [str_rev_ptr]+r0, r1
	add r0, #1
	st [str_rev_i], r0
	pop r0
	sub r0, #1
	b .loop1

.done:
	pop pcl
	pop pch
