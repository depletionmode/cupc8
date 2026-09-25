; E2E-010/012, KRN-013: a program that sets the e-paper card's refresh
; policy through the kernel API (API_EINK_AUTO: on, idle10 5, full_after 2,
; cap10 50, full_kind 3 greyscale, sleep_s 3), reads it back (API_EINK_GET)
; and asks the panel's state (API_EINK_STATUS). It leaves what they gave at
; $7e00-$7e0b and prints it:
;   AUTO rr
;   GET rr on idle10 full_after cap10 full_kind sleep_s
;   ST rr busy dirty partials
; On HDMI every one of them is FF.

s_auto db "AUTO "
s_get db "GET "
s_st db "ST "
pi: resb 1
pe: resb 1

main:
	mov r0, #1
	st $6f00, r0
	mov r0, #5
	st $6f01, r0
	mov r0, #2
	st $6f02, r0
	mov r0, #50
	st $6f03, r0
	mov r0, #3
	st $6f04, r0
	mov r0, #3
	st $6f05, r0
	push pch
	push pcl
	b API_EINK_AUTO
	st $7e00, r0
	push pch
	push pcl
	b API_EINK_GET
	st $7e01, r0
	xor r1, r1
.get:
	ld r0, $6f00+r1
	st $7e02+r1, r0
	add r1, #1
	eq r1, #6
	bzf .status
	b .get
.status:
	push pch
	push pcl
	b API_EINK_STATUS
	st $7e08, r0
	ld r0, $6f00
	st $7e09, r0
	ld r0, $6f01
	st $7e0a, r0
	ld r0, $6f02
	st $7e0b, r0

	mov r0, #10
	push pch
	push pcl
	b API_PUTC
	mov r0, #<[s_auto]
	mov r1, #>[s_auto]
	push pch
	push pcl
	b puts
	ld r0, $7e00
	push pch
	push pcl
	b hex
	mov r0, #10
	push pch
	push pcl
	b API_PUTC
	mov r0, #<[s_get]
	mov r1, #>[s_get]
	push pch
	push pcl
	b puts
	mov r0, #1
	mov r1, #8
	push pch
	push pcl
	b bytes
	mov r0, #10
	push pch
	push pcl
	b API_PUTC
	mov r0, #<[s_st]
	mov r1, #>[s_st]
	push pch
	push pcl
	b puts
	mov r0, #8
	mov r1, #12
	push pch
	push pcl
	b bytes
	pop pcl
	pop pch

; print the string at r0 (low), r1 (high)
puts:
	st $6f00, r0
	st $6f01, r1
	b API_PUTS

; print the bytes $7e00+r0 up to $7e00+r1-1 in hex, a space between
bytes:
	st [pi], r0
	st [pe], r1
.loop:
	ld r1, [pi]
	ld r0, $7e00+r1
	push pch
	push pcl
	b hex
	ld r0, [pi]
	add r0, #1
	st [pi], r0
	ld r1, [pe]
	eq r0, r1
	bzf .done
	mov r0, #32
	push pch
	push pcl
	b API_PUTC
	b .loop
.done:
	pop pcl
	pop pch

; print r0 in hex
hex:
	push r0
	shr r0, #4
	push pch
	push pcl
	b digit
	pop r0
	and r0, #15
digit:
	lt r0, #10
	bzf .num
	add r0, #55
	b API_PUTC
.num:
	add r0, #48
	b API_PUTC
