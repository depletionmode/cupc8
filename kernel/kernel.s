; kernel entry point
main:
;'	s_kernel_ver db "\nCUPCAKE KERNEL v0.1\n"
;'	mov r0, #>[s_kernel_ver]
;'	mov r1, #<[s_kernel_ver]
;'    push pch
;'    push pcl
;'	b print_string
;'
;'	s_ubasic_test db "\nuBASIC test...\n"
;'	mov r0, #>[s_ubasic_test]
;'	mov r1, #<[s_ubasic_test]
;'    push pch
;'    push pcl
;'	b print_string

	;s_ubasic_program db "10 gosub 100\n20 for i = 1 to 10\n30 print i\n40 next i\n50 print \"end\"\n60 end\n100 print \"subroutine\"\n110 return\n"
	;s_ubasic_program db "10 let a = 42\n20 end\n"
	s_ubasic_program db "5 print \"a\"\n10 let a = 42\n20 end\n"
	mov r0, #>[s_ubasic_program]
	mov r1, #<[s_ubasic_program]
	push pch
	push pcl
	b ubasic_init
.ubasic_loop:
	push pch
	push pcl
	b ubasic_run
	push pch
	push pcl
	b ubasic_finished
	eq r0, #0
	bzf .ubasic_loop

;	s_ubasic_test_done db "\nDONE!\n"
;	mov r0, #>[s_ubasic_test_done]
;	mov r1, #<[s_ubasic_test_done]
;    push pch
;    push pcl
;	b print_string
	

;	s_prompt db "\n>> "
;	mov r0, #>[s_prompt]
;	mov r1, #<[s_prompt]
;    push pch
;    push pcl
;	b print_string
;
;	mov r0, #1
;	push pch
;	push pcl
;	b set_echo_char
;
;	s_buf0: resb 256
;.readstring:
;	mov r0, #>[s_buf0]
;	mov r1, #<[s_buf0]
;	push pch
;	push pcl
;	b read_string
;	mov r0, #>[s_buf0]
;	mov r1, #<[s_buf0]
;    push pch
;    push pcl
;	b print_string
;b .readstring
;
;.charloop:
;	push pch
;	push pcl
;	b keyb_read_char
;	sub r0, #32
;	push pch
;	push pcl
;	b print_ascii_char
;	b .charloop

;    push pch
;    push pcl
;    b print_msg

;    push pch
;    push pcl
;    b clr_screen

;    push pch
;    push pcl
;    b dump_char_rom

    mov r0, #255
    st $f000, r0

	halt

kernel_loop:
    nop
    b kernel_loop
