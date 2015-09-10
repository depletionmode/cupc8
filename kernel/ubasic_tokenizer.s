ub_nextptr: resb 2
ub_current_token: resb 1

ubasic_singlechar:
	ldd r0, [ub_ptr]

	eq r0, #10
	bzf .cr
	eq r0, #13
	bzf .cr
	eq r0, #44
	bzf .comma
	eq r0, #59
	bzf .semicolon
	eq r0, #43
	bzf .plus
	eq r0, #45
	bzf .minus
	eq r0, #38
	bzf .and
	eq r0, #124
	bzf .or
	eq r0, #42
	bzf .astr
	eq r0, #47
	bzf .slash
	eq r0, #37
	bzf .mod
	eq r0, #40
	bzf .lparen
	eq r0, #41
	bzf .rparen
	eq r0, #35
	bzf .hash
	eq r0, #60
	bzf .lt
	eq r0, #32
	bzf .gt
	eq r0, #61
	bzf .eq

	mov r0, #0
	b .done

.cr:
	mov r0, TOKENIZER_CR
	b .done

.comma:
	mov r0, TOKENIZER_COMMA
	b .done

.semicolon:
	mov r0, TOKENIZER_SEMICOLON
	b .done

.plus:
	mov r0, TOKENIZER_PLUS
	b .done

.minus:
	mov r0, TOKENIZER_MINUS
	b .done

.and:
	mov r0, TOKENIZER_AND
	b .done

.or:
	mov r0, TOKENIZER_OR
	b .done

.astr:
	mov r0, TOKENIZER_ASTR
	b .done

.slash:
	mov r0, TOKENIZER_SLASH
	b .done

.mod:
	mov r0, TOKENIZER_MOD
	b .done

.lparen:
	mov r0, TOKENIZER_LEFTPAREN
	b .done

.hash:
	mov r0, TOKENIZER_HASH
	b .done

.rparen:
	mov r0, TOKENIZER_RIGHTPAREN
	b .done

.lt:
	mov r0, TOKENIZER_LT
	b .done

.gt:
	mov r0, TOKENIZER_GT
	b .done

.eq:
	mov r0, TOKENIZER_EQ
	b .done

.done:
	pop pcl
	pop pch

ubasic_isdigit:
	mov r1, r0
	xor r0, r0
	lt r1, #48
	bzf .done
	gt r1, #57
	bzf .done
	mov r0, #1
	
.done:
	pop pcl
	pop pch

ubasic_isdigit_ptr:
	ldd r0, [ub_ptr]
	push pch
	push pcl
	b ubasic_isdigit
	
.done:
	pop pcl
	pop pch

ubasic_set_nextptr_ptr_plus_val:
	; helper fcn for ubasic_get_next_token
	; r0: vlaue to add

	ld r1, [ub_ptr]
	add r1, r0
	st [ub_nextptr], r1
	; check wraparound
	lt r1, r0
	bzf .wraparound
.nowraparound:
	b .done
.wraparound:
	ld r1, [ub_ptr+1]
	add r1, #1
	st [ub_nextptr+1], r1

.done:
	pop pcl
	pop pch

ub_s_let db "let"
ub_s_print db "print"
ub_s_if db "if"
ub_s_then db "then"
ub_s_else db "else"
ub_s_for db "for"
ub_s_to db "to"
ub_s_next db "next"
ub_s_goto db "goto"
ub_s_gosub db "gosub"
ub_s_return db "return"
ub_s_call db "call"
ub_s_rem db "rem"
ub_s_peek db "peek"
ub_s_poke db "poke"
ub_s_end db "end"
ubasic_get_next_token:
	ldd r0, [ub_ptr]
	gt r0, #0
	bzf .if0
	mov r0, TOKENIZER_ENDOFINPUT
	b .done

.if0:
	push pch
	push pcl
	b ubasic_isdigit_ptr
	eq r0, #0
	bzf .elseif0_0

	xor r1, r1 ; r1 = i
	push r1
.loop:
	pop r1
	gt r1, #5
	bzf .error
.if1:
	ldd r0, [ub_ptr]+r1
	push r1
	push pch
	push pcl
	b ubasic_isdigit
	pop r1
	gt r0, #0
	bzf .else1
.if2:
	eq r1, #0
	bzf .else2
	ld r1, [ub_ptr]
	ld r0, [ub_ptr+1]
	add r1, #1
	gt r1, #0
	bzf .nocarry0
	add r0, #1
.nocarry0:
	st [ub_nextptr], r1
	st [ub_nextptr+1], r0
	mov r0, TOKENIZER_NUMBER
	b .done
.else2:
	b .error
.else1:
	add r1, #1
	push r1
	b .loop	

.elseif0_0:
	push pch
	push pcl
	b ubasic_singlechar
	push r0
	eq r0, #0
	bzf .elseif0_1
	ld r1, [ub_ptr]
	ld r0, [ub_ptr+1]
	add r1, #1
	gt r1, #0
	bzf .nocarry1
	add r0, #1
.nocarry1:
	st [ub_nextptr], r1
	st [ub_nextptr+1], r0
	pop r0
	b .done
	
.elseif0_1:
	pop r0
	ldd r0, [ub_ptr]
	eq r0, #34
	bzf .true0_1
	b .else0	
.true0_1:
	ld r1, [ub_ptr]
	ld r0, [ub_ptr+1]
	st [ub_nextptr], r1
	st [ub_nextptr+1], r0
.loop1:
	ld r1, [ub_nextptr]
	ld r0, [ub_nextptr+1]
	add r1, #1
	gt r1, #0
	bzf .nocarry2
	add r0, #1
.nocarry2:
	st [ub_nextptr], r1
	st [ub_nextptr+1], r0
	ldd r0, [ub_nextptr]
	eq r0, #34
	bzf .loop1_end
	b .loop1
.loop1_end:
	ld r1, [ub_nextptr]
	ld r0, [ub_nextptr+1]
	add r1, #1
	gt r1, #0
	bzf .nocarry3
	add r0, #1
.nocarry3:
	st [ub_nextptr], r1
	st [ub_nextptr+1], r0
	mov r0, TOKENIZER_STRING
	b .done
	
.else0:
	ld r0, [ub_ptr+1]
	ld r1, [ub_ptr]
	push pch
	push pcl
	b str_cmp_set

	mov r0, #>[ub_s_let]
	mov r1, #<[ub_s_let]
	push pch
	push pcl
	b str_cmp
	gt r0, #0
	bzf .n0
	mov r0, #3	; strlen
	push pch
	push pcl
	b ubasic_set_nextptr_ptr_plus_val
	mov r0, TOKENIZER_LET
	b .done
.n0:
	mov r0, #>[ub_s_print]
	mov r1, #<[ub_s_print]
	push pch
	push pcl
	b str_cmp
	gt r0, #0
	bzf .n1
	mov r0, #5	; strlen
	push pch
	push pcl
	b ubasic_set_nextptr_ptr_plus_val
	mov r0, TOKENIZER_PRINT
	b .done
.n1:
	mov r0, #>[ub_s_if]
	mov r1, #<[ub_s_if]
	push pch
	push pcl
	b str_cmp
	gt r0, #0
	bzf .n2
	mov r0, #2	; strlen
	push pch
	push pcl
	b ubasic_set_nextptr_ptr_plus_val
	mov r0, TOKENIZER_IF
	b .done
.n2:
	mov r0, #>[ub_s_then]
	mov r1, #<[ub_s_then]
	push pch
	push pcl
	b str_cmp
	gt r0, #0
	bzf .n3
	mov r0, #4	; strlen
	push pch
	push pcl
	b ubasic_set_nextptr_ptr_plus_val
	mov r0, TOKENIZER_THEN
	b .done
.n3:
	mov r0, #>[ub_s_else]
	mov r1, #<[ub_s_else]
	push pch
	push pcl
	b str_cmp
	gt r0, #0
	bzf .n4
	mov r0, #4	; strlen
	push pch
	push pcl
	b ubasic_set_nextptr_ptr_plus_val
	mov r0, TOKENIZER_ELSE
	b .done
.n4:
	mov r0, #>[ub_s_for]
	mov r1, #<[ub_s_for]
	push pch
	push pcl
	b str_cmp
	gt r0, #0
	bzf .n5
	mov r0, #3	; strlen
	push pch
	push pcl
	b ubasic_set_nextptr_ptr_plus_val
	mov r0, TOKENIZER_FOR
	b .done
.n5:
	mov r0, #>[ub_s_to]
	mov r1, #<[ub_s_to]
	push pch
	push pcl
	b str_cmp
	gt r0, #0
	bzf .n6
	mov r0, #2	; strlen
	push pch
	push pcl
	b ubasic_set_nextptr_ptr_plus_val
	mov r0, TOKENIZER_TO
	b .done
.n6:
	mov r0, #>[ub_s_next]
	mov r1, #<[ub_s_next]
	push pch
	push pcl
	b str_cmp
	gt r0, #0
	bzf .n7
	mov r0, #4	; strlen
	push pch
	push pcl
	b ubasic_set_nextptr_ptr_plus_val
	mov r0, TOKENIZER_NEXT
	b .done
.n7:
	mov r0, #>[ub_s_goto]
	mov r1, #<[ub_s_goto]
	push pch
	push pcl
	b str_cmp
	gt r0, #0
	bzf .n8
	mov r0, #4	; strlen
	push pch
	push pcl
	b ubasic_set_nextptr_ptr_plus_val
	mov r0, TOKENIZER_GOTO
	b .done
.n8:
	mov r0, #>[ub_s_gosub]
	mov r1, #<[ub_s_gosub]
	push pch
	push pcl
	b str_cmp
	gt r0, #0
	bzf .n9
	mov r0, #5	; strlen
	push pch
	push pcl
	b ubasic_set_nextptr_ptr_plus_val
	mov r0, TOKENIZER_GOSUB
	b .done
.n9:
	mov r0, #>[ub_s_return]
	mov r1, #<[ub_s_return]
	push pch
	push pcl
	b str_cmp
	gt r0, #0
	bzf .n10
	mov r0, #6	; strlen
	push pch
	push pcl
	b ubasic_set_nextptr_ptr_plus_val
	mov r0, TOKENIZER_RETURN
	b .done
.n10:
	mov r0, #>[ub_s_call]
	mov r1, #<[ub_s_call]
	push pch
	push pcl
	b str_cmp
	gt r0, #0
	bzf .n11
	mov r0, #4	; strlen
	push pch
	push pcl
	b ubasic_set_nextptr_ptr_plus_val
	mov r0, TOKENIZER_CALL
	b .done
.n11:
	mov r0, #>[ub_s_rem]
	mov r1, #<[ub_s_rem]
	push pch
	push pcl
	b str_cmp
	gt r0, #0
	bzf .n12
	mov r0, #3	; strlen
	push pch
	push pcl
	b ubasic_set_nextptr_ptr_plus_val
	mov r0, TOKENIZER_REM
	b .done
.n12:
	mov r0, #>[ub_s_peek]
	mov r1, #<[ub_s_peek]
	push pch
	push pcl
	b str_cmp
	gt r0, #0
	bzf .n13
	mov r0, #4	; strlen
	push pch
	push pcl
	b ubasic_set_nextptr_ptr_plus_val
	mov r0, TOKENIZER_PEEK
	b .done
.n13:
	mov r0, #>[ub_s_poke]
	mov r1, #<[ub_s_poke]
	push pch
	push pcl
	b str_cmp
	gt r0, #0
	bzf .n14
	mov r0, #4	; strlen
	push pch
	push pcl
	b ubasic_set_nextptr_ptr_plus_val
	mov r0, TOKENIZER_POKE
	b .done
.n14:
	mov r0, #>[ub_s_end]
	mov r1, #<[ub_s_end]
	push pch
	push pcl
	b str_cmp
	gt r0, #0
	bzf .error
	mov r0, #3	; strlen
	push pch
	push pcl
	b ubasic_set_nextptr_ptr_plus_val
	mov r0, TOKENIZER_END
	b .done

.variable:
	ldd r0, [ub_ptr]
	lt r0, #97
	bzf .error
	gt r0, #122
	bzf .error
	ld r1, [ub_ptr]
	ld r0, [ub_ptr+1]
	add r1, #1
	gt r1, #0
	bzf .nocarry
	add r0, #1
.nocarry:
	st [ub_nextptr], r1
	st [ub_nextptr+1], r0
	mov r0, TOKENIZER_VARIABLE
	b .done
	
.error:
	mov r0, TOKENIZER_ERROR

.done:
	pop pcl
	pop pch

ubasic_tokenizer_goto:
	; program pointer r0||r1
	st [ub_ptr], r1
	st [ub_ptr+1], r0

	push pch
	push pcl
	b ubasic_get_next_token
	st [ub_current_token], r0

.done:
	pop pcl
	pop pch

ubasic_tokenizer_init:
	; program pointer r0||r1
	push pch
	push pcl
	b ubasic_tokenizer_goto

	; is this redundant?
	push pch
	push pcl
	b ubasic_get_next_token

	st [ub_current_token], r0

.done:
	pop pcl
	pop pch

ubasic_tokenizer_token:
	ld r0, [ub_current_token]

	pop pcl
	pop pch

ubasic_tokenizer_next:
	push pch
	push pcl
	b ubasic_tokenizer_finished
	gt r0, #0
	bzf .done

	ld r1, [ub_nextptr]
	ld r0, [ub_nextptr+1]
	st [ub_ptr], r1
	st [ub_ptr+1], r0
	
.loop0:
	ldd r0, [ub_ptr]
	eq r0, #32
	bzf .space
	b .n0
.space:
	; inc ub_ptr
	ld r1, [ub_ptr]
	ld r0, [ub_ptr+1]
	add r1, #1
	gt r1, #0
	bzf .nocarry
	add r0, #1
	st [ub_ptr+1], r0
.nocarry:
	st [ub_ptr], r1

.n0:
	push pch
	push pcl
	b ubasic_get_next_token
	st [ub_current_token], r0

	eq r0, TOKENIZER_REM
	bzf .rem
	b .done

.rem:
.loop1:
	ldd r0, [ub_nextptr]
	eq r0, #10
	bzf .mark
	eq r0, #13
	bzf .mark
	mov r1, #0
	b .bb
.mark:
	mov r1, #1
.bb:
	push pch
	push pcl
	b ubasic_tokenizer_finished
	or r0, r1
	eq r0, #0
	bzf .inc_nextptr0
	b .n1

.inc_nextptr0:
	; inc ub_nextptr
	ld r1, [ub_nextptr]
	ld r0, [ub_nextptr+1]
	add r1, #1
	eq r1, #0
	bzf .carry1
	b .aftercarry1
.carry1:
	add r0, #1
	st [ub_nextptr+1], r0
.aftercarry1:
	st [ub_nextptr], r1
	b .loop0

.n1:
	ldd r0, [ub_nextptr]
	eq r0, #10
	bzf .inc_nextptr
	eq r0, #13
	bzf .inc_nextptr
	b .after_inc_nextptr
.inc_nextptr:
	; inc ub_nextptr
	ld r1, [ub_nextptr]
	ld r0, [ub_nextptr+1]
	add r1, #1
	eq r1, #0
	bzf .carry2
	b .aftercarry2
.carry2:
	add r0, #1
	st [ub_nextptr+1], r0
.aftercarry2:
	st [ub_nextptr], r1
.after_inc_nextptr:
	push pch
	push pcl
	b ubasic_tokenizer_next

.done:
	pop pcl
	pop pch

ubasic_tokenizer_num:
	ld r1, [ub_ptr]
	ld r0, [ub_ptr+1]
	push pch
	push pcl
	b str_atoi

.done:
	pop pcl
	pop pch

ub_tok_str_len: resb 1
ub_tok_str_end_ptr: resb 2
ub_tok_str_len_arg: resb 1
ubasic_tokenizer_string:
	st [ub_tok_str_len_arg], r0
	;push pch
	;push pcl
	;b ubasic_tokenizer_token
	;eq r0, TOKENIZER_STRING
	;bzf .cont
	;b .done

.cont:
	ld r0, [ub_ptr+1]
	ld r1, [ub_ptr]
	add r1, #1
	eq r1, #0
	bzf .carry
.	b .nocarry
.carry:
	add r0, #1
.nocarry:
	push pch
	push pcl
	b str_chr_set
	mov r0, #34
	push pch
	push pcl
	b str_chr
	st [ub_tok_str_end_ptr], r1
	st [ub_tok_str_end_ptr+1], r0
	eq r0, #0	; it's enough to test high byte here
	bzf .done
	; subtract low byte only as have max length < 256
	ld r0, [ub_ptr]
	sub r1, r0
	sub r1, #1
	st [ub_tok_str_len], r1
	ld r0, [ub_tok_str_len_arg]
	lt r0, r1
	bzf .arg_len
	b .next
.arg_len:
	st [ub_tok_str_len], r0
.next:
	; todo memcpy
	ld r1, [ub_tok_str_len]	
	st [ub_string]+r1, #0
.done:
	pop pcl
	pop pch

ubasic_tokenizer_finished:
	ld r1, [ub_ptr]
	ld r0, [ub_ptr+1]
	or r0, r1
	eq r0, #0
	bzf .eoi
	ld r1, [ub_current_token]
	eq r1, TOKENIZER_ENDOFINPUT
	bzf .eoi
	mov r0, #0
	b .done
.eoi:
	mov r0, #1
.done:
	pop pcl
	pop pch

ubasic_tokenizer_variable_num:
	ldd r0, [ub_ptr]
	sub r0, #97

	pop pcl
	pop pch

ubasic_tokenizer_pos:
	; NOTE: unused; use ub_ptr directly!
	; r0 high
	; r1 low
	mov r0, #>[ub_ptr]
	mov r1, #<[ub_ptr]

	pop pcl
	pop pch
