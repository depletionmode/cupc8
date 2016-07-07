; rom0 code
; 128 byte constraint
; responsible for loading the rom off the flash into ram
; situated at $0000 on the flash device
; rom0 base address - $e000

main:
	mov r0, #255	; gpo - indicate bootloader start
	st $f000, r0

	mov r0, #241	; div=30, mode=0,0, cont=0
	st $f10f, r0	; configure spi device

	mov r0, #3
	st $f100, r0	; write flash READ cmd
	st $f102, r1	; start transaction
.wait0:
	ld r1, $f103	; read status
	eq r1, #0
	bzf .wait0

	xor r0, r0
	st $f100, r0
.wait1:
	ld r1, $f103	; read status
	eq r1, #0
	bzf .wait1
	st $f100, r0	; write flash address $0000
.wait2:
	ld r1, $f103	; read status
	eq r1, #0
	bzf .wait2

	mov r1, #10
.loop0:
	ld r0, $f101	; read byte
	st $1000+r1, r0
.wait3:
	ld r0, $f103	; read status
	eq r0, #0
	bzf .wait3
	sub r1
	eq r1, #0
	bzf .read_done
	b .loop0

.read_done:
	mov r0, #206
	st $f10f, r0	; disable cont mode

	mov r0, #129	; gpo - indicate bootloader end
	st $f000, r0

.test_loop:
	b .test_loop

	b $0100			; jump to kernel start vector
