
mul_n: resb 1
mul_v: resb 1
math_mul:
    ; r0 = r0 * r1
    st [mul_v], r0
    st [mul_n], r1
    mov r1, #1  ; i=1
.loop:
    push r0
    ld r0, [mul_n]
    eq r0, r1
    pop r0
    bzf .done  ; i==mul_n ? mul_done
    push r1
    ld r1, [mul_v]
    add r0, r1
    pop r1
    add r1, #1  ; i++
    b .loop
.done:
    pop pcl
    pop pch

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
