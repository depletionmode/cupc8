main:
    ; write pattern to gpo
    mov r0, #255
    mov r1, #0
    st $f000, r0
    st $f000, r1
    mov r0, #170
    st $f000, r0
