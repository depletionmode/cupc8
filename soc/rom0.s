; rom0 code
; 128 byte constraint
; no use of data/bss regions!
; responsible for loading the rom off the flash into ram
; situated at $0000 on the flash device
; rom0 base address - $e000

main:
	mov r0, #0		; gpo - indicate bootloader start
	st $f000, r0

	mov r0, #249	; div=25 (1MHz), mode=0,0, cont=1
	st $f10f, r0	; configure spi device

	mov r0, #3
	st $f100, r0	; write flash READ cmd
	st $f102, r1	; start transaction
.wait0:
	ld r1, $f103	; read status
	eq r1, #0
	bzf .wait0

	mov r0, #0
	st $f100, r0
.wait1:
	ld r1, $f103	; read status
	eq r1, #0
	bzf .wait1
	mov r0, #0
	st $f100, r0	; write flash address $0000
.wait2:
	ld r1, $f103	; read status
	eq r1, #0
	bzf .wait2
;
.ignore_byte:
	mov r0, #255
	st $f100, r0	; write 0xff
.wait3:
	ld r0, $f103	; read status
	eq r0, #0
	bzf .wait3

	mov r1, #255
.loop0:
	mov r0, #255
	st $f100, r0	; write 0xff
.wait4:
	ld r0, $f103	; read status
	eq r0, #0
	bzf .wait4
	ld r0, $f101	; read byte
	;st $1000+r1, r0 ; todo - implement hw support for this!! 
	sub r1, #1
	st $f000, r1
	gt r1, #0	; todo - work out why EQ (and probably other logical comparisons) is screwey with r1 I suspect writeback issues with r1 as first operand...
	bzf .loop0

.read_done:
	mov r0, #248
	st $f10f, r0	; disable cont mode

	;mov r0, #255	
	st $f000, r0	; gpo - indicate bootloader end

.test_loop:
	b .test_loop

	b $1000			; jump to kernel start vector
