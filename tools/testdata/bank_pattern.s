; KRN-008: a distinct pattern in all 32 RAM banks, written and then read
; back through the window at $8000-$bfff, with the kernel's api_bank_set.
; The test prepends "%define BANK_SET $xxxx" (the routine's address in
; kernel.map) and assembles this for $7000. Byte (bank, page, lo) of the
; window holds lo + 3 * page + 7 * bank. Banks 0, 1 and 3 are the normal
; memory, where the kernel lives: bank 0 gets only page $0e (the unused top
; of the stack page, $0e00), bank 1 only pages $38-$3f ($7800-$7fff, above
; this program), bank 3 all of it ($c000-$ffff).
; Result: errs (the first bss byte) counts mismatches (stops at 255).

errs: resb 1
phase: resb 1
bank: resb 1
page: resb 1
pend: resb 1
base: resb 1
want: resb 1
ptr: resb 2

main:
	mov r0, #0
	st [errs], r0
	st [phase], r0
.phase:
	mov r0, #0
	st [bank], r0
.bank:
	ld r0, [bank]
	push pch
	push pcl
	b BANK_SET
	ld r0, [bank]
	eq r0, #0
	bzf .first
	eq r0, #1
	bzf .second
	mov r0, #0
	st [page], r0
	mov r0, #64
	st [pend], r0
	b .pages
.first:
	mov r0, #14
	st [page], r0
	mov r0, #15
	st [pend], r0
	b .pages
.second:
	mov r0, #56
	st [page], r0
	mov r0, #64
	st [pend], r0
.pages:
	ld r0, [page]
	or r0, #128
	st [ptr+1], r0
	mov r0, #0
	st [ptr], r0
	ld r0, [page]
	mov r1, r0
	add r0, r1
	add r0, r1
	st [base], r0
	ld r0, [bank]
	shl r0, #3
	ld r1, [bank]
	sub r0, r1
	ld r1, [base]
	add r0, r1
	st [base], r0
	xor r1, r1
.byte:
	ld r0, [base]
	add r0, r1
	push r0
	ld r0, [phase]
	eq r0, #0
	pop r0
	bzf .write
	st [want], r0
	ldd r0, [ptr]+r1
	push r1
	ld r1, [want]
	eq r0, r1
	pop r1
	bzf .next
	ld r0, [errs]
	eq r0, #255
	bzf .next
	add r0, #1
	st [errs], r0
	b .next
.write:
	std [ptr]+r1, r0
.next:
	add r1, #1
	eq r1, #0
	bzf .page_end
	b .byte
.page_end:
	ld r0, [page]
	add r0, #1
	st [page], r0
	ld r1, [pend]
	eq r0, r1
	bzf .bank_end
	b .pages
.bank_end:
	ld r0, [bank]
	add r0, #1
	st [bank], r0
	eq r0, #32
	bzf .phase_end
	b .bank
.phase_end:
	ld r0, [phase]
	add r0, #1
	st [phase], r0
	eq r0, #2
	bzf .end
	b .phase
.end:
	mov r0, #2
	push pch
	push pcl
	b BANK_SET
	halt
