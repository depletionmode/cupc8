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
