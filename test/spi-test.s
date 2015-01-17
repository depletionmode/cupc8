main:
    ; clear regs
    xor r0, r0
    xor r1, r1

    mov r0, #12
    st $f10f, r0   ; config spi0
    mov r0, #199
    st $f100, r0  ; write tx data
    mov r1, #1
    st $f102, r1    ; transact

    ; loop until data sent
wait:
    add r1, #1      ; counter - not sure if inc works yet!
    ld r0, $f103
    eq r0, #1
tmp:                ; because of assembler fcn lookup bug
    bne .wait
    mov r0, #255    ; mark all done
