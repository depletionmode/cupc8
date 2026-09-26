; KRN-024: API_MEM_CMP and API_MEM_CPY. The test puts the cases in memory
; before it runs: $7d00 = n, case i at $7d10 + 8i = op (0 compare, 1 copy),
; then API_ARGS[0..5] (dst, src, len16). For each case the program calls the
; entry and puts r0, r1 and API_ARGS[0..5] after the call at $7e00 + 8i;
; $7cff = $a5 at the end.

i: resb 1
o: resb 1
k: resb 1
s0: resb 1
s1: resb 1

main:
	xor r0, r0
	st [i], r0
.case:
	ld r0, [i]
	ld r1, $7d00
	eq r0, r1
	bzf .end
	shl r0, #3
	st [o], r0
	xor r0, r0
	st [k], r0
.args:
	ld r1, [o]				; API_ARGS[k] = case[1 + k]
	ld r0, [k]
	add r1, r0
	ld r0, $7d11+r1
	ld r1, [k]
	st $6f00+r1, r0
	add r1, #1
	st [k], r1
	eq r1, #6
	bzf .call
	b .args
.call:
	ld r1, [o]
	ld r0, $7d10+r1
	eq r0, #0
	bzf .cmp
	push pch
	push pcl
	b API_MEM_CPY
	b .store
.cmp:
	push pch
	push pcl
	b API_MEM_CMP
.store:
	st [s0], r0
	st [s1], r1
	ld r1, [o]
	ld r0, [s0]
	st $7e00+r1, r0
	ld r0, [s1]
	st $7e01+r1, r0
	xor r0, r0
	st [k], r0
.out:
	ld r1, [k]				; result[2 + k] = API_ARGS[k]
	ld r0, $6f00+r1
	st [s0], r0
	ld r0, [o]
	add r1, r0
	ld r0, [s0]
	st $7e02+r1, r0
	ld r1, [k]
	add r1, #1
	st [k], r1
	eq r1, #6
	bzf .next
	b .out
.next:
	ld r0, [i]
	add r0, #1
	st [i], r0
	b .case
.end:
	mov r0, #0xa5
	st $7cff, r0
	pop pcl
	pop pch
