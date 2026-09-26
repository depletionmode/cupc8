; KRN-031: a program that uses $c000 and up, as one over 20 KB would: it
; writes over the start of the BASIC program ($c000-$c003, "BA" and the
; end), prints BIG OK and returns. BASIC, loaded again after it, finds no
; program there and starts empty.

s_ok db "BIG OK"

main:
	mov r0, #0x55
	st $c000, r0
	st $c001, r0
	st $c002, r0
	st $c003, r0
	mov r0, #<[s_ok]
	st $6f00, r0
	mov r0, #>[s_ok]
	st $6f01, r0
	push pch
	push pcl
	b API_PUTS
	pop pcl
	pop pch
