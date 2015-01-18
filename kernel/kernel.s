; kernel entry point
main:
;    push pch
;    push pcl
;    b .fill_screen_pixels

    push pch
    push pcl
    b .print_msg

    push pch
    push pcl
    b .dump_char_rom

    mov r0, #255
    st $f000, r0
hang:
    nop
    b .hang
