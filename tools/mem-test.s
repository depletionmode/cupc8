var1: resb 2
var2: resb 2

main:
    mov r0, #170
    st [var2+1], r0
    xor r0, r0
    ld r0, [var2+1]
    st $f000, r0    ; write to GPO
