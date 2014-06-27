main:
    ; write pattern to gpo
    mov r0, #170
    st $2000, r0
    mov r0, #255
    ld r0, $2000
    st $f000, r0
