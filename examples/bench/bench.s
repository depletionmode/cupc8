; bench- a small native CUPC/8 speed test (doc/proposals/kernel-api.md).
; Prints the CPU speed (a 4-instruction loop), the RAM write and read speed
; (std / ldd through a pointer) and a RAM check (a pattern over 4 KB, read
; back). Each timed test runs for about 1 s of the millisecond counter.
;
; Build (kernel/api.inc first, loaded at $7000, with the C8P header)-
;   python3 tools/mkprg.py examples/bench/bench.s -o build/examples/bench.prg
; Run- `exec "BENCH.PRG"` from the SD card, or cupc8.py run build/examples/bench.prg.
;
; Timing- the work goes in chunks (256 loop iterations = about 1024
; instructions, or one 256-byte page = about 1280 instructions); after each
; chunk `chunk_done` counts it and reads API_TICKS. That costs about 55
; instructions (the call, API_TICKS's ~20, a 16-bit subtract and compare), so
; the numbers come out about 5% (CPU) and 4% (RAM) below the bare loop's.
; The buffer is $a000-$afff, well above the program.

msg_title db "\nCUPC/8 benchmark- each test runs for about 1 s\n"
msg_cpu db "CPU:       "
msg_kips db " K loop instructions/s- "
msg_chunks db " x 1024 in "
msg_ms db " ms\n"
msg_wr db "RAM write: "
msg_rd db "RAM read:  "
msg_kbs db " KB/s- "
msg_pages db " pages of 256 bytes in "
msg_chk db "RAM check: "
msg_ok db "OK- 4096 bytes at $a000-$afff\n"
msg_bad db " bad bytes of 4096 at $a000-$afff\n"
; the decimal printer's divisors, low byte first- 10000 1000 100 10
divs db 16, 39, 232, 3, 100, 0, 10, 0

cnt: resb 2		; chunks done
t0: resb 2		; API_TICKS at the start (low 16 bits)
el: resb 2		; ms since t0
ptr: resb 2		; the pointer std / ldd go through
key: resb 1		; the RAM check's pattern for this page
got: resb 1
idx: resb 1
bad: resb 2
num: resb 2		; pnum's number, divisor, digit, state
div: resb 2
dig: resb 1
di: resb 1
started: resb 1

main:
	mov r0, #<[msg_title]
	mov r1, #>[msg_title]
	push pch
	push pcl
	b puts

	; ---- CPU: 256 x (sub, eq, bzf, b) a chunk
	push pch
	push pcl
	b tstart
.cpu:
	xor r0, r0
.spin:
	sub r0, #1
	eq r0, #0
	bzf .spun
	b .spin
.spun:
	push pch
	push pcl
	b chunk_done
	eq r0, #1
	bzf .cpu_done
	b .cpu
.cpu_done:
	mov r0, #<[msg_cpu]
	mov r1, #>[msg_cpu]
	push pch
	push pcl
	b puts
	push pch
	push pcl
	b pcnt
	mov r0, #<[msg_kips]
	mov r1, #>[msg_kips]
	push pch
	push pcl
	b puts
	push pch
	push pcl
	b pcnt
	mov r0, #<[msg_chunks]
	mov r1, #>[msg_chunks]
	push pch
	push pcl
	b puts
	push pch
	push pcl
	b pms

	; ---- RAM write: std over a page a chunk, round $a000-$afff
	push pch
	push pcl
	b tstart
.wpage:
	mov r0, #85
	xor r1, r1
.w:
	std [ptr]+r1, r0
	add r1, #1
	eq r1, #0
	bzf .wdone
	b .w
.wdone:
	push pch
	push pcl
	b next_page
	push pch
	push pcl
	b chunk_done
	eq r0, #1
	bzf .w_end
	b .wpage
.w_end:
	mov r0, #<[msg_wr]
	mov r1, #>[msg_wr]
	push pch
	push pcl
	b puts
	push pch
	push pcl
	b pspeed

	; ---- RAM read: ldd over a page a chunk
	push pch
	push pcl
	b tstart
.rpage:
	xor r1, r1
.r:
	ldd r0, [ptr]+r1
	add r1, #1
	eq r1, #0
	bzf .rdone
	b .r
.rdone:
	push pch
	push pcl
	b next_page
	push pch
	push pcl
	b chunk_done
	eq r0, #1
	bzf .r_end
	b .rpage
.r_end:
	mov r0, #<[msg_rd]
	mov r1, #>[msg_rd]
	push pch
	push pcl
	b puts
	push pch
	push pcl
	b pspeed

	; ---- RAM check: byte i of page p holds i xor (7 + 29p), 16 pages
	xor r0, r0
	st [ptr], r0
	st [bad], r0
	st [bad+1], r0
	mov r0, #160
	st [ptr+1], r0
	mov r0, #7
	st [key], r0
.cw_page:
	xor r1, r1
.cw:
	ld r0, [key]
	xor r0, r1
	std [ptr]+r1, r0
	add r1, #1
	eq r1, #0
	bzf .cw_next
	b .cw
.cw_next:
	ld r0, [key]
	add r0, #29
	st [key], r0
	ld r0, [ptr+1]
	add r0, #1
	st [ptr+1], r0
	eq r0, #176
	bzf .cr_start
	b .cw_page
.cr_start:
	mov r0, #160
	st [ptr+1], r0
	mov r0, #7
	st [key], r0
.cr_page:
	xor r1, r1
.cr:
	ldd r0, [ptr]+r1
	st [got], r0
	st [idx], r1
	ld r0, [key]
	xor r0, r1
	ld r1, [got]
	eq r0, r1
	bzf .cr_good
	ld r0, [bad]
	add r0, #1
	st [bad], r0
	eq r0, #0
	bzf .cr_carry
	b .cr_good
.cr_carry:
	ld r0, [bad+1]
	add r0, #1
	st [bad+1], r0
.cr_good:
	ld r1, [idx]
	add r1, #1
	eq r1, #0
	bzf .cr_next
	b .cr
.cr_next:
	ld r0, [key]
	add r0, #29
	st [key], r0
	ld r0, [ptr+1]
	add r0, #1
	st [ptr+1], r0
	eq r0, #176
	bzf .cr_done
	b .cr_page
.cr_done:
	mov r0, #<[msg_chk]
	mov r1, #>[msg_chk]
	push pch
	push pcl
	b puts
	ld r0, [bad]
	ld r1, [bad+1]
	or r0, r1
	eq r0, #0
	bzf .all_ok
	ld r0, [bad]
	st [num], r0
	ld r0, [bad+1]
	st [num+1], r0
	push pch
	push pcl
	b pnum
	mov r0, #<[msg_bad]
	mov r1, #>[msg_bad]
	push pch
	push pcl
	b puts
	b .exit
.all_ok:
	mov r0, #<[msg_ok]
	mov r1, #>[msg_ok]
	push pch
	push pcl
	b puts
.exit:
	; return to the terminal (as API_EXIT would)
	pop pcl
	pop pch

; start a timed test- cnt = 0, ptr = $a000, t0 = API_TICKS
tstart:
	xor r0, r0
	st [cnt], r0
	st [cnt+1], r0
	st [ptr], r0
	mov r0, #160
	st [ptr+1], r0
	push pch
	push pcl
	b API_TICKS
	ld r0, API_ARGS
	st [t0], r0
	ld r0, $6f01
	st [t0+1], r0
	pop pcl
	pop pch

; ptr to the next page of $a000-$afff
next_page:
	ld r0, [ptr+1]
	add r0, #1
	and r0, #15
	or r0, #160
	st [ptr+1], r0
	pop pcl
	pop pch

; a chunk is done- cnt + 1, el = API_TICKS - t0, r0 = 1 once el >= 1000
chunk_done:
	ld r0, [cnt]
	add r0, #1
	st [cnt], r0
	eq r0, #0
	bzf .carry
	b .ticks
.carry:
	ld r0, [cnt+1]
	add r0, #1
	st [cnt+1], r0
.ticks:
	push pch
	push pcl
	b API_TICKS
	; el high = now high - t0 high, less a borrow from the low bytes
	ld r0, $6f01
	ld r1, [t0+1]
	sub r0, r1
	st [el+1], r0
	ld r0, API_ARGS
	ld r1, [t0]
	lt r0, r1
	bzf .borrow
	b .low
.borrow:
	ld r0, [el+1]
	sub r0, #1
	st [el+1], r0
.low:
	ld r0, API_ARGS
	sub r0, r1
	st [el], r0
	; >= 1000 ($03e8)- high > 3, or high = 3 and low > 231
	ld r0, [el+1]
	gt r0, #3
	bzf .yes
	eq r0, #3
	bzf .high3
	b .no
.high3:
	ld r0, [el]
	gt r0, #231
	bzf .yes
.no:
	xor r0, r0
	pop pcl
	pop pch
.yes:
	mov r0, #1
	pop pcl
	pop pch

; print cnt / el in decimal
pcnt:
	ld r0, [cnt]
	st [num], r0
	ld r0, [cnt+1]
	st [num+1], r0
	push pch
	push pcl
	b pnum
	pop pcl
	pop pch

pms:
	ld r0, [el]
	st [num], r0
	ld r0, [el+1]
	st [num+1], r0
	push pch
	push pcl
	b pnum
	mov r0, #<[msg_ms]
	mov r1, #>[msg_ms]
	push pch
	push pcl
	b puts
	pop pcl
	pop pch

; "K KB/s- P pages of 256 bytes in M ms" with K = P / 4 (P pages in ~1 s)
pspeed:
	ld r0, [cnt+1]
	shl r0, #6
	ld r1, [cnt]
	shr r1, #2
	or r0, r1
	st [num], r0
	ld r0, [cnt+1]
	shr r0, #2
	st [num+1], r0
	push pch
	push pcl
	b pnum
	mov r0, #<[msg_kbs]
	mov r1, #>[msg_kbs]
	push pch
	push pcl
	b puts
	push pch
	push pcl
	b pcnt
	mov r0, #<[msg_pages]
	mov r1, #>[msg_pages]
	push pch
	push pcl
	b puts
	push pch
	push pcl
	b pms
	pop pcl
	pop pch

; print the NUL-terminated string at r1 (high), r0 (low)
puts:
	st $6f00, r0			; API_ARGS
	st $6f01, r1
	push pch
	push pcl
	b API_PUTS
	pop pcl
	pop pch

; print num (16 bits) in decimal, no leading zeros; num is used up
pnum:
	xor r0, r0
	st [started], r0
	st [di], r0
.digit:
	ld r1, [di]
	ld r0, [divs]+r1
	st [div], r0
	add r1, #1
	ld r0, [divs]+r1
	st [div+1], r0
	mov r0, #48
	st [dig], r0
.try:
	; num >= div? by the high bytes, then the low
	ld r0, [num+1]
	ld r1, [div+1]
	gt r0, r1
	bzf .take
	lt r0, r1
	bzf .out
	ld r0, [num]
	ld r1, [div]
	lt r0, r1
	bzf .out
.take:
	; num -= div
	ld r0, [num]
	ld r1, [div]
	lt r0, r1
	bzf .borrow
	b .nob
.borrow:
	ld r0, [num+1]
	sub r0, #1
	st [num+1], r0
.nob:
	ld r0, [num]
	ld r1, [div]
	sub r0, r1
	st [num], r0
	ld r0, [num+1]
	ld r1, [div+1]
	sub r0, r1
	st [num+1], r0
	ld r0, [dig]
	add r0, #1
	st [dig], r0
	b .try
.out:
	ld r0, [dig]
	eq r0, #48
	bzf .zero
	b .put
.zero:
	ld r0, [started]
	eq r0, #0
	bzf .skip
.put:
	mov r0, #1
	st [started], r0
	ld r0, [dig]
	push pch
	push pcl
	b API_PUTC
.skip:
	ld r0, [di]
	add r0, #2
	st [di], r0
	eq r0, #8
	bzf .last
	b .digit
.last:
	ld r0, [num]
	add r0, #48
	push pch
	push pcl
	b API_PUTC
	pop pcl
	pop pch
