; spi driver

%define _DEV0_ 0
%define _DEV1_ 2
%define _DEV2_ 3
%define _DEV3_ 4

; write byte (r0) - device 0
spi_write_0:
    st $f1_DEV0_0, r0  ;fill tx buffer
    mov r0, #1
    st $f1_DEV0_2, r0  ;transact
wait_spi_write_0:
    ld r0, $f1_DEV0_3  ;read status
    eq r0, #1
    bzf .end_spi_write
    b .wait_spi_write
end_spi_write_0:
    mov r0, #0

; read byte (r0) - device 0
spi_read_0:
    mov r0, #1
    st $f1_DEV0_2, r0  ;transact
wait_spi_read_0:
    ld r0, $f1_DEV0_3  ;read status
    eq r0, #1
    bzf .end_spi_read
    b .wait_spi_read
end_spi_read_0:
    ld r0, $f1_DEV0_1  ;read rx buffer
