; kernel entry point
main:
    push pch
    push pcl
    b .print_msg

;    push pch
;    push pcl
;    b .clr_screen

    push pch
    push pcl
    b .dump_char_rom

    mov r0, #255
    st $f000, r0

kernel_loop:
    nop
    b .kernel_loop
