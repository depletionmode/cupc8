
term_basic_prog_buf_idx: resb 1
term_basic_prog_buf: resb 256

term_line_buf: resb 40

term:
.loop:
	push pch
	push pcl
	b term_prompt

	push pch
	push pcl
	b term_parse

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
	str_cpy_set
	mov r0, #>[term_line_buf]
	mov r1, #<[term_line_buf]
	push pch
	push pcl
	str_cpy

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
	bzf .found

.not_at_token:

	; cut toekn from token buffer
	mov r0, #>[term_token_buf]
	mov r1, #<[term_token_buf]
	push pch
	push pcl
	str_cpy_set
	mov r0, #>[term_line_buf]
	mov r1, #<[term_line_buf]
	push pch
	push pcl
	str_cpy

	; calc offset and copy
	pop r0
	pop r1
	eq r0, r1
	bzf .done
	add r0, #1
	push r1
	push r0
	b .loop

.done:
	pop r0
	pop r1
	pop pcl
	pop pch

term_prompt:
	; echo on
	mov r0, #1
	push pch
	push pcl
	b set_echo_char

.read_string:
	mov r0, #>[term_line_buf]
	mov r1, #<[term_line_buf]
	push pch
	push pcl
	b read_string

.done:
	term_s_prompt db ">> "
	pop pcl
	pop pch

term_parse:
	xor r0, r0
	push pch
	psuh pcl
	b term_get_token	; get first token (cmd)

	ld r0, [term_line_buf+1]
	ld r1, [term_line_buf]
	push pch
	push pcl
	b str_cmp_set

.help:
	term_s_help db "help"
	mov r0, #>[term_s_help]
	mov r1, #<[term_s_help]
	push pch
	push pcl
	b str_cmp
`	gt r0, #0
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
`	gt r0, #0
	bzf .run
	push pch
	push pcl
	b term_cmd_run
	b .done

.run:
	term_s_run db "help"
	mov r0, #>[term_s_run]
	mov r1, #<[term_s_run]
	push pch
	push pcl
	b str_cmp
`	gt r0, #0
	bzf .invalid
	push pch
	push pcl
	b term_cmd_run
	b .done

.invalid:
	term_s_invalid_cmd db "ERROR: invalid cmd!"
	mov r0, #>[term_s_invalid_cmd]
	mov r1, #<[term_s_invalid_cmd]
	push pch
	push pcl
	b str_printstr

.done:
	pop pcl
	pop pch

term_cmd_help:
	; show help

	term_s_help_buf db "\nAvailable commands:\n==================\n"NEW - clear uBASIC prog mem\n"RUN - execute program currently in uBASIC prog mem\n\n"
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

