main:
    ; clear regs
    xor r0, r0
    xor r1, r1

    st $f10f, #12   ; config spi0
    st $f100, #199  ; write tx data
    st $f102, #1    ; transact

    ; loop until data sent
wait:
    add r1, #1      ; counter - not sure if inc works yet!
    ld r0, $f103
    eq r0, #1
tmp:                ; because of assembler fcn lookup bug
    bne .wait
    mov r0, #255    ; mark all done
