
div_q: resb 1
math_div:
	; r0 = r0 / r1, r1 = remainder; dividing by 0 gives 0 remainder r0
	eq r1, #0
	bzf .by_zero
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
.by_zero:
	mov r1, r0
	xor r0, r0
	pop pcl
	pop pch

; ------------------------------------------------------------ 16-bit numbers
; BASIC's numbers (and the kernel's where 8 bits are not enough): two bytes,
; low first, two's complement. The routines work on n_a and n_b: n_a op n_b
; into n_a. They change r0, r1 and n_t.

n_a: resb 2
n_b: resb 2
n_t: resb 2					; the remainder of a division
n_p: resb 2					; n16_negp's pointer
n_i: resb 1
n_s: resb 2					; n16_div's signs: the remainder's, the quotient's

; n_a = n_a + n_b
n16_add:
	ld r0, [n_a]
	ld r1, [n_b]
	add r0, r1
	st [n_a], r0
	lt r0, r1				; the low byte carried - the sum is below what was added
	ld r0, [n_a+1]
	ld r1, [n_b+1]
	add r0, r1
	bzf .carry
	b .high
.carry:
	add r0, #1
.high:
	st [n_a+1], r0
	pop pcl
	pop pch

; n_a = n_a - n_b
n16_sub:
	ld r0, [n_a]
	ld r1, [n_b]
	lt r0, r1				; a borrow from the high byte
	sub r0, r1
	st [n_a], r0
	ld r0, [n_a+1]
	ld r1, [n_b+1]
	sub r0, r1
	bzf .borrow
	b .high
.borrow:
	sub r0, #1
.high:
	st [n_a+1], r0
	pop pcl
	pop pch

; n_a = n_a & n_b
n16_and:
	ld r0, [n_a]
	ld r1, [n_b]
	and r0, r1
	st [n_a], r0
	ld r0, [n_a+1]
	ld r1, [n_b+1]
	and r0, r1
	st [n_a+1], r0
	pop pcl
	pop pch

; n_a = n_a | n_b
n16_or:
	ld r0, [n_a]
	ld r1, [n_b]
	or r0, r1
	st [n_a], r0
	ld r0, [n_a+1]
	ld r1, [n_b+1]
	or r0, r1
	st [n_a+1], r0
	pop pcl
	pop pch

; n_a = -n_a; n16_negb: n_b = -n_b; n16_negp: the number at the pointer n_p
n16_neg:
	mov r0, #<[n_a]
	mov r1, #>[n_a]
	b n16_negr
n16_negb:
	mov r0, #<[n_b]
	mov r1, #>[n_b]
n16_negr:
	st [n_p], r0
	st [n_p+1], r1
n16_negp:
	mov r1, #1
	ldd r0, [n_p]+r1
	xor r0, #0xff
	std [n_p]+r1, r0
	xor r1, r1
	ldd r0, [n_p]+r1
	xor r0, #0xff
	add r0, #1
	std [n_p]+r1, r0
	eq r0, #0				; ~low + 1 carried into the high byte
	bzf .carry
	pop pcl
	pop pch
.carry:
	mov r1, #1
	ldd r0, [n_p]+r1
	add r0, #1
	std [n_p]+r1, r0
	pop pcl
	pop pch

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

; compare n_a with n_b, signed: r0 = 0 equal, 1 n_a less, 2 n_a greater
n16_cmp:
	ld r0, [n_a+1]
	xor r0, #0x80			; the sign flipped - then unsigned order is signed order
	ld r1, [n_b+1]
	xor r1, #0x80
	lt r0, r1
	bzf .less
	gt r0, r1
	bzf .greater
	ld r0, [n_a]
	ld r1, [n_b]
	lt r0, r1
	bzf .less
	gt r0, r1
	bzf .greater
	xor r0, r0
	pop pcl
	pop pch
.less:
	mov r0, #1
	pop pcl
	pop pch
.greater:
	mov r0, #2
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

; signed, as C: n_a = n_a / n_b truncated toward 0, n_t = the remainder
; (the sign of n_a). n_b = 0 gives n_a = 0 and n_t = n_a (BASIC: x / 0 is 0).
n16_div:
	ld r0, [n_b]
	ld r1, [n_b+1]
	or r0, r1
	eq r0, #0
	bzf .by_zero
	ld r0, [n_a+1]
	st [n_s], r0
	ld r1, [n_b+1]
	xor r0, r1
	st [n_s+1], r0
	ld r0, [n_a+1]
	lt r0, #0x80
	bzf .a_pos
	push pch
	push pcl
	b n16_neg
.a_pos:
	ld r0, [n_b+1]
	lt r0, #0x80
	bzf .b_pos
	push pch
	push pcl
	b n16_negb
.b_pos:
	push pch
	push pcl
	b n16_udiv
	ld r0, [n_s+1]
	lt r0, #0x80
	bzf .q_pos
	push pch
	push pcl
	b n16_neg
.q_pos:
	ld r0, [n_s]
	lt r0, #0x80
	bzf .done
	mov r0, #<[n_t]
	mov r1, #>[n_t]
	st [n_p], r0
	st [n_p+1], r1
	b n16_negp				; its return is ours
.done:
	pop pcl
	pop pch
.by_zero:
	ld r0, [n_a]
	st [n_t], r0
	ld r0, [n_a+1]
	st [n_t+1], r0
	xor r0, r0
	st [n_a], r0
	st [n_a+1], r0
	pop pcl
	pop pch

; print n_a as a signed decimal number (n_a is used up)
n16_print:
	ld r0, [n_a+1]
	lt r0, #0x80
	bzf .digits
	mov r0, #45				; -
	push pch
	push pcl
	b print_ascii_char
	push pch
	push pcl
	b n16_neg				; -32768 stays $8000 - 32768 unsigned
.digits:
	push #0xff				; the digits go on the stack, last first, above this
.digit:
	mov r0, #10
	st [n_b], r0
	xor r0, r0
	st [n_b+1], r0
	push pch
	push pcl
	b n16_udiv
	ld r0, [n_t]
	add r0, #48
	push r0
	ld r0, [n_a]
	ld r1, [n_a+1]
	or r0, r1
	eq r0, #0
	bzf .print
	b .digit
.print:
	pop r0
	eq r0, #0xff
	bzf .done
	push pch
	push pcl
	b print_ascii_char
	b .print
.done:
	pop pcl
	pop pch
