; kernel entry point
main:
	s_kernel_ver db "\nCUPCAKE KERNEL v0.1\n"
	mov r0, #>[s_kernel_ver]
	mov r1, #<[s_kernel_ver]
    push pch
    push pcl
	b print_string

	s_prompt db "\n>> "
	mov r0, #>[s_prompt]
	mov r1, #<[s_prompt]
    push pch
    push pcl
	b print_string

	mov r0, #1
	push pch
	push pcl
	b set_echo_char

	s_buf0: resb 256
.readstring:
	mov r0, #>[s_buf0]
	mov r1, #<[s_buf0]
	push pch
	push pcl
	b read_string
	mov r0, #>[s_buf0]
	mov r1, #<[s_buf0]
    push pch
    push pcl
	b print_string
b .readstring

.charloop:
	push pch
	push pcl
	b keyb_read_char
	sub r0, #32
	push pch
	push pcl
	b print_ascii_char
	b .charloop

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
