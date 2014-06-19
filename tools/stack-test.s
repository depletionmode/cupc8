main:
    ; code switches r0, r1
    push #255
    pop r0
    push #10
    pop r1
    mov r0, #255
    mov r1, #15
    push r0
    push r1
    nop
    pop r0
    pop r1
