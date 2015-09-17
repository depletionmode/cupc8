
term_basic_prog_buf_idx: resb 1
term_basic_prog_buf: resb 256

term:
.done:
	pop pcl
	pop pch

cmd_run:
	; run program in BASIC program buffer

	mov r0, #>[term_basic_prog_buf]
	mov r1, #<[term_basic_prog_buf]
	push pch
	push pcl
	b ubasic_init
.loop:
	push pch
	push pcl
	b ubasic_run
	push pch
	push pcl
	b ubasic_finished
	eq r0, #0
	bzf .loop

.done:
	pop pcl
	pop pch

cmd_new:
	; reset basic program buffer

	xor r1, r1
.loop:
	ld r0, [term_basic_prog_buf_idx]
	gt r1, r0
	bzf .zeroed
	xor r0, r0
	st [term_basic_prog_buf]+r1, r0
	add r1, #1
	b .loop
	
.zeroed:
	xor r0, r0
	st [term_basic_prog_buf_idx], r0

.done:
	pop pcl
	pop pch

cmd_basic_statement:
	; copy basic statement into program buffer
.done:
	pop pcl
	pop pch

