; spi driver

; write byte (r0)
spi_write:
    st $f100, r0  ;fill tx buffer
    mov r0, #1
    st $f102, r0  ;transact
wait_spi_write:
    ld r0, $f103
    eq r0, #1
    bzf .end_spi_write
    b .wait_spi_write
end_spi_write:
    mov r0, #0

