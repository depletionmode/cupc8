; spi driver

; write byte (r0) - device (r1)
spi_write:
	eq r1, #0
	bzf .spi_write_0
	eq r1, #1
	bzf .spi_write_1
	eq r1, #2
	bzf .spi_write_2
	eq r1, #3
	bzf .spi_write_3
	b .spi_write_end
spi_write_0:
    st $f100, r0  ;fill tx buffer
    mov r0, #1
    st $f102, r0  ;transact
	b .spi_write_wait_0
spi_write_1:
    st $f110, r0  ;fill tx buffer
    mov r0, #1
    st $f112, r0  ;transact
	b .spi_write_wait_1
spi_write_2:
    st $f120, r0  ;fill tx buffer
    mov r0, #1
    st $f122, r0  ;transact
	b .spi_write_wait_2
spi_write_3:
    st $f130, r0  ;fill tx buffer
    mov r0, #1
    st $f132, r0  ;transact
	b .spi_write_wait_3
spi_write_wait_0:
    ld r0, $f103  ;read status
    eq r0, #1
    bzf .spi_write_end
    b .spi_write_wait_0
spi_write_wait_1:
    ld r0, $f113  ;read status
    eq r0, #1
    bzf .spi_write_end
    b .spi_write_wait_1
spi_write_wait_2:
    ld r0, $f123  ;read status
    eq r0, #1
    bzf .spi_write_end
    b .spi_write_wait_2
spi_write_wait_3:
    ld r0, $f133  ;read status
    eq r0, #1
    bzf .spi_write_end
    b .spi_write_wait_3
spi_write_end:
    pop pcl
    pop pch

; read byte (r0) - device (r1)
spi_read:
	eq r1, #0
	bzf .spi_read_wait_0
	eq r1, #1
	bzf .spi_read_wait_1
	eq r1, #2
	bzf .spi_read_wait_2
	eq r1, #3
	bzf .spi_read_wait_3
	b .spi_read_end
spi_read_wait_0:
    mov r0, #1
    st $f102, r0  ;transact
    ld r0, $f103  ;read status
    eq r0, #0
    bzf .spi_read_wait_0
    ld r0, $f101  ;read rx buffer
    b .spi_read_end
spi_read_wait_1:
    mov r0, #1
    st $f112, r0  ;transact
    ld r0, $f113  ;read status
    eq r0, #0
    bzf .spi_read_wait_1
    ld r0, $f111  ;read rx buffer
    b .spi_read_end
spi_read_wait_2:
    mov r0, #1
    st $f122, r0  ;transact
    ld r0, $f123  ;read status
    eq r0, #0
    bzf .spi_read_wait_2
    ld r0, $f121  ;read rx buffer
    b .spi_read_end
spi_read_wait_3:
    mov r0, #1
    st $f132, r0  ;transact
    ld r0, $f133  ;read status
    eq r0, #0
    bzf .spi_read_wait_3
    ld r0, $f131  ;read rx buffer
    b .spi_read_end
spi_read_end:
    pop pcl
    pop pch
