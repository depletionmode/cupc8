; https://github.com/adamdunkels/ubasic

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

program_ptr: resb 2
for_stack_ptr: resb 2
gosub_stack_ptr: resb 2
ended: resb 1
ubasic_init:
	st [program_ptr], r1
	st [program_ptr+1], r0

	xor r0, r0
	st [for_stack_ptr], r0
	st [for_stack_ptr+1], r0
	st [gosub_stack_ptr], r0
	st [gosub_stack_ptr+1], r0

	st [ended], r0

	push pch
	push pcl
	b ubasic_index_free

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
	b ubasic_fatal

.cont:
	push pch
	puch pcl
	b ubasic_tokanizer_next

	pop pcl
	pop pch

r: resb 1
ubasic_varfactor:
	push pch
	push pcl
	b ubasic_tokenizer_variable_num
	
	push pch
	push pcl
	b ubasic_get_variable
	st [r], r0

	mov r0, TOKENIZER_VARIABLE
	push pch
	push pcl
	b ubasic_accept

	ld r0, [r]
	pop pcl
	pop pch

ubasic_factor:
	push pch
	puch pcl
	b ubasic_tokenizer_token

	eq r0, TOKENIZER_NUMBER
	bzf .number
	eq r0, TOKENIZER_LEFTPAREN
	bzf .leftparen
	; default
	push pch
	push pcl
	b ubasic_varfactor
	st [r], r0
	b .end

.number:
	push pch
	push pcl
	b ubasic_tokenizer_num
	st [r], r0

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

	mov r0, TOKENIZER_RIGHTPAREN
	push pch
	push pcl
	b ubasic_accept

.end:
	ld r0, [r]
	pop pcl
	pop pch

f1: resb 1
f2: resb 1
op: resb 1
ubasic_term:
	push pch
	push pcl
	b ubasic_factor
	st [f1], r0

	push pch
	push pcl
	b ubasic_tokenizer_token
	st [op], r0

.loop:	
	ld r0, [op]
	eq r0, TOKENIZER_ASTR
	bzf .next
	eq r0, TOKENIZER_SLASH
	bzf .next
	eq r0, TOKENIZER_MOD
	bzf .next
	b .end

.next:
	push pch
	puch pcl
	b ubasic_tokenizer_next

	push pch
	push pcl
	b ubasic_factor
	st [f2], r0

	ld r0, [op]
	eq r0, TOKENIZER_ASTR
	bzf .astr
	eq r0, TOKENIZER_SLASH
	bzf .slash
	eq r0, TOKENIZER_MOD
	bzf .mod
	b .getop

.astr:
	ld r0, [f1]
	ld r1, [f2]
    push pch
    push pcl
    b math_mul
    st [f1], r0
	b .getop

.slash:
	ld r0, [f1]
	ld r1, [f2]
    push pch
    push pcl
    ;todo b math_div
    st [f1], r0
	b .getop

.mod:
	ld r0, [f1]
	ld r1, [f2]
    push pch
    push pcl
    ;todo b math_mod
    st [f1], r0
	b .getop

.getop:
	push pch
	push pcl
	b ubasic_tokenizer_token
	st [op], r0

	b .loop

.end:
	ld r0, [f1]
	pop pcl
	pop pch

t1: resb 1
t2: resb 1
ubasic_expr:
	push pch
	push pcl
	b ubasic_term
	st [t1], r0

	push pch
	push pcl
	b ubasic_tokenizer_token
	st [op], r0

.loop:	
	ld r0, [op]
	eq r0, TOKENIZER_PLUS
	bzf .next
	eq r0, TOKENIZER_MINUS
	bzf .next
	eq r0, TOKENIZER_AND
	bzf .next
	eq r0, TOKENIZER_OR
	bzf .next
	b .end

.next:
	push pch
	puch pcl
	b ubasic_tokenizer_next

	push pch
	push pcl
	b ubasic_factor
	st [t2], r0

	ld r0, [op]
	eq r0, TOKENIZER_PLUS
	bzf .plus
	eq r0, TOKENIZER_MINUS
	bzf .minus
	eq r0, TOKENIZER_AND
	bzf .and
	eq r0, TOKENIZER_OR
	bzf .or
	b .getop

.plus:
	ld r0, [t1]
	ld r1, [t2]
	add r0, r1
    st [t1], r0
	b .getop

.minus:
	ld r0, [t1]
	ld r1, [t2]
	sub r0, r1
    st [t1], r0
	b .getop

.and:
	ld r0, [t1]
	ld r1, [t2]
	and r0, r1
    st [t1], r0
	b .getop

.or:
	ld r0, [t1]
	ld r1, [t2]
	or r0, r1
    st [t1], r0
	b .getop

.getop:
	push pch
	push pcl
	b ubasic_tokenizer_token
	st [op], r0

	b .loop

.end:
	ld r0, [t1]
	pop pcl
	pop pch

re1: resb 1
re2: resb 1
ubasic_relation:
	push pch
	push pcl
	b ubasic_expr
	st [re1], r0

	push pch
	push pcl
	b ubasic_tokenizer_token
	st [op], r0

.loop:	
	ld r0, [op]
	eq r0, TOKENIZER_LT
	bzf .next
	eq r0, TOKENIZER_GT
	bzf .next
	eq r0, TOKENIZER_EQ
	bzf .next
	b .end

.next:
	push pch
	puch pcl
	b ubasic_tokenizer_next

	push pch
	push pcl
	b ubasic_factor
	st [re2], r0

	ld r0, [op]
	eq r0, TOKENIZER_LT
	bzf .lt
	eq r0, TOKENIZER_GT
	bzf .gt
	eq r0, TOKENIZER_EQ
	b .getop

.lt:
	ld r0, [re1]
	ld r1, [re2]
	lt r0, r1
	bzf .islt
	mov r0, #0
	b .lt_next
.islt:
	mov r0, #1
.lt_next:
    st [re1], r0
	b .getop

.gt:
	ld r0, [re1]
	ld r1, [re2]
	gt r0, r1
	bzf .isgt
	mov r0, #0
	b .gt_next
.isgt:
	mov r0, #1
.gt_next:
    st [re1], r0
	b .getop

.eq:
	ld r0, [re1]
	ld r1, [re2]
	eq r0, r1
	bzf .iseq
	mov r0, #0
	b .eq_next
.iseq:
	mov r0, #1
.eq_next:
    st [re1], r0
	b .getop

.getop:
	push pch
	push pcl
	b ubasic_tokenizer_token
	st [op], r0

	b .loop

.end:
	ld r0, [re1]
	pop pcl
	pop pch

ubasic_index_free:
	; todo - implement fcn - address mess
	ld r0, [line_index_head]
	eq r0, #0
	bzf .end

	st [line_index_current], r0

.loop:
	ld r0, [line_index_current]
	st [line_index_head], r0

.end:
	pop pcl
	pop pch

linenum: resb 1
ubasic_jump_linenum_slow:
	st [linenum], r0

	ld r0, [program_ptr]
	push pch
	push pcl
	b ubasic_tokenizer_init

.loop0:
	push pch
	push pcl
	b ubasic_tokenizer_num
	ld r1, [linenum]
	eq r0, r1
	bzf .end

.loop1:
.loop2:
	push pch
	push pcl
	b ubasic_tokenizer_next
	push pch
	push pcl
	b ubasic_tokenizer_token
	eq r0, TOKENIZER_CR
	bzf .n0
	push pch
	push pcl
	b ubasic_tokenizer_token
	eq r0, TOKENIZER_ENDOFINPUT
	bzf .n0
	b .loop2
.n0:
	push pch
	push pcl
	b ubasic_tokenizer_token
	eq r0, TOKENIZER_CR
	bzf .n1
	b .n2
.n1:
	push pch
	push pcl
	b ubasic_tokenizer_next
.n2:	
	push pch
	push pcl
	b ubasic_tokenizer_token
	eq r0, TOKENIZER_NUMBER
	bzf .loop0
	b .loop1
	
.end:
	pop pcl
	pop pch

pos: resb 1
ubasic_jump_linenum:
	st [linenum], r0
	push pch
	push pcl
	b ubasic_index_find
	st [pos], r0
	eq r0, #0
	bzf .pos_null
	push pch
	push pcl
	b ubasic_tokanizer_goto
	b .end
.pos_null:
	ld r0, [linenum]
	push pch
	push pcl
	b ubasic_jump_linenum_slow
.end:
	pop pcl
	pop pch
	
ubasic_goto_statement:
	push pch
	push pcl
	mov r0, TOKENIZER_GOTO
	b ubasic_accept

	push pch
	push pcl
	b ubasic_tokenizer_num
	push pch
	push pcl
	b ubasic_jump_linenum

	pop pcl
	pop pch

ubasic_print_statement:
	push pch
	push pcl
	mov r0, TOKENIZER_PRINT
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
	b .end

.string:
	; todo
	push pch
	push pcl
	b ubasic_tokenizer_next
	b .next
.comma
	; todo
	push pch
	push pcl
	b ubasic_tokenizer_next
	b .next
.semicolon
	; todo
	push pch
	push pcl
	b ubasic_tokenizer_next
	b .next
.var_or_num
	; todo
	b .next
.
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
	; todo - print eol
	push pch
	push pcl
	b ubasic_tokanizer_next

	pop pcl
	pop pch

ubasic_if_statement:
	mov r0, TOKENIZER_IF
	push pch
	push pcl
	b ubasic_accept

	push pch
	push pcl
	b ubasic_relation
	st [r], r0

	mov r0, TOKENIZER_THEN
	push pch
	push pcl
	b ubasic_accept

	ld r0, [r]
	eq r0, #0
	bzf .else
	push pch
	push pcl
	b ubasic_statement
	b .end
.else:
.loop:
	push pch
	puch pcl
	b ubasic_tokenizer_next
	push pch
	puch pcl
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
	puch pcl
	b ubasic_tokenizer_token
	eq r0, TOKENIZER_ELSE
	bzf .tok_else
	eq r0, TOKENIZER_CR
	bzf .tok_next

.tok_else:
	push pch	
	push pcl
	b ubasic_tokanizer_next
	push pch	
	push pcl
	b ubasic_statement
	b .end

.tok_next:
	push pch	
	push pcl
	b ubasic_tokanizer_next

.end:
	pop pcl
	pop pch
