; banked RAM (doc/proposals/extended-ram.md, doc/hardware/memory-map.md)
;
; The main board's 512 KB SRAM is 32 banks of 16 KB. RAM_BANK ($f205)
; picks the bank the CPU sees in the window at $8000-$bfff; everything else
; is the normal 64 KB (banks 0, 1 and 3). Reset value 2 is the identity map.
;
; The kernel keeps nothing in the window (its code, data, bss and the API
; block are all below $7000), so interrupts need not save RAM_BANK. A
; program's own interrupt handler that uses the window must save and
; restore it. api_bank_far_copy changes RAM_BANK while it runs and puts the
; caller's bank back before it returns; it is not reentrant.
;
; Physical addresses below are bank * $4000 + offset ($00000-$7ffff).

bank_buf: resb 256
bank_saved: resb 1
bank_s: resb 3
bank_d: resb 3
bank_n: resb 2
bank_k: resb 1
bank_ptr: resb 2
bank_t: resb 3
bank_a: resb 3
bank_c: resb 1

; api_bank_set: select the bank the window at $8000-$bfff shows.
;   in:  r0 = bank, 0-31
;   out: r0 = 0 ok; 1 if the bank is above 31 (RAM_BANK unchanged)
api_bank_set:
	gt r0, #31
	bzf .bad
	st $f205, r0
	mov r0, #0
	pop pcl
	pop pch
.bad:
	mov r0, #1
	pop pcl
	pop pch

; api_bank_get: the bank the window shows now.
;   out: r0 = bank, 0-31
api_bank_get:
	ld r0, $f205
	pop pcl
	pop pch

; api_bank_count: how many banks there are.
;   out: r0 = 32 (512 KB)
api_bank_count:
	mov r0, #32
	pop pcl
	pop pch

; api_bank_far_copy: copy bytes between any two (bank, offset) places, as
; memmove does (overlapping ranges are fine), through a 256-byte buffer
; below the window. Ranges run on across bank boundaries (the physical
; address is bank * $4000 + offset).
;   in:  API block $6f00 source bank (0-31), $6f01-$6f02 source offset
;        ($0000-$3fff, little-endian), $6f03 destination bank, $6f04-$6f05
;        destination offset, $6f06-$6f07 length (0-$ffff)
;   out: r0 = 0 ok; 1 if a bank is above 31, an offset above $3fff, or
;        either range goes past the end of the SRAM ($7ffff); nothing is
;        copied then. r1 is not preserved. RAM_BANK is the caller's again.
api_bank_far_copy:
	ld r0, $f205
	st [bank_saved], r0

	; source (bank, offset) to a physical address in bank_s
	ld r0, $6f00
	gt r0, #31
	bzf .bad
	ld r0, $6f02
	gt r0, #63
	bzf .bad
	ld r0, $6f01
	st [bank_s], r0
	ld r0, $6f00
	and r0, #3
	shl r0, #6
	ld r1, $6f02
	or r0, r1
	st [bank_s+1], r0
	ld r0, $6f00
	shr r0, #2
	st [bank_s+2], r0

	; destination to bank_d
	ld r0, $6f03
	gt r0, #31
	bzf .bad
	ld r0, $6f05
	gt r0, #63
	bzf .bad
	ld r0, $6f04
	st [bank_d], r0
	ld r0, $6f03
	and r0, #3
	shl r0, #6
	ld r1, $6f05
	or r0, r1
	st [bank_d+1], r0
	ld r0, $6f03
	shr r0, #2
	st [bank_d+2], r0

	ld r0, $6f06
	st [bank_n], r0
	ld r0, $6f07
	st [bank_n+1], r0

	; both ranges must end at or below $80000
	ld r0, [bank_s]
	st [bank_t], r0
	ld r0, [bank_s+1]
	st [bank_t+1], r0
	ld r0, [bank_s+2]
	st [bank_t+2], r0
	push pch
	push pcl
	b bank_end
	eq r0, #0
	bzf .src_ok
	b .bad
.src_ok:
	ld r0, [bank_d]
	st [bank_t], r0
	ld r0, [bank_d+1]
	st [bank_t+1], r0
	ld r0, [bank_d+2]
	st [bank_t+2], r0
	push pch
	push pcl
	b bank_end
	eq r0, #0
	bzf .dst_ok
	b .bad
.dst_ok:
	ld r0, [bank_n]
	ld r1, [bank_n+1]
	or r0, r1
	eq r0, #0
	bzf .ok

	; a destination above the source copies from the end down
	ld r0, [bank_d+2]
	ld r1, [bank_s+2]
	gt r0, r1
	bzf .back
	lt r0, r1
	bzf .fwd
	ld r0, [bank_d+1]
	ld r1, [bank_s+1]
	gt r0, r1
	bzf .back
	lt r0, r1
	bzf .fwd
	ld r0, [bank_d]
	ld r1, [bank_s]
	gt r0, r1
	bzf .back

	; forwards: each chunk stays inside one 256-byte page of both ranges,
	; so it never crosses a bank either
.fwd:
	ld r0, [bank_s]
	xor r0, #255
	ld r1, [bank_d]
	xor r1, #255
	push pch
	push pcl
	b bank_chunk_len
	ld r0, [bank_s]
	st [bank_t], r0
	ld r0, [bank_s+1]
	st [bank_t+1], r0
	ld r0, [bank_s+2]
	st [bank_t+2], r0
	push pch
	push pcl
	b bank_read_chunk
	ld r0, [bank_d]
	st [bank_t], r0
	ld r0, [bank_d+1]
	st [bank_t+1], r0
	ld r0, [bank_d+2]
	st [bank_t+2], r0
	push pch
	push pcl
	b bank_write_chunk
	; the destination is still in bank_t
	push pch
	push pcl
	b bank_step_up
	ld r0, [bank_t]
	st [bank_d], r0
	ld r0, [bank_t+1]
	st [bank_d+1], r0
	ld r0, [bank_t+2]
	st [bank_d+2], r0
	ld r0, [bank_s]
	st [bank_t], r0
	ld r0, [bank_s+1]
	st [bank_t+1], r0
	ld r0, [bank_s+2]
	st [bank_t+2], r0
	push pch
	push pcl
	b bank_step_up
	ld r0, [bank_t]
	st [bank_s], r0
	ld r0, [bank_t+1]
	st [bank_s+1], r0
	ld r0, [bank_t+2]
	st [bank_s+2], r0
	push pch
	push pcl
	b bank_n_down
	bzf .ok
	b .fwd

	; backwards: bank_s and bank_d become the last byte of each range
.back:
	ld r0, [bank_s]
	st [bank_t], r0
	ld r0, [bank_s+1]
	st [bank_t+1], r0
	ld r0, [bank_s+2]
	st [bank_t+2], r0
	push pch
	push pcl
	b bank_end
	mov r0, #0
	st [bank_k], r0
	push pch
	push pcl
	b bank_step_down
	ld r0, [bank_t]
	st [bank_s], r0
	ld r0, [bank_t+1]
	st [bank_s+1], r0
	ld r0, [bank_t+2]
	st [bank_s+2], r0
	ld r0, [bank_d]
	st [bank_t], r0
	ld r0, [bank_d+1]
	st [bank_t+1], r0
	ld r0, [bank_d+2]
	st [bank_t+2], r0
	push pch
	push pcl
	b bank_end
	mov r0, #0
	st [bank_k], r0
	push pch
	push pcl
	b bank_step_down
	ld r0, [bank_t]
	st [bank_d], r0
	ld r0, [bank_t+1]
	st [bank_d+1], r0
	ld r0, [bank_t+2]
	st [bank_d+2], r0
.bloop:
	; the chunk ends at the last bytes and starts no lower than their pages
	ld r0, [bank_s]
	ld r1, [bank_d]
	push pch
	push pcl
	b bank_chunk_len
	ld r0, [bank_s]
	ld r1, [bank_k]
	sub r0, r1
	st [bank_t], r0
	ld r0, [bank_s+1]
	st [bank_t+1], r0
	ld r0, [bank_s+2]
	st [bank_t+2], r0
	push pch
	push pcl
	b bank_read_chunk
	ld r0, [bank_d]
	ld r1, [bank_k]
	sub r0, r1
	st [bank_t], r0
	ld r0, [bank_d+1]
	st [bank_t+1], r0
	ld r0, [bank_d+2]
	st [bank_t+2], r0
	push pch
	push pcl
	b bank_write_chunk
	ld r0, [bank_s]
	st [bank_t], r0
	ld r0, [bank_s+1]
	st [bank_t+1], r0
	ld r0, [bank_s+2]
	st [bank_t+2], r0
	push pch
	push pcl
	b bank_step_down
	ld r0, [bank_t]
	st [bank_s], r0
	ld r0, [bank_t+1]
	st [bank_s+1], r0
	ld r0, [bank_t+2]
	st [bank_s+2], r0
	ld r0, [bank_d]
	st [bank_t], r0
	ld r0, [bank_d+1]
	st [bank_t+1], r0
	ld r0, [bank_d+2]
	st [bank_t+2], r0
	push pch
	push pcl
	b bank_step_down
	ld r0, [bank_t]
	st [bank_d], r0
	ld r0, [bank_t+1]
	st [bank_d+1], r0
	ld r0, [bank_t+2]
	st [bank_d+2], r0
	push pch
	push pcl
	b bank_n_down
	bzf .ok
	b .bloop

.ok:
	ld r0, [bank_saved]
	st $f205, r0
	mov r0, #0
	pop pcl
	pop pch
.bad:
	ld r0, [bank_saved]
	st $f205, r0
	mov r0, #1
	pop pcl
	pop pch

; ---- far_copy's helpers (not API entries)

; bank_chunk_len: bank_k = the smallest of r0, r1 and n - 1 (n = bank_n,
; not 0), which is one less than the chunk length (1-256).
bank_chunk_len:
	lt r1, r0
	bzf .use1
	b .have
.use1:
	mov r0, r1
.have:
	st [bank_k], r0
	ld r0, [bank_n+1]
	eq r0, #0
	bzf .small
	b .done
.small:
	ld r0, [bank_n]
	sub r0, #1
	ld r1, [bank_k]
	lt r0, r1
	bzf .take
	b .done
.take:
	st [bank_k], r0
.done:
	pop pcl
	pop pch

; bank_map: RAM_BANK and bank_ptr for the physical address in bank_t.
bank_map:
	ld r0, [bank_t+2]
	shl r0, #2
	ld r1, [bank_t+1]
	shr r1, #6
	or r0, r1
	st $f205, r0
	ld r0, [bank_t+1]
	and r0, #63
	or r0, #128
	st [bank_ptr+1], r0
	ld r0, [bank_t]
	st [bank_ptr], r0
	pop pcl
	pop pch

; bank_read_chunk: bank_buf gets bank_k + 1 bytes from physical bank_t
; (inside one page).
bank_read_chunk:
	push pch
	push pcl
	b bank_map
	xor r1, r1
.next:
	ldd r0, [bank_ptr]+r1
	st [bank_buf]+r1, r0
	ld r0, [bank_k]
	eq r1, r0
	bzf .done
	add r1, #1
	b .next
.done:
	pop pcl
	pop pch

; bank_write_chunk: bank_k + 1 bytes of bank_buf to physical bank_t.
bank_write_chunk:
	push pch
	push pcl
	b bank_map
	xor r1, r1
.next:
	ld r0, [bank_buf]+r1
	std [bank_ptr]+r1, r0
	ld r0, [bank_k]
	eq r1, r0
	bzf .done
	add r1, #1
	b .next
.done:
	pop pcl
	pop pch

; bank_step_up: bank_t += bank_k + 1 (24 bits).
bank_step_up:
	ld r0, [bank_k]
	st [bank_a], r0
	mov r0, #0
	st [bank_a+1], r0
	st [bank_a+2], r0
	mov r0, #1
	st [bank_c], r0
	b bank_add24

; bank_step_down: bank_t -= bank_k + 1 (24 bits, wrapping): adds
; $ffffff - bank_k.
bank_step_down:
	ld r0, [bank_k]
	xor r0, #255
	st [bank_a], r0
	mov r0, #255
	st [bank_a+1], r0
	st [bank_a+2], r0
	mov r0, #0
	st [bank_c], r0
	b bank_add24

; bank_n_down: bank_n -= bank_k + 1; ZF set when it is then 0.
bank_n_down:
	ld r0, [bank_n]
	st [bank_t], r0
	ld r0, [bank_n+1]
	st [bank_t+1], r0
	mov r0, #0
	st [bank_t+2], r0
	push pch
	push pcl
	b bank_step_down
	ld r0, [bank_t]
	st [bank_n], r0
	ld r1, [bank_t+1]
	st [bank_n+1], r1
	or r0, r1
	eq r0, #0
	pop pcl
	pop pch

; bank_end: bank_t += bank_n; r0 = 0 when bank_t is then at most $80000
; (the range fits in the SRAM), else 1.
bank_end:
	ld r0, [bank_n]
	st [bank_a], r0
	ld r0, [bank_n+1]
	st [bank_a+1], r0
	mov r0, #0
	st [bank_a+2], r0
	st [bank_c], r0
	push pch
	push pcl
	b bank_add24
	ld r0, [bank_t+2]
	lt r0, #8
	bzf .fits
	eq r0, #8
	bzf .edge
	b .over
.edge:
	ld r0, [bank_t+1]
	ld r1, [bank_t]
	or r0, r1
	eq r0, #0
	bzf .fits
.over:
	mov r0, #1
	pop pcl
	pop pch
.fits:
	mov r0, #0
	pop pcl
	pop pch

; bank_add24: bank_t += bank_a + bank_c (24 bits; the carry out is dropped).
bank_add24:
	ld r0, [bank_t]
	ld r1, [bank_a]
	push pch
	push pcl
	b bank_adc
	st [bank_t], r0
	ld r0, [bank_t+1]
	ld r1, [bank_a+1]
	push pch
	push pcl
	b bank_adc
	st [bank_t+1], r0
	ld r0, [bank_t+2]
	ld r1, [bank_a+2]
	push pch
	push pcl
	b bank_adc
	st [bank_t+2], r0
	pop pcl
	pop pch

; bank_adc: r0 = r0 + r1 + bank_c (8 bits); bank_c = the carry out.
bank_adc:
	add r0, r1
	; a sum below an addend wrapped
	lt r0, r1
	bzf .carry
	ld r1, [bank_c]
	add r0, r1
	; now 0 only if it wrapped (carry in 1) or was 0 (carry in 0)
	eq r0, #0
	bzf .zero
	mov r1, #0
	st [bank_c], r1
	pop pcl
	pop pch
.zero:
	st [bank_c], r1
	pop pcl
	pop pch
.carry:
	; at most 254 here, so the carry in cannot wrap it again
	ld r1, [bank_c]
	add r0, r1
	mov r1, #1
	st [bank_c], r1
	pop pcl
	pop pch
