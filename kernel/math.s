
div_q: resb 1
math_div:
	; r0 = r0 / r1
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
	mov r1, r0	; remainder
	ld r0, [div_q]
	pop pcl
	pop pch

mul_n: resb 1
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
	
