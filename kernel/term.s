
; The BASIC program is text at $c000-$dfff, the top 8 KB of the user area
; (memory-map.md): each line as typed, ending in a CR, then a 0.
; term_basic_prog_buf_idx is its length. A program for $7000 bigger than
; 20 KB goes over it.
%define TERM_PROG_HI #0xc0
term_basic_prog_buf_idx: resb 2
term_full: resb 1			; the last line was refused (PROGRAM FULL)

term_line_buf: resb 80

term_do:
	; start with an empty program: .bss is not cleared, and the SRAM
	; powers up with junk
	xor r0, r0
	st [term_basic_prog_buf_idx], r0
	st [term_basic_prog_buf_idx+1], r0
	st $c000, r0
	st API_RUN, r0			; no program from the PC yet

	term_s_info db "\n      CUPC/8 BASIC 2026.09      \n"
	mov r0, #>[term_s_info]
	mov r1, #<[term_s_info]
	push pch
	push pcl
	b str_printstr

	; the stack as it is at the prompt, where a program's end takes it back
	push pch
	push pcl
	b sys_mark

.loop:
	push pch
	push pcl
	b term_prompt

	push pch
	push pcl
	b term_parse

	b .loop

.done:
	pop pcl
	pop pch

term_token_num: resb 1
term_token_buf: resb 80
term_get_token:
	; r0 - token number
	push r0

	; copy line into token buffer
	mov r1, #<[term_token_buf]
	push r1
	mov r1, #>[term_token_buf]
	push r1

	mov r1, #<[term_line_buf]
	push r1
	mov r1, #>[term_line_buf]
	push r1

	push pch
	push pcl
	b str_cpy

	xor r0, r0
	st [term_token_num], r0
.loop:
	ld r1, [term_token_buf]+r0
	eq r1, #32
	bzf .whitespace_found
	eq r1, #10
	bzf .whitespace_found
	eq r1, #13
	bzf .whitespace_found
	eq r1, #0
	bzf .whitespace_found
	add r0, #1
	b .loop

.whitespace_found:
	; null terminate token
	xor r1, r1
	st [term_token_buf]+r0, r1

	pop r1
	push r0

	; see if at wanted token
	ld r0, [term_token_num]
	eq r0, r1
	add r0, #1
	st [term_token_num], r0
	pop r0
	bzf .done
	push r0

.not_at_token:
	; cut token from token buffer
	pop r0

	mov r1, #<[term_token_buf]
	push r1
	mov r1, #>[term_token_buf]
	push r1

	mov r1, #<[term_line_buf]
	add r1, r0
	lt r1, r0
	mov r0, #>[term_line_buf]
	bzf .carry
	b .nocarry
.carry:
	add r0, #1
.nocarry:
	push r1
	push r0


	push pch
	push pcl
	b str_cpy
	xor r0, r0
	b .loop

.done:
	pop pcl
	pop pch

term_prompt:
	; echo on
	mov r0, #1
	push pch
	push pcl
	b set_echo_char

	term_s_prompt db "\n>> "
	mov r0, #>[term_s_prompt]
	mov r1, #<[term_s_prompt]
	push pch
	push pcl
	b str_printstr

.read_string:
	mov r0, #1				; a program from the PC may start meanwhile
	st [keyb_term], r0
	mov r0, #>[term_line_buf]
	mov r1, #<[term_line_buf]
	push pch
	push pcl
	b read_string
	xor r0, r0
	st [keyb_term], r0

	term_s_cr db "\n"
	mov r0, #>[term_s_cr]
	mov r1, #<[term_s_cr]
	push pch
	push pcl
	b str_printstr

.done:
	pop pcl
	pop pch

term_parse:
	xor r0, r0
	push pch
	push pcl
	b term_get_token	; get first token (cmd)

	mov r0, #>[term_token_buf]
	mov r1, #<[term_token_buf]
	push pch
	push pcl
	b str_cmp_set
	ld r0, [term_token_buf]

.help:
	term_s_help db "help"
	mov r0, #>[term_s_help]
	mov r1, #<[term_s_help]
	push pch
	push pcl
	b str_cmp
	gt r0, #0
	bzf .new
	push pch
	push pcl
	b term_cmd_help
	b .done

.new:
	term_s_new db "new"
	mov r0, #>[term_s_new]
	mov r1, #<[term_s_new]
	push pch
	push pcl
	b str_cmp
	gt r0, #0
	bzf .run
	push pch
	push pcl
	b term_cmd_new
	b .done

.run:
	term_s_run db "run"
	mov r0, #>[term_s_run]
	mov r1, #<[term_s_run]
	push pch
	push pcl
	b str_cmp
	gt r0, #0
	bzf .clr
	push pch
	push pcl
	b term_cmd_run
	b .done

.clr:
	term_s_clr db "clr"
	mov r0, #>[term_s_clr]
	mov r1, #<[term_s_clr]
	push pch
	push pcl
	b str_cmp
	gt r0, #0
	bzf .net
	push pch
	push pcl
	b term_cmd_clr
	b .done

.net:
	term_s_net db "net"
	mov r0, #>[term_s_net]
	mov r1, #<[term_s_net]
	push pch
	push pcl
	b str_cmp
	gt r0, #0
	bzf .list
	mov r0, #<[term_line_buf]
	st [net_line], r0
	mov r0, #>[term_line_buf]
	st [net_line+1], r0
	push pch
	push pcl
	b net_cmd
	b .done

.list:
	term_s_list db "list"
	mov r0, #>[term_s_list]
	mov r1, #<[term_s_list]
	push pch
	push pcl
	b str_cmp
	gt r0, #0
	bzf .save
	push pch
	push pcl
	b term_cmd_list
	b .done

.save:
	term_s_save db "save"
	mov r0, #>[term_s_save]
	mov r1, #<[term_s_save]
	push pch
	push pcl
	b str_cmp
	gt r0, #0
	bzf .load
	push pch
	push pcl
	b ub_cmd_save
	b .done

.load:
	term_s_load db "load"
	mov r0, #>[term_s_load]
	mov r1, #<[term_s_load]
	push pch
	push pcl
	b str_cmp
	gt r0, #0
	bzf .dir
	push pch
	push pcl
	b ub_cmd_load
	b .done

.dir:
	term_s_dir db "dir"
	mov r0, #>[term_s_dir]
	mov r1, #<[term_s_dir]
	push pch
	push pcl
	b str_cmp
	gt r0, #0
	bzf .del
	push pch
	push pcl
	b ub_cmd_dir
	b .done

.del:
	term_s_del db "del"
	mov r0, #>[term_s_del]
	mov r1, #<[term_s_del]
	push pch
	push pcl
	b str_cmp
	gt r0, #0
	bzf .refresh
	push pch
	push pcl
	b ub_cmd_del
	b .done

.refresh:
	term_s_refresh db "refresh"
	mov r0, #>[term_s_refresh]
	mov r1, #<[term_s_refresh]
	push pch
	push pcl
	b str_cmp
	gt r0, #0
	bzf .exec
	push pch
	push pcl
	b eink_cmd_refresh
	b .done

.exec:
	term_s_exec db "exec"
	mov r0, #>[term_s_exec]
	mov r1, #<[term_s_exec]
	push pch
	push pcl
	b str_cmp
	gt r0, #0
	bzf .num
	push pch
	push pcl
	b sys_cmd_exec
	b .done

.num:
	mov r0, #>[term_token_buf]
	mov r1, #<[term_token_buf]
	push pch
	push pcl
	b str_atoi
	gt r1, #0x7f			; a line number is 1-32767
	bzf .invalid
	or r0, r1
	eq r0, #0
	bzf .invalid
	b term_cmd_basicline
	b .done

.invalid:
	term_s_invalid_cmd db "\nERROR: invalid cmd!\n"
	mov r0, #>[term_s_invalid_cmd]
	mov r1, #<[term_s_invalid_cmd]
	push pch
	push pcl
	b str_printstr

.done:
	pop pcl
	pop pch

term_cmd_clr:
	push pch
	push pcl
	b clr_screen
.done:
	pop pcl
	pop pch

; list- print the program as it is kept, each line's CR as a new line
term_list_i: resb 2
term_list_p: resb 2
term_cmd_list:
	xor r0, r0
	st [term_list_i], r0
	st [term_list_i+1], r0
.loop:
	ld r1, [term_list_i]			; stop at the length
	ld r0, [term_basic_prog_buf_idx]
	eq r1, r0
	bzf .lo_same
	b .byte
.lo_same:
	ld r1, [term_list_i+1]
	ld r0, [term_basic_prog_buf_idx+1]
	eq r1, r0
	bzf .done
.byte:
	ld r0, [term_list_i]
	st [term_list_p], r0
	ld r0, [term_list_i+1]
	add r0, TERM_PROG_HI
	st [term_list_p+1], r0
	ldd r0, [term_list_p]
	eq r0, #13
	bzf .newline
	b .put
.newline:
	mov r0, #10
.put:
	push pch
	push pcl
	b print_ascii_char
	ld r0, [term_list_i]
	add r0, #1
	st [term_list_i], r0
	eq r0, #0
	bzf .carry
	b .loop
.carry:
	ld r0, [term_list_i+1]
	add r0, #1
	st [term_list_i+1], r0
	b .loop
.done:
	pop pcl
	pop pch

; A typed line into the program, which is kept in line-number order: it goes
; in its place, replaces the line of its number, and a line number alone
; (spaces after it are fine) deletes that line. The rest of the program moves
; up or down by the change; PROGRAM FULL if the program would end past
; $dfff. term_v holds 16-bit pointers, low first:
;  0 a move's from, 2 its to, 4 the from it stops at (term_move)
;  6 the typed line's place, 8 past the line there if that has the typed
;    line's number (else the place), 10 the program's end, its 0
term_v: resb 12
term_step: resb 2			; what term_add adds - the move's step
term_ln: resb 2				; the typed line's number
term_new: resb 1			; the typed line's length with its CR, 0 for just a number
term_cmd_basicline:
	xor r0, r0
	st [term_full], r0
	st [term_step+1], r0
	mov r0, #>[term_line_buf]
	mov r1, #<[term_line_buf]
	push pch
	push pcl
	b str_atoi
	st [term_ln], r0
	st [term_ln+1], r1
	ld r0, [term_basic_prog_buf_idx]	; the end - $c000 + the length
	st [term_v+10], r0
	st [term_v+8], r0
	ld r0, [term_basic_prog_buf_idx+1]
	add r0, TERM_PROG_HI
	st [term_v+11], r0
	st [term_v+9], r0
	; typing a program in order adds each line at the end, so first the last
	; line - the one after the CR before the end's CR, or the first
	ld r0, [term_basic_prog_buf_idx]
	ld r1, [term_basic_prog_buf_idx+1]
	or r0, r1
	eq r0, #0
	bzf .at_end				; an empty program
	mov r0, #0xff
	st [term_step], r0
	st [term_step+1], r0
	mov r1, #8
	push pch
	push pcl
	b term_add
.back:
	mov r1, #8
	push pch
	push pcl
	b term_add
	ld r0, [term_v+9]
	eq r0, #0xbf
	bzf .last
	ldd r0, [term_v+8]
	eq r0, #13
	bzf .last
	b .back
.last:
	mov r0, #1
	st [term_step], r0
	xor r0, r0
	st [term_step+1], r0
	mov r1, #8
	push pch
	push pcl
	b term_add
	ld r0, [term_v+9]
	ld r1, [term_v+8]
	push pch
	push pcl
	b term_cmp
	eq r0, #1
	bzf .at_end				; the last line's number is smaller
	xor r0, r0				; else from the first line
	st [term_v+6], r0
	mov r0, TERM_PROG_HI
	st [term_v+7], r0
.find:
	ld r0, [term_v+6]
	st [term_v+8], r0
	ld r0, [term_v+7]
	st [term_v+9], r0
	ldd r0, [term_v+6]
	eq r0, #0
	bzf .placed				; the program's end
	ld r0, [term_v+7]
	ld r1, [term_v+6]
	push pch
	push pcl
	b term_cmp
	eq r0, #2
	bzf .placed				; a bigger number - the typed line goes before it
	push r0
	xor r1, r1				; past the line's CR
.eol:
	ldd r0, [term_v+6]+r1
	add r1, #1
	eq r0, #13
	bzf .eol_found
	b .eol
.eol_found:
	st [term_step], r1
	mov r1, #8
	push pch
	push pcl
	b term_add
	pop r0
	eq r0, #0
	bzf .placed				; the same number - the typed line replaces it
	ld r0, [term_v+8]		; a smaller number - on to the next line
	st [term_v+6], r0
	ld r0, [term_v+9]
	st [term_v+7], r0
	b .find
.at_end:
	ld r0, [term_v+10]
	st [term_v+6], r0
	st [term_v+8], r0
	ld r0, [term_v+11]
	st [term_v+7], r0
	st [term_v+9], r0
.placed:
	xor r1, r1
.scan:						; a line number alone?
	ld r0, [term_line_buf]+r1
	add r1, #1
	eq r0, #13
	bzf .delete
	eq r0, #32
	bzf .scan
	lt r0, #48
	bzf .text
	gt r0, #57
	bzf .text
	b .scan
.text:
	ld r1, [rs_i]
	add r1, #1
	b .length
.delete:
	xor r1, r1
.length:
	st [term_new], r1
	; the program grows by k - the typed line's length less the old line's
	; (under 80 each, so the low bytes do), the step k sign-extended
	mov r0, r1
	ld r1, [term_v+8]
	sub r0, r1
	ld r1, [term_v+6]
	add r0, r1
	st [term_step], r0
	xor r1, r1
	st [term_step+1], r1
	eq r0, #0
	bzf .shrink
	gt r0, #0x7f
	bzf .negative
	; it grows - the end moves up by k, the rest from the end down to the
	; old line's end, a byte at a time
	ld r0, [term_v+10]
	st [term_v], r0
	ld r0, [term_v+11]
	st [term_v+1], r0
	mov r1, #10
	push pch
	push pcl
	b term_add
	ld r0, [term_v+11]
	eq r0, #0xe0
	bzf .full				; the new end is past $dfff
	ld r0, [term_v+10]
	st [term_v+2], r0
	ld r0, [term_v+11]
	st [term_v+3], r0
	ld r0, [term_v+8]
	st [term_v+4], r0
	ld r0, [term_v+9]
	st [term_v+5], r0
	mov r0, #0xff
	st [term_step], r0
	st [term_step+1], r0
	mov r1, #4
	push pch
	push pcl
	b term_add
	b .move
.negative:
	mov r1, #0xff
	st [term_step+1], r1
.shrink:					; the rest from the old line's end up, down by k
	ld r0, [term_v+10]
	st [term_v+4], r0
	ld r0, [term_v+11]
	st [term_v+5], r0
	mov r1, #10
	push pch
	push pcl
	b term_add
	ld r0, [term_v+8]
	st [term_v], r0
	st [term_v+2], r0
	ld r0, [term_v+9]
	st [term_v+1], r0
	st [term_v+3], r0
	mov r1, #2
	push pch
	push pcl
	b term_add
	mov r0, #1
	st [term_step], r0
	xor r0, r0
	st [term_step+1], r0
	mov r1, #4
	push pch
	push pcl
	b term_add
.move:
	push pch
	push pcl
	b term_move
	; the typed line into its place
	mov r0, #<[term_line_buf]
	st [term_v], r0
	st [term_v+4], r0
	mov r0, #>[term_line_buf]
	st [term_v+1], r0
	st [term_v+5], r0
	ld r0, [term_v+6]
	st [term_v+2], r0
	ld r0, [term_v+7]
	st [term_v+3], r0
	xor r0, r0
	st [term_step+1], r0
	ld r0, [term_new]
	st [term_step], r0
	mov r1, #4
	push pch
	push pcl
	b term_add
	mov r0, #1
	st [term_step], r0
	push pch
	push pcl
	b term_move
	ld r0, [term_v+10]		; the length - the new end less $c000
	st [term_basic_prog_buf_idx], r0
	ld r0, [term_v+11]
	sub r0, TERM_PROG_HI
	st [term_basic_prog_buf_idx+1], r0
	b .done
.full:
	mov r0, #1
	st [term_full], r0
	term_s_full db "\nPROGRAM FULL\n"
	mov r0, #>[term_s_full]
	mov r1, #<[term_s_full]
	push pch
	push pcl
	b str_printstr
.done:
	pop pcl
	pop pch

; compare the number the line at r0 (high), r1 (low) starts with to the typed
; line's - r0 0 the same, 1 smaller, 2 bigger
term_cmp:
	push pch
	push pcl
	b str_atoi
	st [n_a], r0
	st [n_a+1], r1
	ld r0, [term_ln]
	st [n_b], r0
	ld r0, [term_ln+1]
	st [n_b+1], r0
	push pch
	push pcl
	b n16_cmp
	pop pcl
	pop pch

; the 16 bits at term_v + r1 plus term_step
term_add:
	ld r0, [term_v]+r1
	push r1
	ld r1, [term_step]
	add r0, r1
	lt r0, r1				; carried
	pop r1
	st [term_v]+r1, r0
	ld r0, [term_v+1]+r1
	bzf .carry
	b .high
.carry:
	add r0, #1
.high:
	push r1
	ld r1, [term_step+1]
	add r0, r1
	pop r1
	st [term_v+1]+r1, r0
	pop pcl
	pop pch

; copy a byte at a time from term_v+0 to term_v+2, stepping both by
; term_step, until the from is term_v+4
term_move:
.loop:
	ld r0, [term_v]
	ld r1, [term_v+4]
	eq r0, r1
	bzf .low_same
	b .byte
.low_same:
	ld r0, [term_v+1]
	ld r1, [term_v+5]
	eq r0, r1
	bzf .done
.byte:
	ldd r0, [term_v]
	std [term_v+2], r0
	xor r1, r1
	push pch
	push pcl
	b term_add
	mov r1, #2
	push pch
	push pcl
	b term_add
	b .loop
.done:
	pop pcl
	pop pch

term_cmd_help:
	; show help

	term_s_help_buf db "\nNEW RUN LIST CLR NET SAVE LOAD DIR DEL REFRESH EXEC\nBASIC: LET PRINT IF THEN ELSE FOR TO NEXT GOTO GOSUB RETURN REM END\nPEEK POKE MODE CLS COLOR PLOT LINE BOX PALETTE REFRESH\n"
	mov r0, #>[term_s_help_buf]
	mov r1, #<[term_s_help_buf]
	push pch
	push pcl
	b str_printstr

.done:
	pop pcl
	pop pch

term_cmd_run:
	; run program in BASIC program buffer

	mov r0, TERM_PROG_HI
	xor r1, r1
	push pch
	push pcl
	b ubasic_init
.loop:
	push pch
	push pcl
	b ubasic_run
	push pch
	push pcl
	b ubasic_finished
	eq r0, #0
	bzf .loop
	push pch
	push pcl
	b ubasic_gfx_done

	term_s_done db "\nDONE.\n"
	mov r0, #>[term_s_done]
	mov r1, #<[term_s_done]
	push pch
	push pcl
	b str_printstr

.done:
	pop pcl
	pop pch

term_cmd_new:
	; an empty program
	xor r0, r0
	st [term_basic_prog_buf_idx], r0
	st [term_basic_prog_buf_idx+1], r0
	st $c000, r0

.done:
	pop pcl
	pop pch

term_cmd_basic_statement:
	; copy basic statement into program buffer
.done:
	pop pcl
	pop pch
