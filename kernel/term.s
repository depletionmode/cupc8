
term_basic_prog_buf_idx: resb 1
term_basic_prog_buf: resb 256

term_line_buf: resb 40

term_do:
	term_s_info db "\n      CUPC/8 BASIC 2015.10      \n\n"
	mov r0, #>[term_s_info]
	mov r1, #<[term_s_info]
	push pch
	push pcl
	b str_printstr

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
term_token_buf: resb 40
term_get_token:
	; r0 - token number
	push r0

	; copy line into token buffer
	mov r0, #>[term_token_buf]
	mov r1, #<[term_token_buf]
	push pch
	push pcl
	b str_cpy_set
	mov r0, #>[term_line_buf]
	mov r1, #<[term_line_buf]
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
	mov r0, #>[term_token_buf]
	mov r1, #<[term_token_buf]
	push pch
	push pcl
	b str_cpy_set
	pop r0
	mov r1, #<[term_line_buf]
	add r1, r0
	lt r1, r0
	mov r0, #>[term_line_buf]
	bzf .carry
	b .nocarry
.carry:
	add r0, #1
.nocarry:
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
	mov r0, #>[term_line_buf]
	mov r1, #<[term_line_buf]
	push pch
	push pcl
	b read_string

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
	bzf .num
	push pch
	push pcl
	b term_cmd_run
	b .done

.num:
	mov r0, #>[term_token_buf]
	mov r1, #<[term_token_buf]
	push pch
	push pcl
	b str_atoi
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

term_basic_prog_ptr: resb 2
term_cmd_basicline:
	mov r0, #>[term_basic_prog_buf]
	st [term_basic_prog_ptr+1], r0
	mov r1, #<[term_basic_prog_buf]
	ld r0, [term_basic_prog_buf_idx]
	add r1, r0
	st [term_basic_prog_ptr], r1
	lt r1, r0
	bzf .carry
	b .nocarry
.carry:
	mov r0, #>[term_basic_prog_buf]
	add r0, #1
	st [term_basic_prog_ptr+1], r0
.nocarry:
	ld r0, [term_basic_prog_ptr+1]
	ld r1, [term_basic_prog_ptr]
	push pch
	push pcl
	b mem_cpy_set0
	mov r0, #>[term_line_buf]
	mov r1, #<[term_line_buf]
	push pch
	push pcl
	b mem_cpy_set1
	mov r0, #>[term_line_buf]
	mov r1, #<[term_line_buf]
	push pch
	push pcl
	b str_len
	push r0
	push pch
	push pcl
	b mem_cpy

	ld r1, [term_basic_prog_buf_idx]
	pop r0
	add r1, r0
	st [term_basic_prog_buf_idx], r1

.done:
	pop pcl
	pop pch

term_cmd_help:
	; show help

	term_s_help_buf db "\nNEW RUN CLEAR\n"
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

	mov r0, #>[term_basic_prog_buf]
	mov r1, #<[term_basic_prog_buf]
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
	; reset basic program buffer

	xor r1, r1
.loop:
	ld r0, [term_basic_prog_buf_idx]
	gt r1, r0
	bzf .zeroed
	xor r0, r0
	st [term_basic_prog_buf]+r1, r0
	add r1, #1
	b .loop

.zeroed:
	xor r0, r0
	st [term_basic_prog_buf_idx], r0

.done:
	pop pcl
	pop pch

term_cmd_basic_statement:
	; copy basic statement into program buffer
.done:
	pop pcl
	pop pch
