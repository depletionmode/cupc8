; https://github.com/adamdunkels/ubasic
;
; CUPC/8 BASIC (doc/CUPC8 Manual.md; doc/proposals/basic-graphics.md): uBASIC
; with 16-bit signed numbers (-32768..32767, wrapping; basic/n16.s,
; kernel/math.s), line numbers 1-32767, one-letter variables a-z, and
; graphics statements through the kernel API. The program is text in
; $c000-$dfff (basic/basic.s).
;
; A number in registers is r0 = its low byte, r1 = its high byte; a pointer
; into the program is r0 = high, r1 = low (ubasic_tokenizer_goto's).

ub_variables: resb 52		; a-z, two bytes each, low first
ub_string: resb 40
ub_val: resb 2				; ubasic_set_variable's value

%define TOKENIZER_ERROR			#0
%define TOKENIZER_ENDOFINPUT	#1
%define TOKENIZER_NUMBER		#2
%define TOKENIZER_STRING		#3
%define TOKENIZER_VARIABLE		#4
%define TOKENIZER_LET			#5
%define TOKENIZER_PRINT			#6
%define TOKENIZER_IF			#7
%define TOKENIZER_THEN			#8
%define TOKENIZER_ELSE			#9
%define TOKENIZER_FOR			#10
%define TOKENIZER_TO			#11
%define TOKENIZER_NEXT			#12
%define TOKENIZER_GOTO			#13
%define TOKENIZER_GOSUB			#14
%define TOKENIZER_RETURN		#15
%define TOKENIZER_CALL			#16
%define TOKENIZER_REM			#17
%define TOKENIZER_PEEK			#18
%define TOKENIZER_POKE			#19
%define TOKENIZER_END			#20
%define TOKENIZER_COMMA			#21
%define TOKENIZER_SEMICOLON		#22
%define TOKENIZER_PLUS			#23
%define TOKENIZER_MINUS			#24
%define TOKENIZER_AND			#25
%define TOKENIZER_OR			#26
%define TOKENIZER_ASTR			#27
%define TOKENIZER_SLASH			#28
%define TOKENIZER_MOD			#29
%define TOKENIZER_HASH			#30
%define TOKENIZER_LEFTPAREN		#31
%define TOKENIZER_RIGHTPAREN	#32
%define TOKENIZER_LT			#33
%define TOKENIZER_GT			#34
%define TOKENIZER_EQ			#35
%define TOKENIZER_CR			#36
%define TOKENIZER_MODE			#37
%define TOKENIZER_CLS			#38
%define TOKENIZER_COLOR			#39
%define TOKENIZER_PLOT			#40
%define TOKENIZER_LINE			#41
%define TOKENIZER_BOX			#42
%define TOKENIZER_PALETTE		#43
%define TOKENIZER_REFRESH		#44

; the line index: where each line run so far starts, so GOTO, GOSUB and NEXT
; need not search. 4 bytes a line (its number, then the pointer; low first)
; for up to 300 lines, then a line number 0; a line past those is found
; from the start of the program (ubasic_jump_linenum_slow).
ub_line_index: resb 1204
ub_ix_p: resb 2
ub_ix_n: resb 2
ub_linenum: resb 2
ub_jl: resb 2				; the line ubasic_jump_linenum looks for
ub_for_stack_index: resb 1
ub_for_stack: resb 20		; 4 deep: the line after the FOR (2), the variable, the limit (2)
ub_for_var: resb 1
ub_gosub_stack_index: resb 1
ub_gosub_stack: resb 20		; 10 deep: the line to return to (2)
ub_ptr: resb 2

program_ptr: resb 2
ended: resb 1
ub_failed: resb 1			; a fatal error ended the run
ub_mode: resb 1				; the graphics mode the program set (0 TEXT, 1 GFX, 2 e-ink native)
ubasic_init:
	push r0
	push r1

	st [program_ptr], r1
	st [program_ptr+1], r0

	xor r0, r0
	st [ub_gosub_stack_index], r0
	st [ub_for_stack_index], r0
	st [ended], r0
	st [ub_failed], r0
	st [ub_mode], r0

	; every variable starts at 0: RAM powers up with junk
	xor r1, r1
.clear_variables:
	st [ub_variables]+r1, r0
	add r1, #1
	eq r1, #52
	bzf .done_clear_variables
	b .clear_variables
.done_clear_variables:

	; an empty line index (RAM holds whatever the boot ROM's RAM test left)
	st [ub_line_index], r0
	st [ub_line_index+1], r0

	pop r1
	pop r0
	push pch
	push pcl
	b ubasic_tokenizer_init

	pop pcl
	pop pch

token: resb 1
ubasic_accept:
	st [token], r0

	push pch
	push pcl
	b ubasic_tokenizer_token

	ld r1, [token]
	xor r0, r1
	eq r0, #0
	bzf .cont
	; err
	push pch
	push pcl
	b ubasic_fatal


.cont:
	push pch
	push pcl
	b ubasic_tokenizer_next

	pop pcl
	pop pch

r: resb 2
; a number, a variable, an expression in parentheses, or - and a factor
ubasic_factor:
	push pch
	push pcl
	b ubasic_tokenizer_token

	eq r0, TOKENIZER_NUMBER
	bzf .number
	eq r0, TOKENIZER_LEFTPAREN
	bzf .leftparen
	eq r0, TOKENIZER_MINUS
	bzf .minus
	; a variable
	push pch
	push pcl
	b ubasic_tokenizer_variable_num
	push pch
	push pcl
	b ubasic_get_variable
	st [r], r0
	st [r+1], r1
	mov r0, TOKENIZER_VARIABLE
	push pch
	push pcl
	b ubasic_accept
	b .end

.number:
	push pch
	push pcl
	b ubasic_tokenizer_num
	st [r], r0
	st [r+1], r1

	mov r0, TOKENIZER_NUMBER
	push pch
	push pcl
	b ubasic_accept

	b .end

.leftparen:
	mov r0, TOKENIZER_LEFTPAREN
	push pch
	push pcl
	b ubasic_accept

	push pch
	push pcl
	b ubasic_expr
	st [r], r0
	st [r+1], r1

	mov r0, TOKENIZER_RIGHTPAREN
	push pch
	push pcl
	b ubasic_accept
	b .end

.minus:
	push pch
	push pcl
	b ubasic_tokenizer_next
	push pch
	push pcl
	b ubasic_factor
	st [n_a], r0
	st [n_a+1], r1
	push pch
	push pcl
	b n16_neg
	ld r0, [n_a]
	st [r], r0
	ld r0, [n_a+1]
	st [r+1], r0

.end:
	ld r0, [r]
	ld r1, [r+1]
	pop pcl
	pop pch

; Expressions, by precedence level: 0 relations (< > =), 1 + - & |, 2 * / %,
; then factors. Each level is operand (op operand)*, left to right; a level
; keeps its state on the stack while an operand is parsed, so parentheses
; nest.
ub_lvl: resb 1
ub_op: resb 1
ub_lhs: resb 2
ub_res: resb 2

; a relation (IF's condition): the value in r0, r1
ubasic_relation:
	mov r0, #0
	b ub_level

; an expression: the value in r0, r1
ubasic_expr:
	mov r0, #1
; level r0's expression
ub_level:
	ld r1, [ub_lvl]
	push r1
	ld r1, [ub_op]
	push r1
	ld r1, [ub_lhs]
	push r1
	ld r1, [ub_lhs+1]
	push r1
	st [ub_lvl], r0
	push pch
	push pcl
	b ub_operand
	st [ub_lhs], r0
	st [ub_lhs+1], r1
.loop:
	push pch
	push pcl
	b ubasic_tokenizer_token
	st [ub_op], r0
	mov r1, #0xff			; the operator's level, $ff if it is none
	lt r0, TOKENIZER_PLUS
	bzf .level
	lt r0, TOKENIZER_ASTR
	bzf .is1
	lt r0, TOKENIZER_HASH
	bzf .is2
	lt r0, TOKENIZER_LT
	bzf .level
	lt r0, TOKENIZER_CR
	bzf .is0
	b .level
.is0:
	mov r1, #0
	b .level
.is1:
	mov r1, #1
	b .level
.is2:
	mov r1, #2
.level:
	ld r0, [ub_lvl]
	eq r0, r1
	bzf .op
	b .end
.op:
	push pch
	push pcl
	b ubasic_tokenizer_next
	ld r0, [ub_lvl]
	push pch
	push pcl
	b ub_operand
	st [n_b], r0
	st [n_b+1], r1
	ld r0, [ub_lhs]
	st [n_a], r0
	ld r0, [ub_lhs+1]
	st [n_a+1], r0
	ld r0, [ub_op]
	push pch
	push pcl
	b ub_binop
	ld r0, [n_a]
	st [ub_lhs], r0
	ld r0, [n_a+1]
	st [ub_lhs+1], r0
	b .loop
.end:
	ld r0, [ub_lhs]
	st [ub_res], r0
	ld r0, [ub_lhs+1]
	st [ub_res+1], r0
	pop r1
	st [ub_lhs+1], r1
	pop r1
	st [ub_lhs], r1
	pop r1
	st [ub_op], r1
	pop r1
	st [ub_lvl], r1
	ld r0, [ub_res]
	ld r1, [ub_res+1]
	pop pcl
	pop pch

; an operand of level r0's operators: the next level's expression, or a factor
ub_operand:
	eq r0, #2
	bzf .factor
	add r0, #1
	b ub_level
.factor:
	b ubasic_factor

; n_a = n_a (operator r0) n_b; a relation gives 1 true, 0 false (signed)
ub_binop:
	eq r0, TOKENIZER_PLUS
	bzf n16_add
	eq r0, TOKENIZER_MINUS
	bzf n16_sub
	eq r0, TOKENIZER_AND
	bzf n16_and
	eq r0, TOKENIZER_OR
	bzf n16_or
	eq r0, TOKENIZER_ASTR
	bzf n16_mul
	eq r0, TOKENIZER_SLASH
	bzf n16_div
	eq r0, TOKENIZER_MOD
	bzf .mod
	push r0
	push pch
	push pcl
	b n16_cmp				; 0 equal, 1 less, 2 greater
	pop r1
	sub r1, #32				; < 1, > 2, = 3
	eq r1, #3
	bzf .eq
	b .test
.eq:
	xor r1, r1
.test:
	eq r0, r1
	xor r0, r0
	st [n_a+1], r0
	bzf .true
	st [n_a], r0
	pop pcl
	pop pch
.true:
	mov r0, #1
	st [n_a], r0
	pop pcl
	pop pch
.mod:
	push pch
	push pcl
	b n16_div
	ld r0, [n_t]
	st [n_a], r0
	ld r0, [n_t+1]
	st [n_a+1], r0
	pop pcl
	pop pch

; to the line numbered ub_jl, from the start of the program; a fatal error if
; there is none. Past the line index's reach, or a line not run yet.
ubasic_jump_linenum_slow:
	ld r1, [program_ptr]
	ld r0, [program_ptr+1]
	push pch
	push pcl
	b ubasic_tokenizer_init
.line:
	push pch
	push pcl
	b ubasic_tokenizer_token
	eq r0, TOKENIZER_NUMBER
	bzf .number
	b .missing
.number:
	push pch
	push pcl
	b ubasic_tokenizer_num
	push r1
	ld r1, [ub_jl]
	eq r0, r1
	pop r0
	bzf .low_same
	b .skip
.low_same:
	ld r1, [ub_jl+1]
	eq r0, r1
	bzf .end
.skip:
	; to the next line: past the next line end in the text (a REM, a string
	; hold no line end)
	ldd r0, [ub_ptr]
	eq r0, #0
	bzf .missing
	eq r0, #13
	bzf .eol
	eq r0, #10
	bzf .eol
	push pch
	push pcl
	b ub_ptr_inc
	b .skip
.eol:
	push pch
	push pcl
	b ub_ptr_inc
	ld r0, [ub_ptr+1]
	ld r1, [ub_ptr]
	push pch
	push pcl
	b ubasic_tokenizer_goto
	b .line
.missing:
	push pch
	push pcl
	b ubasic_fatal
.end:
	pop pcl
	pop pch

; ub_ptr + 1
ub_ptr_inc:
	ld r0, [ub_ptr]
	add r0, #1
	st [ub_ptr], r0
	eq r0, #0
	bzf .carry
	pop pcl
	pop pch
.carry:
	ld r0, [ub_ptr+1]
	add r0, #1
	st [ub_ptr+1], r0
	pop pcl
	pop pch

; to line r0 (low), r1 (high)
ubasic_jump_linenum:
	st [ub_jl], r0
	st [ub_jl+1], r1
	push pch
	push pcl
	b ubasic_index_find
	push r0
	or r0, r1
	eq r0, #0
	pop r0
	bzf .slow
	b ubasic_tokenizer_goto
.slow:
	b ubasic_jump_linenum_slow

ubasic_goto_statement:
	mov r0, TOKENIZER_GOTO
	push pch
	push pcl
	b ubasic_accept

	push pch
	push pcl
	b ubasic_tokenizer_num

	b ubasic_jump_linenum

ubasic_print_statement:
	mov r0, TOKENIZER_PRINT
	push pch
	push pcl
	b ubasic_accept

.loop:
	push pch
	push pcl
	b ubasic_tokenizer_token
	eq r0, TOKENIZER_STRING
	bzf .string
	eq r0, TOKENIZER_COMMA
	bzf .comma
	eq r0, TOKENIZER_SEMICOLON
	bzf .semicolon
	eq r0, TOKENIZER_VARIABLE
	bzf .var_or_num
	eq r0, TOKENIZER_NUMBER
	bzf .var_or_num
	eq r0, TOKENIZER_LEFTPAREN
	bzf .var_or_num
	eq r0, TOKENIZER_MINUS
	bzf .var_or_num
	b .end

.string:
	push pch
	push pcl
	b ubasic_tokenizer_string
	mov r0, #>[ub_string]
	mov r1, #<[ub_string]
	push pch
	push pcl
	b str_printstr
	push pch
	push pcl
	b ubasic_tokenizer_next
	b .next
.comma:
	mov r0, #32
	push pch
	push pcl
	b API_PUTC
	push pch
	push pcl
	b ubasic_tokenizer_next
	b .next
.semicolon:
	push pch
	push pcl
	b ubasic_tokenizer_next
	b .next
.var_or_num:
	push pch
	push pcl
	b ubasic_expr
	st [n_a], r0
	st [n_a+1], r1
	push pch
	push pcl
	b n16_print
	b .next

.next:
	push pch
	push pcl
	b ubasic_tokenizer_token
	eq r0, TOKENIZER_CR
	bzf .end
	eq r0, TOKENIZER_ENDOFINPUT
	bzf .end
	b .loop

.end:
	mov r0, #10
	push pch
	push pcl
	b API_PUTC
	push pch
	push pcl
	b ubasic_end_of_statement
	pop pcl
	pop pch

ubasic_end_of_statement:
	; a statement ends at CR (consumed), or at an ELSE or the end of the
	; program (left for the caller); anything else is an error
	push pch
	push pcl
	b ubasic_tokenizer_token
	eq r0, TOKENIZER_CR
	bzf .cr
	eq r0, TOKENIZER_ELSE
	bzf .done
	eq r0, TOKENIZER_ENDOFINPUT
	bzf .done
	push pch
	push pcl
	b ubasic_fatal
	b .done
.cr:
	push pch
	push pcl
	b ubasic_tokenizer_next
.done:
	pop pcl
	pop pch

ub_if: resb 1
ubasic_if_statement:
	mov r0, TOKENIZER_IF
	push pch
	push pcl
	b ubasic_accept

	push pch
	push pcl
	b ubasic_relation
	or r0, r1				; true - not 0
	st [ub_if], r0

	mov r0, TOKENIZER_THEN
	push pch
	push pcl
	b ubasic_accept

	ld r0, [ub_if]
	eq r0, #0
	bzf .else
	push pch
	push pcl
	b ubasic_statement
	push pch
	push pcl
	b ubasic_tokenizer_token
	eq r0, TOKENIZER_ELSE
	bzf .skip_else
	b .end
.skip_else:
	push pch
	push pcl
	b ubasic_tokenizer_next
	push pch
	push pcl
	b ubasic_tokenizer_token
	eq r0, TOKENIZER_CR
	bzf .tok_next
	eq r0, TOKENIZER_ENDOFINPUT
	bzf .end
	b .skip_else
.else:
.loop:
	push pch
	push pcl
	b ubasic_tokenizer_next
	push pch
	push pcl
	b ubasic_tokenizer_token
	eq r0, TOKENIZER_ELSE
	bzf .n
	eq r0, TOKENIZER_CR
	bzf .n
	eq r0, TOKENIZER_ENDOFINPUT
	bzf .n
	b .loop
.n:
	push pch
	push pcl
	b ubasic_tokenizer_token
	eq r0, TOKENIZER_ELSE
	bzf .tok_else
	eq r0, TOKENIZER_CR
	bzf .tok_next
	b .end

.tok_else:
	push pch
	push pcl
	b ubasic_tokenizer_next
	push pch
	push pcl
	b ubasic_statement
	b .end

.tok_next:
	push pch
	push pcl
	b ubasic_tokenizer_next

.end:
	pop pcl
	pop pch

ub_var: resb 1
ubasic_let_statement:
	push pch
	push pcl
	b ubasic_tokenizer_variable_num
	st [ub_var], r0

	mov r0, TOKENIZER_VARIABLE
	push pch
	push pcl
	b ubasic_accept

	mov r0, TOKENIZER_EQ
	push pch
	push pcl
	b ubasic_accept

	push pch
	push pcl
	b ubasic_expr
	st [ub_val], r0
	st [ub_val+1], r1
	ld r0, [ub_var]
	push pch
	push pcl
	b ubasic_set_variable

	push pch
	push pcl
	b ubasic_end_of_statement

	pop pcl
	pop pch

ubasic_gosub_statement:
	mov r0, TOKENIZER_GOSUB
	push pch
	push pcl
	b ubasic_accept

	push pch
	push pcl
	b ubasic_tokenizer_num
	push r1					; the line to go to
	push r0

	mov r0, TOKENIZER_NUMBER
	push pch
	push pcl
	b ubasic_accept
	mov r0, TOKENIZER_CR
	push pch
	push pcl
	b ubasic_accept

	ld r1, [ub_gosub_stack_index]
	gt r1, #18
	bzf .full
	push pch
	push pcl
	b ubasic_tokenizer_num	; the next line's number - RETURN goes there
	push r1
	ld r1, [ub_gosub_stack_index]
	st [ub_gosub_stack]+r1, r0
	add r1, #1
	pop r0
	st [ub_gosub_stack]+r1, r0
	add r1, #1
	st [ub_gosub_stack_index], r1
	pop r0
	pop r1
	b ubasic_jump_linenum
.full:
	pop r0
	pop r1
	b ubasic_fatal

ubasic_return_statement:
	mov r0, TOKENIZER_RETURN
	push pch
	push pcl
	b ubasic_accept

	ld r1, [ub_gosub_stack_index]
	eq r1, #0
	bzf .empty
	sub r1, #1
	ld r0, [ub_gosub_stack]+r1
	push r0
	sub r1, #1
	ld r0, [ub_gosub_stack]+r1
	st [ub_gosub_stack_index], r1
	pop r1
	b ubasic_jump_linenum
.empty:
	b ubasic_fatal

ubasic_next_statement:
	mov r0, TOKENIZER_NEXT
	push pch
	push pcl
	b ubasic_accept

	push pch
	push pcl
	b ubasic_tokenizer_variable_num
	st [ub_for_var], r0
	mov r0, TOKENIZER_VARIABLE
	push pch
	push pcl
	b ubasic_accept

	ld r1, [ub_for_stack_index]
	eq r1, #0
	bzf .bad
	sub r1, #3
	ld r0, [ub_for_stack]+r1	; the innermost FOR's variable
	ld r1, [ub_for_var]
	eq r0, r1
	bzf .same
	b .bad
.same:
	mov r0, r1				; the variable + 1
	push pch
	push pcl
	b ubasic_get_variable
	st [n_a], r0
	st [n_a+1], r1
	mov r0, #1
	st [n_b], r0
	xor r0, r0
	st [n_b+1], r0
	push pch
	push pcl
	b n16_add
	ld r0, [n_a]
	st [ub_val], r0
	ld r0, [n_a+1]
	st [ub_val+1], r0
	ld r0, [ub_for_var]
	push pch
	push pcl
	b ubasic_set_variable
	ld r1, [ub_for_stack_index]	; past the limit?
	sub r1, #2
	ld r0, [ub_for_stack]+r1
	st [n_b], r0
	add r1, #1
	ld r0, [ub_for_stack]+r1
	st [n_b+1], r0
	ld r0, [ub_val]
	st [n_a], r0
	ld r0, [ub_val+1]
	st [n_a+1], r0
	push pch
	push pcl
	b n16_cmp
	eq r0, #2
	bzf .done
	ld r1, [ub_for_stack_index]	; not yet - to the line after the FOR
	sub r1, #5
	ld r0, [ub_for_stack]+r1
	push r0
	add r1, #1
	ld r1, [ub_for_stack]+r1
	pop r0
	b ubasic_jump_linenum
.done:
	ld r1, [ub_for_stack_index]
	sub r1, #5
	st [ub_for_stack_index], r1
	mov r0, TOKENIZER_CR
	b ubasic_accept
.bad:
	mov r0, TOKENIZER_CR
	push pch
	push pcl
	b ubasic_accept
	b ubasic_fatal

ubasic_for_statement:
	mov r0, TOKENIZER_FOR
	push pch
	push pcl
	b ubasic_accept

	push pch
	push pcl
	b ubasic_tokenizer_variable_num
	st [ub_for_var], r0
	mov r0, TOKENIZER_VARIABLE
	push pch
	push pcl
	b ubasic_accept
	mov r0, TOKENIZER_EQ
	push pch
	push pcl
	b ubasic_accept
	push pch
	push pcl
	b ubasic_expr
	st [ub_val], r0
	st [ub_val+1], r1
	ld r0, [ub_for_var]
	push pch
	push pcl
	b ubasic_set_variable
	mov r0, TOKENIZER_TO
	push pch
	push pcl
	b ubasic_accept
	push pch
	push pcl
	b ubasic_expr
	push r1					; the limit
	push r0
	mov r0, TOKENIZER_CR
	push pch
	push pcl
	b ubasic_accept

	ld r1, [ub_for_stack_index]
	gt r1, #15
	bzf .full
	push pch
	push pcl
	b ubasic_tokenizer_num	; the line after the FOR, where NEXT goes back to
	push r1
	ld r1, [ub_for_stack_index]
	st [ub_for_stack]+r1, r0
	add r1, #1
	pop r0
	st [ub_for_stack]+r1, r0
	add r1, #1
	ld r0, [ub_for_var]
	st [ub_for_stack]+r1, r0
	add r1, #1
	pop r0
	st [ub_for_stack]+r1, r0
	add r1, #1
	pop r0
	st [ub_for_stack]+r1, r0
	add r1, #1
	st [ub_for_stack_index], r1
	pop pcl
	pop pch
.full:
	pop r0
	pop r0
	b ubasic_fatal

ub_mem_ptr: resb 2
ub_peek_var: resb 1
ub_peek_pos: resb 2
; A 16-bit address, or (the old 8-bit form, which saved programs use) its
; high byte and low byte: the address is hi * 256 + lo.
;   poke addr, value          poke hi, lo, value
;   peek addr, var            peek hi, lo, var
ubasic_peek_statement:
	mov r0, TOKENIZER_PEEK
	push pch
	push pcl
	b ubasic_accept
	push pch
	push pcl
	b ubasic_expr
	st [ub_mem_ptr], r0
	st [ub_mem_ptr+1], r1
	mov r0, TOKENIZER_COMMA
	push pch
	push pcl
	b ubasic_accept
	; a variable and the statement's end: peek addr, var
	push pch
	push pcl
	b ubasic_tokenizer_token
	eq r0, TOKENIZER_VARIABLE
	bzf .var
	b .lo
.var:
	ld r0, [ub_ptr]
	st [ub_peek_pos], r0
	ld r0, [ub_ptr+1]
	st [ub_peek_pos+1], r0
	push pch
	push pcl
	b ubasic_tokenizer_variable_num
	st [ub_peek_var], r0
	push pch
	push pcl
	b ubasic_tokenizer_next
	push pch
	push pcl
	b ubasic_tokenizer_token
	eq r0, TOKENIZER_CR
	bzf .read
	eq r0, TOKENIZER_ELSE
	bzf .read
	eq r0, TOKENIZER_ENDOFINPUT
	bzf .read
	ld r0, [ub_peek_pos+1]	; no - back to the variable, lo's expression
	ld r1, [ub_peek_pos]
	push pch
	push pcl
	b ubasic_tokenizer_goto
.lo:
	push pch
	push pcl
	b ubasic_expr
	push pch
	push pcl
	b ub_mem_hi_lo
	mov r0, TOKENIZER_COMMA
	push pch
	push pcl
	b ubasic_accept
	push pch
	push pcl
	b ubasic_tokenizer_variable_num
	st [ub_peek_var], r0
	mov r0, TOKENIZER_VARIABLE
	push pch
	push pcl
	b ubasic_accept
.read:
	ldd r0, [ub_mem_ptr]
	st [ub_val], r0
	xor r0, r0
	st [ub_val+1], r0
	ld r0, [ub_peek_var]
	push pch
	push pcl
	b ubasic_set_variable
	b ubasic_end_of_statement

; the address hi * 256 + lo: hi is in ub_mem_ptr, lo in r0, r1
ub_mem_hi_lo:
	push r0
	ld r0, [ub_mem_ptr]
	add r1, r0				; hi's low byte + lo's high byte
	st [ub_mem_ptr+1], r1
	pop r0
	st [ub_mem_ptr], r0
	pop pcl
	pop pch

ubasic_poke_statement:
	mov r0, TOKENIZER_POKE
	push pch
	push pcl
	b ubasic_accept
	push pch
	push pcl
	b ubasic_expr
	st [ub_mem_ptr], r0
	st [ub_mem_ptr+1], r1
	mov r0, TOKENIZER_COMMA
	push pch
	push pcl
	b ubasic_accept
	push pch
	push pcl
	b ubasic_expr
	push r0
	push r1
	push pch
	push pcl
	b ubasic_tokenizer_token
	pop r1
	eq r0, TOKENIZER_COMMA
	pop r0
	bzf .three
	b .write
.three:
	push pch
	push pcl
	b ub_mem_hi_lo
	push pch
	push pcl
	b ubasic_tokenizer_next
	push pch
	push pcl
	b ubasic_expr
.write:
	std [ub_mem_ptr], r0
	b ubasic_end_of_statement

ubasic_end_statement:
	mov r0, TOKENIZER_END
	push pch
	push pcl
	b ubasic_accept
	mov r0, #1
	st [ended], r0

	pop pcl
	pop pch

; ------------------------------------------------------------ graphics
; Through the kernel API (kernel/sys.s), so either graphics card runs them.
; In ub_mode 2 the e-ink card's native entries (x16, y16, greys 0-3), else
; GFX's (x16, y8, colours 0-255): y and h are clamped to 0-255 there.

ub_argc: resb 1
ub_argv: resb 12			; up to 6 arguments, two bytes each
ub_dst: resb 1

; the statement's arguments after its keyword: expressions separated by
; commas, up to 6, into ub_argv; the statement's end checked. r0 = how many,
; or $ff after a syntax error (reported)
ub_args:
	push pch
	push pcl
	b ubasic_tokenizer_next
	xor r0, r0
	st [ub_argc], r0
	push pch
	push pcl
	b ubasic_tokenizer_token
	eq r0, TOKENIZER_CR
	bzf .end
	eq r0, TOKENIZER_ELSE
	bzf .end
	eq r0, TOKENIZER_ENDOFINPUT
	bzf .end
.arg:
	push pch
	push pcl
	b ubasic_expr
	push r1
	push r0
	ld r1, [ub_argc]
	shl r1, #1
	pop r0
	st [ub_argv]+r1, r0
	add r1, #1
	pop r0
	st [ub_argv]+r1, r0
	ld r0, [ub_argc]
	add r0, #1
	st [ub_argc], r0
	push pch
	push pcl
	b ubasic_tokenizer_token
	eq r0, TOKENIZER_COMMA
	bzf .comma
	b .end
.comma:
	ld r0, [ub_argc]
	eq r0, #6				; a seventh - the comma is left, a syntax error
	bzf .end
	push pch
	push pcl
	b ubasic_tokenizer_next
	b .arg
.end:
	push pch
	push pcl
	b ubasic_end_of_statement
	ld r0, [ended]
	eq r0, #0
	bzf .ok
	mov r0, #0xff
	pop pcl
	pop pch
.ok:
	ld r0, [ub_argc]
	pop pcl
	pop pch

; argument r0 into API_ARGS + r1: ub_arg16 both bytes, ub_arg8 the low byte,
; ub_argy the low byte clamped to 0-255 (GFX's y8, h8)
ub_arg16:
	st [ub_dst], r1
	shl r0, #1
	mov r1, r0
	add r1, #1
	ld r0, [ub_argv]+r1
	push r0
	sub r1, #1
	ld r0, [ub_argv]+r1
	ld r1, [ub_dst]
	st API_ARGS+r1, r0
	add r1, #1
	pop r0
	st API_ARGS+r1, r0
	pop pcl
	pop pch

ub_arg8:
	push r1
	shl r0, #1
	mov r1, r0
	ld r0, [ub_argv]+r1
	pop r1
	st API_ARGS+r1, r0
	pop pcl
	pop pch

ub_argy:
	push r1
	shl r0, #1
	mov r1, r0
	add r1, #1
	ld r0, [ub_argv]+r1		; the high byte
	sub r1, #1
	ld r1, [ub_argv]+r1
	eq r0, #0
	bzf .put
	lt r0, #0x80
	mov r1, #0				; negative - 0
	bzf .max
	b .put
.max:
	mov r1, #255			; over 255 - 255
.put:
	mov r0, r1
	pop r1
	st API_ARGS+r1, r0
	pop pcl
	pop pch

; a statement with the wrong arguments (unless ub_args reported it)
ub_syntax:
	ld r0, [ended]
	eq r0, #0
	bzf ubasic_fatal
	pop pcl
	pop pch

; mode n: 0 TEXT, 1 GFX, 2 the e-ink card's native mode. Another n, or 2 on
; HDMI, is ignored (as the card does)
ub_mode_statement:
	push pch
	push pcl
	b ub_args
	eq r0, #1
	bzf .one
	b ub_syntax
.one:
	ld r0, [ub_argv+1]
	eq r0, #0
	bzf .small
	b .done
.small:
	ld r0, [ub_argv]
	gt r0, #2
	bzf .done
	push r0
	push pch
	push pcl
	b API_GFX_MODE
	pop r1
	eq r0, #0
	bzf .set
	b .done
.set:
	st [ub_mode], r1
.done:
	pop pcl
	pop pch

; cls [c]: TEXT with attribute c ($07), GFX with colour c (0), mode 2 with
; grey c (3, white)
ub_cls_statement:
	push pch
	push pcl
	b ub_args
	eq r0, #1
	bzf .given
	eq r0, #0
	bzf .default
	b ub_syntax
.default:
	ld r0, [ub_mode]
	eq r0, #1
	bzf .black
	eq r0, #2
	bzf .white
	mov r0, #0x07
	b API_CLS
.black:
	xor r0, r0
	b API_CLS
.white:
	mov r0, #3
	b API_CLS
.given:
	ld r0, [ub_argv]
	b API_CLS

; color fg [, bg]: the TEXT attribute (16 colours each; bg 0 if not given)
ub_color_statement:
	push pch
	push pcl
	b ub_args
	eq r0, #1
	bzf .fg
	eq r0, #2
	bzf .bg
	b ub_syntax
.fg:
	xor r0, r0
	st [ub_argv+2], r0
.bg:
	ld r0, [ub_argv+2]
	shl r0, #4
	ld r1, [ub_argv]
	and r1, #15
	or r0, r1
	b API_ATTR

; plot x, y, c
ub_plot_statement:
	push pch
	push pcl
	b ub_args
	eq r0, #3
	bzf .args
	b ub_syntax
.args:
	mov r0, #0
	mov r1, #0
	push pch
	push pcl
	b ub_arg16
	ld r0, [ub_mode]
	eq r0, #2
	bzf .native
	mov r0, #1
	mov r1, #2
	push pch
	push pcl
	b ub_argy
	mov r0, #2
	mov r1, #3
	push pch
	push pcl
	b ub_arg8
	b API_GFX_PIXEL
.native:
	mov r0, #1
	mov r1, #2
	push pch
	push pcl
	b ub_arg16
	mov r0, #2
	mov r1, #4
	push pch
	push pcl
	b ub_arg8
	b API_GFX2_PIXEL

; line x0, y0, x1, y1, c
ub_line_statement:
	push pch
	push pcl
	b ub_args
	eq r0, #5
	bzf .args
	b ub_syntax
.args:
	ld r0, [ub_mode]
	eq r0, #2
	bzf .native
	push pch
	push pcl
	b ub_xy8				; x0, y0 at 0
	mov r0, #2				; x1, y1 at 3
	mov r1, #3
	push pch
	push pcl
	b ub_xy8_at
	mov r0, #4
	mov r1, #6
	push pch
	push pcl
	b ub_arg8
	b API_GFX_LINE
.native:
	push pch
	push pcl
	b ub_args16_4
	b API_GFX2_LINE

; box x, y, w, h, c [, f]: an outline, or filled when f is given and not 0
ub_box_statement:
	push pch
	push pcl
	b ub_args
	eq r0, #5
	bzf .args
	eq r0, #6
	bzf .args
	b ub_syntax
.args:
	ld r0, [ub_mode]
	eq r0, #2
	bzf .native
	push pch
	push pcl
	b ub_xy8				; x, y at 0
	mov r0, #2				; w, h at 3
	mov r1, #3
	push pch
	push pcl
	b ub_xy8_at
	mov r0, #4
	mov r1, #6
	push pch
	push pcl
	b ub_arg8
	push pch
	push pcl
	b ub_filled
	bzf .fill
	b API_GFX_RECT
.fill:
	b API_GFX_FILL_RECT
.native:
	push pch
	push pcl
	b ub_args16_4
	push pch
	push pcl
	b ub_filled
	bzf .fill2
	b API_GFX2_RECT
.fill2:
	b API_GFX2_FILL_RECT

; Z set when box's sixth argument is there and not 0
ub_filled:
	ld r0, [ub_argc]
	eq r0, #6
	bzf .six
	pop pcl
	pop pch
.six:
	ld r0, [ub_argv+10]
	ld r1, [ub_argv+11]
	or r0, r1
	gt r0, #0
	pop pcl
	pop pch

; arguments 0-3 as x16, y16, x16, y16 and 4 as g, at API_ARGS 0-8 (mode 2)
ub_args16_4:
	mov r0, #0
.arg:
	push r0
	mov r1, r0
	shl r1, #1
	push pch
	push pcl
	b ub_arg16
	pop r0
	add r0, #1
	eq r0, #4
	bzf .g
	b .arg
.g:
	mov r1, #8
	b ub_arg8

; arguments r0, r0 + 1 as x16, y8 at API_ARGS + r1 (ub_xy8: 0 and 1 at 0)
ub_xy8:
	mov r0, #0
	mov r1, #0
ub_xy8_at:
	push r0
	push r1
	push pch
	push pcl
	b ub_arg16
	pop r1
	add r1, #2
	pop r0
	add r0, #1
	b ub_argy

; palette i, r, g, b: set a palette entry; palette: the default palette back
ub_palette_statement:
	push pch
	push pcl
	b ub_args
	eq r0, #0
	bzf .reset
	eq r0, #4
	bzf .set
	b ub_syntax
.reset:
	b API_GFX_PALETTE_RESET
.set:
	mov r0, #3
.arg:
	push r0
	mov r1, r0
	push pch
	push pcl
	b ub_arg8
	pop r0
	eq r0, #0
	bzf .send
	sub r0, #1
	b .arg
.send:
	b API_GFX_PALETTE

; refresh [m]: the e-ink panel now, m as REFRESH (3 greyscale in mode 2,
; else 0 partial); nothing on HDMI
ub_refresh_statement:
	push pch
	push pcl
	b ub_args
	eq r0, #1
	bzf .given
	eq r0, #0
	bzf .default
	b ub_syntax
.default:
	ld r0, [ub_mode]
	eq r0, #2
	bzf .grey
	xor r0, r0
	b API_EINK_REFRESH
.grey:
	mov r0, #3
	b API_EINK_REFRESH
.given:
	ld r0, [ub_argv]
	b API_EINK_REFRESH

; after a run: a program that left a graphics mode keeps its picture until
; a key, then TEXT comes back (cleared; a fatal error's message again)
ubasic_gfx_done:
	ld r0, [ub_mode]
	eq r0, #0
	bzf .done
	push pch
	push pcl
	b API_GETKEY
	xor r0, r0
	st [ub_mode], r0
	push pch
	push pcl
	b API_GFX_MODE
	ld r0, [ub_failed]
	eq r0, #0
	bzf .done
	push pch
	push pcl
	b ub_fatal_msg
.done:
	pop pcl
	pop pch

token: resb 1
ubasic_statement:
	push pch
	push pcl
	b ubasic_tokenizer_token
	st [token], r0

	eq r0, TOKENIZER_PRINT
	bzf .print
	eq r0, TOKENIZER_IF
	bzf .if
	eq r0, TOKENIZER_GOTO
	bzf .goto
	eq r0, TOKENIZER_GOSUB
	bzf .gosub
	eq r0, TOKENIZER_RETURN
	bzf .return
	eq r0, TOKENIZER_FOR
	bzf .for
	eq r0, TOKENIZER_PEEK
	bzf .peek
	eq r0, TOKENIZER_POKE
	bzf .poke
	eq r0, TOKENIZER_NEXT
	bzf .next
	eq r0, TOKENIZER_END
	bzf .end
	eq r0, TOKENIZER_LET
	bzf .let
	eq r0, TOKENIZER_VARIABLE
	bzf .variable
	eq r0, TOKENIZER_MODE
	bzf ub_mode_statement
	eq r0, TOKENIZER_CLS
	bzf ub_cls_statement
	eq r0, TOKENIZER_COLOR
	bzf ub_color_statement
	eq r0, TOKENIZER_PLOT
	bzf ub_plot_statement
	eq r0, TOKENIZER_LINE
	bzf ub_line_statement
	eq r0, TOKENIZER_BOX
	bzf ub_box_statement
	eq r0, TOKENIZER_PALETTE
	bzf ub_palette_statement
	eq r0, TOKENIZER_REFRESH
	bzf ub_refresh_statement
	; a REM line: the tokenizer already skipped to the next line (or the end)
	eq r0, TOKENIZER_NUMBER
	bzf .done
	eq r0, TOKENIZER_ENDOFINPUT
	bzf .done

.invalid:
	; err
	push pch
	push pcl
	b ubasic_fatal

.print:
	push pch
	push pcl
	b ubasic_print_statement
	b .done

.if:
	push pch
	push pcl
	b ubasic_if_statement
	b .done

.goto:
	push pch
	push pcl
	b ubasic_goto_statement
	b .done

.gosub:
	push pch
	push pcl
	b ubasic_gosub_statement
	b .done

.return:
	push pch
	push pcl
	b ubasic_return_statement
	b .done

.for:
	push pch
	push pcl
	b ubasic_for_statement
	b .done

.peek:
	push pch
	push pcl
	b ubasic_peek_statement
	b .done

.poke:
	push pch
	push pcl
	b ubasic_poke_statement
	b .done

.next:
	push pch
	push pcl
	b ubasic_next_statement
	b .done

.end:
	push pch
	push pcl
	b ubasic_end_statement
	b .done

.let:
	mov r0, TOKENIZER_LET
	push pch
	push pcl
	b ubasic_accept
	; fall through

.variable:
	push pch
	push pcl
	b ubasic_let_statement

.done:
	pop pcl
	pop pch

ubasic_line_statement:
	push pch
	push pcl
	b ubasic_tokenizer_num
	push pch
	push pcl
	b ubasic_index_add

	mov r0, TOKENIZER_NUMBER
	push pch
	push pcl
	b ubasic_accept

	push pch
	push pcl
	b ubasic_statement

	pop pcl
	pop pch

ubasic_run:
	push pch
	push pcl
	b ubasic_tokenizer_finished
	gt r0, #0
	bzf .done

	push pch
	push pcl
	b ubasic_line_statement

.done:
	pop pcl
	pop pch

ubasic_finished:
	push pch
	push pcl
	b ubasic_tokenizer_finished

	ld r1, [ended]

	or r0, r1

	pop pcl
	pop pch

; variable r0 (0-25) = ub_val
ubasic_set_variable:
	gt r0, #25
	bzf .done
	shl r0, #1
	ld r1, [ub_val]
	st [ub_variables]+r0, r1
	add r0, #1
	ld r1, [ub_val+1]
	st [ub_variables]+r0, r1
.done:
	pop pcl
	pop pch

; variable r0 (0-25): r0 low, r1 high
ubasic_get_variable:
	gt r0, #25
	bzf .none
	shl r0, #1
	mov r1, r0
	add r1, #1
	ld r1, [ub_variables]+r1
	ld r0, [ub_variables]+r0
	pop pcl
	pop pch
.none:
	xor r0, r0
	xor r1, r1
	pop pcl
	pop pch

ubasic_fatal:
	mov r0, #1
	st [ended], r0
	st [ub_failed], r0
ub_fatal_msg:
	ub_fatal_error db "BASIC: FATAL ERROR!\n"
	mov r0, #>[ub_fatal_error]
	mov r1, #<[ub_fatal_error]
	push pch
	push pcl
	b str_printstr
	pop pcl
	pop pch

; the line numbered r0 (low), r1 (high) starts at ub_ptr: into the index,
; unless it is there already or the index is full
ubasic_index_add:
	push pch
	push pcl
	b ubasic_index_find		; ub_ix_p - that line's entry, or the end
	or r0, r1
	eq r0, #0
	bzf .new
	b .done
.new:
	ld r0, [ub_ix_p]		; the last entry is kept for the end
	eq r0, #<[ub_line_index+1200]
	bzf .lo_last
	b .add
.lo_last:
	ld r0, [ub_ix_p+1]
	eq r0, #>[ub_line_index+1200]
	bzf .done
.add:
	xor r1, r1
	ld r0, [ub_linenum]
	std [ub_ix_p]+r1, r0
	add r1, #1
	ld r0, [ub_linenum+1]
	std [ub_ix_p]+r1, r0
	add r1, #1
	ld r0, [ub_ptr]
	std [ub_ix_p]+r1, r0
	add r1, #1
	ld r0, [ub_ptr+1]
	std [ub_ix_p]+r1, r0
	add r1, #1
	xor r0, r0				; the end after the new entry
	std [ub_ix_p]+r1, r0
	add r1, #1
	std [ub_ix_p]+r1, r0
.done:
	pop pcl
	pop pch

; where line r0 (low), r1 (high) starts: r0 = high, r1 = low, or 0 if it is
; not in the index. ub_ix_p is left at its entry, or at the index's end.
ubasic_index_find:
	st [ub_linenum], r0
	st [ub_linenum+1], r1
	mov r0, #<[ub_line_index]
	st [ub_ix_p], r0
	mov r0, #>[ub_line_index]
	st [ub_ix_p+1], r0
.loop:
	xor r1, r1
	ldd r0, [ub_ix_p]+r1
	st [ub_ix_n], r0
	mov r1, #1
	ldd r1, [ub_ix_p]+r1
	st [ub_ix_n+1], r1
	or r0, r1
	eq r0, #0
	bzf .nomatch
	ld r0, [ub_ix_n]
	ld r1, [ub_linenum]
	eq r0, r1
	bzf .lo_same
	b .next
.lo_same:
	ld r0, [ub_ix_n+1]
	ld r1, [ub_linenum+1]
	eq r0, r1
	bzf .match
.next:
	ld r0, [ub_ix_p]
	add r0, #4
	st [ub_ix_p], r0
	lt r0, #4
	bzf .carry
	b .loop
.carry:
	ld r0, [ub_ix_p+1]
	add r0, #1
	st [ub_ix_p+1], r0
	b .loop
.match:
	mov r1, #3
	ldd r0, [ub_ix_p]+r1
	mov r1, #2
	ldd r1, [ub_ix_p]+r1
	pop pcl
	pop pch
.nomatch:
	xor r0, r0
	xor r1, r1
	pop pcl
	pop pch

; ------------------------------------------------------------ files on the storage card
; SAVE "NAME", LOAD "NAME" (the kernel API's storage group; DIR and DEL are
; the terminal's). A program is saved as text, a CR LF after each line, so a
; PC can read and edit it. Handle 0.

ub_ni: resb 1
ub_si: resb 2				; SAVE: the next program byte (from $c004)
ub_li: resb 1
ub_ri: resb 1
ub_full: resb 1
ub_n: resb 1				; bytes in ub_buf
ub_buf: resb 128

ub_s_saved db "\nSAVED\n"
ub_s_loaded db "\nLOADED\n"
ub_s_usage db "\nSAVE, LOAD or DEL \"NAME\"\n"

; the name after the command word, quoted or not, into ub_name; r0 = its length
ub_get_name:
	xor r1, r1
.skip_word:
	ld r0, [bas_line]+r1
	gt r0, #32
	bzf .in_word
	b .skip_space
.in_word:
	add r1, #1
	b .skip_word
.skip_space:
	ld r0, [bas_line]+r1
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
	st [ub_ni], r0
.loop:
	ld r0, [bas_line]+r1
	gt r0, #32				; ends at a space, the CR or the terminator
	bzf .char
	b .end
.char:
	eq r0, #34				; or the closing quote
	bzf .end
	push r1
	ld r1, [ub_ni]
	eq r1, #13				; longer than 8.3 - the card refuses 13
	bzf .next
	st [ub_name]+r1, r0
	add r1, #1
	st [ub_ni], r1
.next:
	pop r1
	add r1, #1
	b .loop
.end:
	ld r1, [ub_ni]
	xor r0, r0
	st [ub_name]+r1, r0
	ld r0, [ub_ni]
	pop pcl
	pop pch

; open ub_name as handle 0, mode r1 (0 read, 1 write)
ub_open:
	mov r0, #<[ub_name]
	st API_ARGS, r0
	mov r0, #>[ub_name]
	st $6f01, r0
	xor r0, r0
	b API_ST_OPEN

; the ub_n bytes of ub_buf to handle 0
ub_write:
	mov r0, #<[ub_buf]
	st API_ARGS, r0
	mov r0, #>[ub_buf]
	st $6f01, r0
	ld r1, [ub_n]
	xor r0, r0
	b API_ST_WRITE

; up to 128 bytes of handle 0 into ub_buf, ub_n = how many
ub_read:
	mov r0, #<[ub_buf]
	st API_ARGS, r0
	mov r0, #>[ub_buf]
	st $6f01, r0
	mov r1, #128
	xor r0, r0
	push pch
	push pcl
	b API_ST_READ
	st [ub_n], r1
	pop pcl
	pop pch

; close handle 0
ub_close:
	xor r0, r0
	b API_ST_CLOSE

ub_cmd_save:
	push pch
	push pcl
	b ub_get_name
	eq r0, #0
	bzf .usage
	mov r1, #1
	push pch
	push pcl
	b ub_open
	eq r0, #0
	bzf .opened
	b .error
.opened:
	xor r0, r0
	st [ub_n], r0
	st [ub_si+1], r0
	mov r0, #4				; from the first line
	st [ub_si], r0
.loop:
	ld r1, [ub_si]			; the program's end
	ld r0, $c002
	eq r1, r0
	bzf .lo_end
	b .byte
.lo_end:
	ld r1, [ub_si+1]
	ld r0, $c003
	eq r1, r0
	bzf .last
.byte:
	ld r0, [ub_si+1]
	add r0, PROG_HI
	st [ub_si+1], r0
	ldd r0, [ub_si]
	ld r1, [ub_si+1]
	sub r1, PROG_HI
	st [ub_si+1], r1
	push r0
	ld r1, [ub_n]
	gt r1, #126				; a full chunk - room for a CR LF is left
	bzf .flush
.append:
	pop r0
	ld r1, [ub_n]
	st [ub_buf]+r1, r0
	add r1, #1
	st [ub_n], r1
	eq r0, #13
	bzf .lf
	b .next
.lf:
	mov r0, #10
	ld r1, [ub_n]
	st [ub_buf]+r1, r0
	add r1, #1
	st [ub_n], r1
.next:
	ld r1, [ub_si]
	add r1, #1
	st [ub_si], r1
	eq r1, #0
	bzf .si_hi
	b .loop
.si_hi:
	ld r1, [ub_si+1]
	add r1, #1
	st [ub_si+1], r1
	b .loop
.flush:
	push pch
	push pcl
	b ub_write
	eq r0, #0
	bzf .flushed
	pop r1					; the byte waiting to be appended
	b .close_error
.flushed:
	xor r0, r0
	st [ub_n], r0
	b .append
.last:
	ld r0, [ub_n]
	eq r0, #0
	bzf .close
	push pch
	push pcl
	b ub_write
	eq r0, #0
	bzf .close
	b .close_error
.close:
	push pch
	push pcl
	b ub_close
	eq r0, #0
	bzf .saved
	b .error
.saved:
	mov r0, #>[ub_s_saved]
	mov r1, #<[ub_s_saved]
	push pch
	push pcl
	b str_printstr
	b .done
.close_error:
	push r0
	push pch
	push pcl
	b ub_close
	pop r0
.error:
	push pch
	push pcl
	b API_ST_PERROR
	b .done
.usage:
	mov r0, #>[ub_s_usage]
	mov r1, #<[ub_s_usage]
	push pch
	push pcl
	b str_printstr
.done:
	pop pcl
	pop pch

; the line gathered in bas_line (ub_li characters) into the program, as if
; typed - lines that do not start with a line number are skipped
ub_load_line:
	ld r1, [ub_li]
	eq r1, #0
	bzf .done
	mov r0, #13
	st [bas_line]+r1, r0
	add r1, #1
	xor r0, r0
	st [bas_line]+r1, r0
	st [ub_li], r0
	mov r0, #>[bas_line]
	mov r1, #<[bas_line]
	push pch
	push pcl
	b str_atoi
	gt r1, #0x7f			; a line number is 1-32767, as typed
	bzf .done
	or r0, r1
	eq r0, #0
	bzf .done
	push pch
	push pcl
	b bas_cmd_line
	ld r0, [bas_full]		; refused - the program is full
	eq r0, #0
	bzf .done
	b .full
.full:
	mov r0, #1
	st [ub_full], r0
.done:
	xor r0, r0
	st [ub_li], r0
	pop pcl
	pop pch

ub_cmd_load:
	push pch
	push pcl
	b ub_get_name
	eq r0, #0
	bzf .usage
	push pch
	push pcl
	b ub_load_file
	eq r0, #0
	bzf .loaded
	push pch
	push pcl
	b API_ST_PERROR
	b .done
.loaded:
	mov r0, #>[ub_s_loaded]
	mov r1, #<[ub_s_loaded]
	push pch
	push pcl
	b str_printstr
	b .done
.usage:
	mov r0, #>[ub_s_usage]
	mov r1, #<[ub_s_usage]
	push pch
	push pcl
	b str_printstr
.done:
	pop pcl
	pop pch

; LOAD's work (also exec's): NEW, then the file ub_name's lines as if typed.
; r0 = 0, or the error
ub_load_file:
	xor r1, r1
	push pch
	push pcl
	b ub_open
	eq r0, #0
	bzf .opened
	b .done
.opened:
	push pch
	push pcl
	b bas_cmd_new
	xor r0, r0
	st [ub_li], r0
	st [ub_full], r0
.read:
	push pch
	push pcl
	b ub_read
	eq r0, #0
	bzf .got
	b .close_error
.got:
	xor r0, r0
	st [ub_ri], r0
.byte:
	ld r0, [ub_full]
	eq r0, #0
	bzf .more
	b .close
.more:
	ld r1, [ub_ri]
	ld r0, [ub_n]
	eq r1, r0
	bzf .chunk_done
	ld r0, [ub_buf]+r1
	add r1, #1
	st [ub_ri], r1
	eq r0, #13
	bzf .eol
	eq r0, #10
	bzf .eol
	ld r1, [ub_li]
	eq r1, #78				; the longest line that can be typed
	bzf .byte
	st [bas_line]+r1, r0
	add r1, #1
	st [ub_li], r1
	b .byte
.eol:
	push pch
	push pcl
	b ub_load_line
	b .byte
.chunk_done:
	ld r0, [ub_n]
	eq r0, #128				; a short chunk is the end of the file
	bzf .read
	push pch
	push pcl
	b ub_load_line			; a last line without a line end
.close:
	push pch
	push pcl
	b ub_close
	b .done
.close_error:
	push r0
	push pch
	push pcl
	b ub_close
	pop r0
.done:
	pop pcl
	pop pch
