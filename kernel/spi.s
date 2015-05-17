; spi driver

; write byte (r0) - device (r1)
spi_write:
	eq r1, #0
	bzf .do_0
	eq r1, #1
	bzf .do_1
	eq r1, #2
	bzf .do_2
	eq r1, #3
	bzf .do_3
	b .end
.do_0:
    st $f100, r0  ;fill tx buffer
    mov r0, #1
    st $f102, r0  ;transact
	b .wait_0
.do_1:
    st $f110, r0  ;fill tx buffer
    mov r0, #1
    st $f112, r0  ;transact
	b .wait_1
.do_2:
    st $f120, r0  ;fill tx buffer
    mov r0, #1
    st $f122, r0  ;transact
	b .wait_2
.do_3:
    st $f130, r0  ;fill tx buffer
    mov r0, #1
    st $f132, r0  ;transact
	b .wait_3
.wait_0:
    ld r0, $f103  ;read status
    eq r0, #1
    bzf .end
    b .wait_0
.wait_1:
    ld r0, $f113  ;read status
    eq r0, #1
    bzf .end
    b .wait_1
.wait_2:
    ld r0, $f123  ;read status
    eq r0, #1
    bzf .end
    b .wait_2
.wait_3:
    ld r0, $f133  ;read status
    eq r0, #1
    bzf .end
    b .wait_3
.end:
    pop pcl
    pop pch

; read byte (r0) - device (r1)
spi_read:
	eq r1, #0
	bzf .wait_0
	eq r1, #1
	bzf .wait_1
	eq r1, #2
	bzf .wait_2
	eq r1, #3
	bzf .wait_3
	b .end
.wait_0:
    mov r0, #255
    st $f100, r0  ;fill tx buffer
    mov r0, #1
    st $f102, r0  ;transact
    ld r0, $f103  ;read status
    eq r0, #0
    bzf .wait_0
    ld r0, $f101  ;read rx buffer
    b .end
.wait_1:
    mov r0, #255
    st $f110, r0  ;fill tx buffer
    mov r0, #1
    st $f112, r0  ;transact
    ld r0, $f113  ;read status
    eq r0, #0
    bzf .wait_1
    ld r0, $f111  ;read rx buffer
    b .end
.wait_2:
    mov r0, #255
    st $f120, r0  ;fill tx buffer
    mov r0, #1
    st $f122, r0  ;transact
    ld r0, $f123  ;read status
    eq r0, #0
    bzf .wait_2
    ld r0, $f121  ;read rx buffer
    b .end
.wait_3:
    mov r0, #255
    st $f130, r0  ;fill tx buffer
    mov r0, #1
    st $f132, r0  ;transact
    ld r0, $f133  ;read status
    eq r0, #0
    bzf .wait_3
    ld r0, $f131  ;read rx buffer
    b .end
.end:
    pop pcl
    pop pch
