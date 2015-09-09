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

ubasic_get_next_token:
	;todo

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
	eq r1, #0
	bzf .carry0
	b .aftercarry0
.carry0:
	add r0, #1
	st [ub_ptr+1], r0
.aftercarry0:
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
	mov r0, #>[ub_ptr]
	mov r1, #<[ub_ptr]
	push pch
	push pcl
	b str_atoi	; todo implement str_atoi

.done:
	pop pcl
	pop pch

ubasic_tokenizer_string:
	; todo
.done:
	pop pcl
	pop pch

ubasic_tokenizer_finished:
	ld r0, [ub_ptr]
	ld r1, [ub_ptr]
	or r0, r1
	ld r1, [ub_current_token]
	eq r1, TOKENIZER_ENDOFINPUT
	bzf .eoi
	mov r1, #0
	b .done
.eoi:
	mov r1, #1
.done:
	or r0, r1
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
