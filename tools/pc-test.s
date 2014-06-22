func1:
    ; return to caller
    pop pch
    pop pcl

main:
    ; call func1
    push pch
    push pcl
    b .func1
    mov r0, #255
