
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
	push pch
	push pcl
	b term_cmd_new
	xor r0, r0
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

; ------------------------------------------------------------ program editing
; A typed line into the program, which is kept in line-number order: it goes
; in its place, replaces the line of its number, and a line number alone
; (spaces after it are fine) deletes that line. The rest of the program moves
; by the difference (API_MEM_CPY, a memmove); PROGRAM FULL if the program
; would end past $dfff. A line numbered above the last one typed is looked
; for from that one's place on (term_p), so a program typed or loaded in
; order is quick. The work is in API_ARGS ($6f00): +2 the old line's end
; while looking, then API_MEM_CPY's dst, src and len; +6 the new length.
; This part uses the kernel through the API, str_atoi and n16_cmp only.
%define API_MEM_CPY $101e
term_p: resb 2				; the last typed line's place ($c000 after new)
term_ln: resb 2				; the typed line's number
term_new: resb 1			; the typed line's length with its CR, 0 for just a number
term_d: resb 2				; what term_add adds
term_cmd_basicline:
	xor r0, r0
	st [term_full], r0
	mov r0, #>[term_line_buf]
	mov r1, #<[term_line_buf]
	push pch
	push pcl
	b term_cmp				; 2 if above the last typed line
	push r0
	ld r0, [n_a]
	st [term_ln], r0
	ld r0, [n_a+1]
	st [term_ln+1], r0
	pop r0
	eq r0, #2
	bzf .find
	xor r0, r0				; else from the first line
	st [term_p], r0
	mov r0, TERM_PROG_HI
	st [term_p+1], r0
.find:
	ld r0, [term_p]			; the old line's end - the place, for now
	st $6f02, r0
	ld r0, [term_p+1]
	st $6f03, r0
	ldd r0, [term_p]
	eq r0, #0
	bzf .placed				; the program's end
	ld r0, [term_p+1]
	ld r1, [term_p]
	push pch
	push pcl
	b term_cmp
	eq r0, #2
	bzf .placed				; a bigger number - the typed line goes before it
	push r0
	xor r1, r1
.eol:
	ldd r0, [term_p]+r1
	add r1, #1
	eq r0, #13
	bzf .eol_found
	b .eol
.eol_found:
	st [term_d], r1			; past the line's CR
	xor r0, r0
	st [term_d+1], r0
	mov r1, #2
	push pch
	push pcl
	b term_add
	pop r0
	eq r0, #0
	bzf .placed				; the same number - the typed line replaces it
	ld r0, $6f02			; a smaller number - on to the next line
	st [term_p], r0
	ld r0, $6f03
	st [term_p+1], r0
	b .find
.placed:
	; the bytes from the old line's end to the program's 0, that included -
	; the length + 1 less (the end - $c000)
	ld r0, [term_basic_prog_buf_idx]
	ld r1, $6f02
	lt r0, r1				; a borrow
	sub r0, r1
	st $6f04, r0
	ld r0, [term_basic_prog_buf_idx+1]
	add r0, TERM_PROG_HI
	ld r1, $6f03
	sub r0, r1
	bzf .borrow
	b .count_hi
.borrow:
	sub r0, #1
.count_hi:
	st $6f05, r0
	mov r0, #1
	st [term_d], r0
	xor r0, r0
	st [term_d+1], r0
	mov r1, #4
	push pch
	push pcl
	b term_add
	; the typed line's length, 0 for a line number alone
	ld r1, [rs_i]
	add r1, #1
	st [term_new], r1
	xor r1, r1
.scan:
	ld r0, [term_line_buf]+r1
	add r1, #1
	eq r0, #32
	bzf .scan
	sub r0, #48
	lt r0, #10
	bzf .scan
	eq r0, #221				; its CR, 13 - 48
	bzf .delete
	b .text
.delete:
	xor r0, r0
	st [term_new], r0
.text:
	; the program grows by k - the typed line's length less the old line's
	; (under 80 each, so the low bytes do) - sign-extended into term_d
	ld r0, [term_new]
	ld r1, $6f02
	sub r0, r1
	ld r1, [term_p]
	add r0, r1
	st [term_d], r0
	xor r1, r1
	gt r0, #0x7f
	bzf .negative
	b .signed
.negative:
	mov r1, #0xff
.signed:
	st [term_d+1], r1
	ld r0, [term_basic_prog_buf_idx]	; the new length, at most $1fff
	st $6f06, r0
	ld r0, [term_basic_prog_buf_idx+1]
	st $6f07, r0
	mov r1, #6
	push pch
	push pcl
	b term_add
	ld r0, $6f07
	gt r0, #0x1f
	bzf .full
	ld r0, $6f06
	st [term_basic_prog_buf_idx], r0
	ld r0, $6f07
	st [term_basic_prog_buf_idx+1], r0
	ld r0, $6f02			; the rest to the old line's end + k
	st $6f00, r0
	ld r0, $6f03
	st $6f01, r0
	xor r1, r1
	push pch
	push pcl
	b term_add
	push pch
	push pcl
	b API_MEM_CPY
	ld r0, [term_p]			; the typed line into its place
	st $6f00, r0
	ld r0, [term_p+1]
	st $6f01, r0
	mov r0, #<[term_line_buf]
	st $6f02, r0
	mov r0, #>[term_line_buf]
	st $6f03, r0
	ld r0, [term_new]
	st $6f04, r0
	xor r0, r0
	st $6f05, r0
	push pch
	push pcl
	b API_MEM_CPY
	pop pcl
	pop pch
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

; the number the text at r0 (high), r1 (low) starts with, into n_a, against
; the typed line's (term_ln) - r0 0 the same, 1 less, 2 greater
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
	b n16_cmp

; the 16 bits at API_ARGS + r1 plus term_d
term_add:
	ld r0, $6f00+r1
	push r1
	ld r1, [term_d]
	add r0, r1
	lt r0, r1				; carried
	pop r1
	st $6f00+r1, r0
	add r1, #1
	ld r0, $6f00+r1
	bzf .carry
	b .high
.carry:
	add r0, #1
.high:
	push r1
	ld r1, [term_d+1]
	add r0, r1
	pop r1
	st $6f00+r1, r0
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
	st [term_p], r0			; lines are looked for from the first
	mov r0, TERM_PROG_HI
	st [term_p+1], r0

.done:
	pop pcl
	pop pch

term_cmd_basic_statement:
	; copy basic statement into program buffer
.done:
	pop pcl
	pop pch
