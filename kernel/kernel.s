; kernel entry point
main:
    push pch
    push pcl
    b .print_msg
;    mov r0, #67    ; 'C'
;    push pch
;    push pcl
;    b .print_char

    mov r0, #255
    st $f000, r0
hang:
    nop
    b .hang
