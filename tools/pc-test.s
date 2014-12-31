func1:
    ; return to caller
    mov r1, #170
    st $f000, r1
    pop pcl
    pop pch

main:
    ; call func1
    push pch
    push pcl
    b .func1
    mov r0, #255
    st $f000, r0
