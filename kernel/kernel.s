; kernel entry point
main:
    nop
    mov r0, #65    ; 'A'
    push pch
    push pcl
    b .print_char

hang:
    nop
    b .hang
