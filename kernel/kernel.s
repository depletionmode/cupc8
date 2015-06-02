; kernel entry point
main:
	s_kernel_ver db "\nCUPCAKE KERNEL v0.1\n"
	mov r0, #>[s_kernel_ver]
	mov r1, #<[s_kernel_ver]
    push pch
    push pcl
	b print_string

    push pch
    push pcl
    b print_msg

;    push pch
;    push pcl
;    b clr_screen

    push pch
    push pcl
    b dump_char_rom

    mov r0, #255
    st $f000, r0

	halt

kernel_loop:
    nop
    b kernel_loop
