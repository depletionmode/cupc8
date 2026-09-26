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
	eq r0, #62
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
	ld r0, [ub_ptr+1]
	st [ub_nextptr+1], r0
	; carry out of the low byte: the sum is below what was added
	ld r0, [ub_ptr]
	lt r1, r0
	bzf .wraparound
	b .done
.wraparound:
	ld r1, [ub_ptr+1]
	add r1, #1
	st [ub_nextptr+1], r1

.done:
	pop pcl
	pop pch

; the keywords in token order, each followed by a space: LET (5) to END
; (20), then MODE (37) to REFRESH (44). None is the start of another.
ub_keywords db "let print if then else for to next goto gosub return call rem peek poke end mode cls color plot line box palette refresh "
ub_kw_i: resb 1
ub_kw_j: resb 1
ub_kw_tok: resb 1
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
	gt r1, #5				; a number is at most 5 digits (32767)
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
	mov r0, r1
	push pch
	push pcl
	b ubasic_set_nextptr_ptr_plus_val
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
	; a keyword: the text at ub_ptr starts with it
	xor r0, r0
	st [ub_kw_i], r0
	mov r0, TOKENIZER_LET
	st [ub_kw_tok], r0
.word:
	ld r1, [ub_kw_i]
	ld r0, [ub_keywords]+r1
	eq r0, #0
	bzf .variable
	xor r0, r0
	st [ub_kw_j], r0
.char:
	ld r1, [ub_kw_i]
	ld r0, [ub_keywords]+r1
	eq r0, #32
	bzf .matched
	ld r1, [ub_kw_j]
	ldd r1, [ub_ptr]+r1
	eq r0, r1
	bzf .same
.skip:
	ld r1, [ub_kw_i]		; to the next word
	ld r0, [ub_keywords]+r1
	add r1, #1
	st [ub_kw_i], r1
	eq r0, #32
	bzf .next_word
	b .skip
.same:
	ld r0, [ub_kw_i]
	add r0, #1
	st [ub_kw_i], r0
	ld r0, [ub_kw_j]
	add r0, #1
	st [ub_kw_j], r0
	b .char
.next_word:
	ld r0, [ub_kw_tok]
	add r0, #1
	eq r0, #21				; after END - MODE
	bzf .graphics
	b .kw_tok
.graphics:
	mov r0, TOKENIZER_MODE
.kw_tok:
	st [ub_kw_tok], r0
	b .word
.matched:
	ld r0, [ub_kw_j]
	push pch
	push pcl
	b ubasic_set_nextptr_ptr_plus_val
	ld r0, [ub_kw_tok]
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
	ub_s_tokenizer_error db "BASIC: TOKENIZER ERROR!\n"
	mov r0, #>[ub_s_tokenizer_error]
	mov r1, #<[ub_s_tokenizer_error]
	push pch
	push pcl
	b str_printstr
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
	b .loop0

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
	push r1			; tokenizer_finished uses r1
	push pch
	push pcl
	b ubasic_tokenizer_finished
	pop r1
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
	b .loop1

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

ub_str_src: resb 2
ubasic_tokenizer_string:
	; the string token at ub_ptr, without its quotes, into ub_string
	ld r1, [ub_ptr]
	ld r0, [ub_ptr+1]
	add r1, #1
	eq r1, #0
	bzf .carry
	b .set
.carry:
	add r0, #1
.set:
	st [ub_str_src], r1
	st [ub_str_src+1], r0
	xor r1, r1
.loop:
	ldd r0, [ub_str_src]+r1
	eq r0, #34
	bzf .end
	eq r0, #0
	bzf .end
	eq r1, #39
	bzf .end
	st [ub_string]+r1, r0
	add r1, #1
	b .loop
.end:
	xor r0, r0
	st [ub_string]+r1, r0
	pop pcl
	pop pch

ubasic_tokenizer_finished:
	ldd r0, [ub_ptr]
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
