main:
    mov r0, #170
    st $2000, r0
    xor r0, r0
    ld r0, $2000
    st $f000, r0    ; write to GPO
