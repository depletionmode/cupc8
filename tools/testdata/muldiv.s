; Software mul/div using the kernel algorithms.
mul_n: resb 1
div_q: resb 1

math_mul:
	st [mul_n], r0
	xor r0, r0
.loop:
	push r0
	ld r0, [mul_n]
	eq r0, #0
	bzf .done
	sub r0, #1
	st [mul_n], r0
	pop r0
	add r0, r1
	b .loop
.done:
	pop r0
	pop pcl
	pop pch

math_div:
	push r0
	xor r0, r0
	st [div_q], r0
	pop r0
.loop:
	lt r0, r1
	bzf .done
	push r0
	ld r0, [div_q]
	add r0, #1
	st [div_q], r0
	pop r0
	sub r0, r1
	b .loop
.done:
	mov r1, r0
	ld r0, [div_q]
	pop pcl
	pop pch

main:
	mov r0, #3
	mov r1, #7
	push pch
	push pcl
	b math_mul
	st $2000, r0		; 21

	mov r0, #20
	mov r1, #6
	push pch
	push pcl
	b math_div
	st $2001, r0		; 3
	st $2002, r1		; 2

	mov r0, #0
	mov r1, #9
	push pch
	push pcl
	b math_mul
	st $2003, r0		; 0
	halt
