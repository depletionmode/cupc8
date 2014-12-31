func1:
    ; return to caller
    pop pcl
    pop pch

main:
    ; call func1
    push pch
    push pcl
    b .func1
    mov r0, #255
