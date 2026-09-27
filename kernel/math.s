; ------------------------------------------------------------ 16-bit numbers
; Two bytes, low first, two's complement. The routines work on n_a and n_b:
; n_a op n_b into n_a. They change r0, r1 and n_t. The kernel's own (API_GFX2_BLIT1,
; BLIT2); BASIC, a program, has its own copy of these in basic/n16.s.

n_a: resb 2
n_b: resb 2
n_t: resb 2					; the remainder of a division
n_i: resb 1

; n_a = n_a << 1
n16_shl1:
	ld r0, [n_a]
	shr r0, #7
	ld r1, [n_a+1]
	shl r1, #1
	or r1, r0
	st [n_a+1], r1
	ld r0, [n_a]
	shl r0, #1
	st [n_a], r0
	pop pcl
	pop pch

; n_a = n_a * n_b (the low 16 bits: right for signed numbers too); n_b is
; used up. Shift and add, until no bit of n_b is left.
n16_mul:
	xor r0, r0
	st [n_t], r0
	st [n_t+1], r0
.loop:
	ld r0, [n_b]
	ld r1, [n_b+1]
	or r0, r1
	eq r0, #0
	bzf .done
	ld r0, [n_b]
	and r0, #1
	eq r0, #0
	bzf .shift
	ld r0, [n_t]			; n_t += n_a
	ld r1, [n_a]
	add r0, r1
	st [n_t], r0
	lt r0, r1
	ld r0, [n_t+1]
	ld r1, [n_a+1]
	add r0, r1
	bzf .carry
	b .high
.carry:
	add r0, #1
.high:
	st [n_t+1], r0
.shift:
	push pch
	push pcl
	b n16_shl1
	ld r0, [n_b+1]			; n_b >>= 1
	and r0, #1
	shl r0, #7
	ld r1, [n_b]
	shr r1, #1
	or r1, r0
	st [n_b], r1
	ld r0, [n_b+1]
	shr r0, #1
	st [n_b+1], r0
	b .loop
.done:
	ld r0, [n_t]
	st [n_a], r0
	ld r0, [n_t+1]
	st [n_a+1], r0
	pop pcl
	pop pch

; unsigned: n_a = n_a / n_b, n_t = the remainder. n_b at most $8000 (the
; remainder then stays within 16 bits); n_b = 0 gives n_a = $ffff.
n16_udiv:
	xor r0, r0
	st [n_t], r0
	st [n_t+1], r0
	mov r0, #16
	st [n_i], r0
.bit:
	ld r0, [n_t]			; n_t -n_a <<= 1
	shr r0, #7
	ld r1, [n_t+1]
	shl r1, #1
	or r1, r0
	st [n_t+1], r1
	ld r0, [n_a+1]
	shr r0, #7
	ld r1, [n_t]
	shl r1, #1
	or r1, r0
	st [n_t], r1
	push pch
	push pcl
	b n16_shl1
	ld r0, [n_t+1]			; n_t >= n_b - subtract it, and a 1 into the quotient
	ld r1, [n_b+1]
	lt r0, r1
	bzf .next
	gt r0, r1
	bzf .sub
	ld r0, [n_t]
	ld r1, [n_b]
	lt r0, r1
	bzf .next
.sub:
	ld r0, [n_t]
	ld r1, [n_b]
	lt r0, r1
	sub r0, r1
	st [n_t], r0
	ld r0, [n_t+1]
	ld r1, [n_b+1]
	sub r0, r1
	bzf .borrow
	b .high
.borrow:
	sub r0, #1
.high:
	st [n_t+1], r0
	ld r0, [n_a]
	or r0, #1
	st [n_a], r0
.next:
	ld r0, [n_i]
	sub r0, #1
	st [n_i], r0
	eq r0, #0
	bzf .done
	b .bit
.done:
	pop pcl
	pop pch
