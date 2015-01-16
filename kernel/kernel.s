; kernel entry point
main:
    mov r0, #65    ; 'A'
    push pch
    push pcl
    b .print_char

    mov r0, #255
    st $f000, r0
hang:
    nop
    b .hang
