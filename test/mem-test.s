var1: resb 1
var2: resb 2

main:
    mov r0, #170
    st [var2+1], r0
    xor r0, r0
    ld r0, [var2+1]
    st $f000, r0    ; write to GPO
    mov r0, #129
    mov r1, #2
    st [var1]+r1, r0
    xor r0, r0
    mov r1, #1
    add r1, #1
    ld r0, [var1]+r1
    st $f000, r0    ; write to GPO
	halt
