; KRN-021: API_GFX_TEXT8 into a nearly full FIFO. GFX mode, then 1150
; API_GFX_PIXEL frames (7 bytes each in the card's FIFO: 8050 of its 8192)
; while the test holds the card's execution, then a 255-character TEXT8 at
; (0, 100), fg 15 on bg 1: its 262-byte frame does not fit until the card runs
; again. $be00 = 1 once the TEXT8 call has returned, $be01 = 2 at the end.

tbuf: resb 256
n: resb 2

main:
	mov r0, #1
	push pch
	push pcl
	b API_GFX_MODE
	xor r0, r0
	st $be00, r0
	st $be01, r0
	st [n], r0
	st [n+1], r0
.pixel:
	ld r0, [n]				; PIXEL (n & 255, 200), colour 7
	st $6f00, r0
	xor r0, r0
	st $6f01, r0
	mov r0, #200
	st $6f02, r0
	mov r0, #7
	st $6f03, r0
	push pch
	push pcl
	b API_GFX_PIXEL
	ld r0, [n]
	add r0, #1
	st [n], r0
	eq r0, #0
	bzf .carry
	b .count
.carry:
	ld r0, [n+1]
	add r0, #1
	st [n+1], r0
.count:
	ld r0, [n+1]				; 1150 = $047e
	eq r0, #4
	bzf .hi4
	b .pixel
.hi4:
	ld r0, [n]
	eq r0, #0x7e
	bzf .text
	b .pixel
.text:
	xor r1, r1				; 255 characters, A-Z over and over, then a 0
.fill:
	mov r0, r1
.mod:
	lt r0, #26
	bzf .ch
	sub r0, #26
	b .mod
.ch:
	add r0, #65
	st [tbuf]+r1, r0
	add r1, #1
	eq r1, #255
	bzf .ended
	b .fill
.ended:
	xor r0, r0
	st [tbuf]+r1, r0
	xor r0, r0
	st $6f00, r0
	st $6f01, r0
	mov r0, #100
	st $6f02, r0
	mov r0, #15
	st $6f03, r0
	mov r0, #1
	st $6f04, r0
	mov r0, #<[tbuf]
	st $6f06, r0
	mov r0, #>[tbuf]
	st $6f07, r0
	push pch
	push pcl
	b API_GFX_TEXT8
	mov r0, #1
	st $be00, r0
	mov r0, #2
	st $be01, r0
	pop pcl
	pop pch
