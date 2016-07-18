; rom0 code
; 128 byte constraint
; no use of data/bss regions!
; responsible for loading the rom off the flash into ram
; situated at $0000 on the flash device
; rom0 base address - $e000

main:
;	mov r0, #0
;	st $f000, r0
;	b .test
;.res:
;	mov r0, #1
;	st $f000, r0
;	st $f000, r1
;	b .halt
;.test:
;	mov r1, #200
;	st $f000, r1
;	lt r1, #201
;	bzf .res
;.loop:
;	b .loop
;.halt:
;	mov r0, #255
;	st $f000, r0
;	b .halt

;	mov r0, #0		; gpo - indicate bootloader start
;	st $f000, r0

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
	st $f100, r0	; write flash address $0000
.wait1:
	ld r1, $f103	; read status
	eq r1, #0
	bzf .wait1
.wait2:
	ld r1, $f103	; read status
	eq r1, #0
	bzf .wait2

; wait until data is ready
.ignore_byte:
	mov r0, #255
	st $f100, r0	; write dummy
.wait3:
	ld r0, $f103	; read status
	eq r0, #0
	bzf .wait3
	ld r0, $f101	; read byte
	eq r0, #0
	bzf .ignore_byte
	eq r0, #255
	bzf .ignore_byte
	st $1000, r0	; store 1st byte

.load_rom1:
	mov r1, #1
.loop0:
	mov r0, #0
	st $f100, r1	; write dummy
.wait4:
	ld r0, $f103	; read status
	eq r0, #0
	bzf .wait4
	ld r0, $f101	; read byte
	push r1
	push r0
	mov r0, r1
	pop r1
	st $1000+r0, r1 ; todo - implement hw support for this!!
	pop r1
	add r1, #1
	st $f000, r1
	lt r1, #55	; todo - work out why EQ (and probably other logical comparisons) is screwey with r1 I suspect writeback issues with r1 as first operand...
	bzf .loop0

.read_done:
	mov r0, #248
	st $f10f, r0	; disable cont mode

	st $f000, r0	; gpo - indicate bootloader end

;st $0000, r0
;mov r0, #8
;st $0008, r0
;mov r1, #1
;st $0000+r0, r1 ; todo - implement hw support for this!! 
;st $f000, r1
;mov r0, #9
;st $0009, r0
;mov r1, #128
;st $0000+r0, r1 ; todo - implement hw support for this!! 
;st $f000, r1
;xor r0, r0
;ld r0, $0000
;st $f000, r0
;xor r0, r0
;mov r1, #9
;ld r0, $0000+r1
;st $f000, r0
;xor r0, r0
;mov r1, #8
;xor r1, r1
;; WTF is wrong with this????
;ld r1, $0000+r1
;st $f000, r1

;xor r1, r1
;st $0000, r1
;mov r0, #12
;st $0000, r0
;xor r0, r0
;xor r1, r1
;ld r1, $0000
;st $f000, r1


;	mov r0, #255	
;	xor r0, r0
	ld r0, $1002
	st $f000, r0	; gpo - indicate bootloader end
.test_loop:
	b .test_loop

;	b $1000			; jump to kernel start vector
