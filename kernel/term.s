; The terminal (doc/proposals/basic-program.md): the banner, BASIC loaded
; into $7000 (sys.s sys_basic_boot), the prompt and its line editor (printf.s
; read_string), and the commands the kernel runs itself - help, dir, del, net,
; refresh, exec. Every other line goes to the program at $7000 that set the
; terminal's hook (API_TERM_HOOK: BASIC, basic/basic.s); with none it is an
; invalid command.

term_line_buf: resb 80
term_i: resb 1				; term_find: where in its table
term_j: resb 1				;   and in the line
term_k: resb 1				;   the word's number there
term_tab: resb 2			;   the table
term_ni: resb 1
term_num: resb 4
term_rem: resb 1
term_bit: resb 1
term_carry: resb 1
term_dig: resb 1
term_digs: resb 12

term_s_usage db "\nSAVE, LOAD or DEL \"NAME\"\n"
term_cmds db "help net dir del refresh exec "

term_do:
	mov r0, #2				; API_RUN 2 while BASIC loads (cupc8.py run waits)
	st API_RUN, r0

	term_s_info db "\n      CUPC/8 BASIC 2026.09      \n"
	mov r0, #>[term_s_info]
	mov r1, #<[term_s_info]
	push pch
	push pcl
	b str_printstr

	push pch
	push pcl
	b sys_basic_boot
	xor r0, r0
	st API_RUN, r0			; no program from the PC yet

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
	mov r0, #<[term_cmds]
	mov r1, #>[term_cmds]
	push pch
	push pcl
	b term_find
	eq r0, #1
	bzf term_cmd_help
	eq r0, #2
	bzf .net
	eq r0, #3
	bzf term_cmd_dir
	eq r0, #4
	bzf term_cmd_del
	eq r0, #5
	bzf eink_cmd_refresh
	eq r0, #6
	bzf sys_cmd_exec
	; any other line: the program's at $7000
	mov r0, #<[term_line_buf]
	st API_ARGS, r0
	mov r0, #>[term_line_buf]
	st $6f01, r0
	xor r0, r0
	b term_hook
.net:
	mov r0, #<[term_line_buf]
	st [net_line], r0
	mov r0, #>[term_line_buf]
	st [net_line+1], r0
	b net_cmd

; the line's first word (up to a space, CR, LF or its end) in the table of
; words at r0 (low), r1 (high), each followed by a space: r0 = its number
; there, from 1, or 0
term_find:
	st [term_tab], r0
	st [term_tab+1], r1
	xor r0, r0
	st [term_i], r0
	mov r0, #1
	st [term_k], r0
.word:
	xor r0, r0
	st [term_j], r0
.char:
	ld r1, [term_i]
	ldd r0, [term_tab]+r1
	eq r0, #0				; the table's end
	bzf .none
	eq r0, #32				; the word's end
	bzf .end
	ld r1, [term_j]
	ld r1, [term_line_buf]+r1
	eq r0, r1
	bzf .same
	b .skip
.same:
	ld r0, [term_i]
	add r0, #1
	st [term_i], r0
	ld r0, [term_j]
	add r0, #1
	st [term_j], r0
	b .char
.end:
	ld r1, [term_j]			; the line's word ends here too?
	ld r0, [term_line_buf]+r1
	eq r0, #32
	bzf .found
	eq r0, #13
	bzf .found
	eq r0, #10
	bzf .found
	eq r0, #0
	bzf .found
.skip:
	ld r1, [term_i]			; on past this word's space
.past:
	ldd r0, [term_tab]+r1
	add r1, #1
	eq r0, #32
	bzf .next
	b .past
.next:
	st [term_i], r1
	ld r0, [term_k]
	add r0, #1
	st [term_k], r0
	b .word
.found:
	ld r0, [term_k]
	pop pcl
	pop pch
.none:
	xor r0, r0
	pop pcl
	pop pch

; request r0 to the hook (sys_hook, API_TERM_HOOK), API_ARGS set: 0 a line,
; 1 a file exec found with no program header. API_RUN is 2 while it runs
; (the program at $7000 is running: cupc8.py run must not write over it).
; With no hook: "invalid cmd", or for a file "bad program header".
term_hook:
	push r0
	mov r0, #2
	st API_RUN, r0
	ld r0, [sys_hook]
	ld r1, [sys_hook+1]
	or r0, r1
	eq r0, #0
	pop r0
	bzf .none
	push pch
	push pcl
	b .jump
	xor r0, r0
	st API_RUN, r0
	pop pcl
	pop pch
.jump:
	ld r1, [sys_hook+1]		; its address as a return address
	push r1
	ld r1, [sys_hook]
	push r1
	pop pcl
	pop pch
.none:
	xor r1, r1
	st API_RUN, r1
	eq r0, #0
	bzf .invalid
	mov r0, #>[sys_s_header]
	mov r1, #<[sys_s_header]
	b str_printstr
.invalid:
	term_s_invalid_cmd db "\nERROR: invalid cmd!\n"
	mov r0, #>[term_s_invalid_cmd]
	mov r1, #<[term_s_invalid_cmd]
	b str_printstr

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

; ------------------------------------------------------------ files on the storage card
; DIR and DEL "NAME" (kernel/storage.s); SAVE and LOAD are BASIC's.

; the name after the command word, quoted or not, into st_name; r0 = its length
term_get_name:
	xor r1, r1
.skip_word:
	ld r0, [term_line_buf]+r1
	gt r0, #32
	bzf .in_word
	b .skip_space
.in_word:
	add r1, #1
	b .skip_word
.skip_space:
	ld r0, [term_line_buf]+r1
	eq r0, #32
	bzf .space
	eq r0, #34				; an opening quote
	bzf .quote
	b .copy
.space:
	add r1, #1
	b .skip_space
.quote:
	add r1, #1
.copy:
	xor r0, r0
	st [term_ni], r0
.loop:
	ld r0, [term_line_buf]+r1
	gt r0, #32				; ends at a space, the CR or the terminator
	bzf .char
	b .end
.char:
	eq r0, #34				; or the closing quote
	bzf .end
	push r1
	ld r1, [term_ni]
	eq r1, #13				; longer than 8.3 - the card refuses 13
	bzf .next
	st [st_name]+r1, r0
	add r1, #1
	st [term_ni], r1
.next:
	pop r1
	add r1, #1
	b .loop
.end:
	ld r1, [term_ni]
	xor r0, r0
	st [st_name]+r1, r0
	ld r0, [term_ni]
	pop pcl
	pop pch

term_cmd_del:
	push pch
	push pcl
	b term_get_name
	eq r0, #0
	bzf .usage
	push pch
	push pcl
	b st_delete
	eq r0, #0
	bzf .done
	push pch
	push pcl
	b st_print_err
	b .done
.usage:
	mov r0, #>[term_s_usage]
	mov r1, #<[term_s_usage]
	push pch
	push pcl
	b str_printstr
.done:
	pop pcl
	pop pch

; every file - its name, then its size in bytes
term_cmd_dir:
	mov r0, #10
	push pch
	push pcl
	b print_ascii_char
	push pch
	push pcl
	b st_dir_first
.entry:
	eq r0, #0
	bzf .show
	eq r0, #255				; after the last file
	bzf .done
	push pch
	push pcl
	b st_print_err
	b .done
.show:
	xor r1, r1
.name:
	ld r0, [st_rbuf+5]		; the name's length
	eq r1, r0
	bzf .pad
	push r1
	ld r0, [st_rbuf+6]+r1
	push pch
	push pcl
	b print_ascii_char
	pop r1
	add r1, #1
	b .name
.pad:
	gt r1, #12
	bzf .size
	push r1
	mov r0, #32
	push pch
	push pcl
	b print_ascii_char
	pop r1
	add r1, #1
	b .pad
.size:
	ld r0, [st_rbuf]
	st [term_num], r0
	ld r0, [st_rbuf+1]
	st [term_num+1], r0
	ld r0, [st_rbuf+2]
	st [term_num+2], r0
	ld r0, [st_rbuf+3]
	st [term_num+3], r0
	push pch
	push pcl
	b term_print_u32
	mov r0, #10
	push pch
	push pcl
	b print_ascii_char
	push pch
	push pcl
	b st_dir_next
	b .entry
.done:
	pop pcl
	pop pch

; print term_num (4 bytes, low first) in decimal - each digit is the remainder
; of a 32-step shift-and-subtract division by 10
term_print_u32:
	xor r0, r0
	st [term_dig], r0
.digit:
	xor r0, r0
	st [term_rem], r0
	mov r0, #32
	st [term_bit], r0
.bit:
	ld r0, [term_num+3]
	shr r0, #7
	st [term_carry], r0
	ld r0, [term_num+2]
	shr r0, #7
	ld r1, [term_num+3]
	shl r1, #1
	or r1, r0
	st [term_num+3], r1
	ld r0, [term_num+1]
	shr r0, #7
	ld r1, [term_num+2]
	shl r1, #1
	or r1, r0
	st [term_num+2], r1
	ld r0, [term_num]
	shr r0, #7
	ld r1, [term_num+1]
	shl r1, #1
	or r1, r0
	st [term_num+1], r1
	ld r1, [term_num]
	shl r1, #1
	st [term_num], r1
	ld r0, [term_rem]
	shl r0, #1
	ld r1, [term_carry]
	or r0, r1
	st [term_rem], r0
	lt r0, #10
	bzf .no_sub
	sub r0, #10
	st [term_rem], r0
	ld r0, [term_num]
	or r0, #1
	st [term_num], r0
.no_sub:
	ld r0, [term_bit]
	sub r0, #1
	st [term_bit], r0
	eq r0, #0
	bzf .digit_done
	b .bit
.digit_done:
	ld r0, [term_rem]
	add r0, #48
	ld r1, [term_dig]
	st [term_digs]+r1, r0
	add r1, #1
	st [term_dig], r1
	ld r0, [term_num]
	ld r1, [term_num+1]
	or r0, r1
	ld r1, [term_num+2]
	or r0, r1
	ld r1, [term_num+3]
	or r0, r1
	eq r0, #0
	bzf .print
	b .digit
.print:
	ld r1, [term_dig]
	eq r1, #0
	bzf .done
	sub r1, #1
	st [term_dig], r1
	ld r0, [term_digs]+r1
	push pch
	push pcl
	b print_ascii_char
	b .print
.done:
	pop pcl
	pop pch
