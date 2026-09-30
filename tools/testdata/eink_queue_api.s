; GPU-010 extension: genuine kernel short-command API pressure while the
; automatic 750 renderer is active. No raw slot writes or delay changes.
qi: resb 1
qj: resb 1
s_done db "API QUEUE COMPLETE"

main:
	mov r0, #0
	push pch
	push pcl
	b API_GFX_MODE
	mov r0, #7
	push pch
	push pcl
	b API_CLS
	mov r0, #0
	push pch
	push pcl
	b API_CURSOR
	; An automatic partial every 10 ms of quiet/capped output ensures real
	; rendering overlaps sustained API traffic, within the existing policy.
	mov r0, #1
	st $6f00, r0
	st $6f01, r0
	mov r0, #30
	st $6f02, r0
	mov r0, #1
	st $6f03, r0
	st $6f04, r0
	xor r0, r0
	st $6f05, r0
	push pch
	push pcl
	b API_EINK_AUTO
	xor r0, r0
	st [qi], r0
.outer:
	mov r0, #46
	push pch
	push pcl
	b API_PUTC
	xor r0, r0
	st [qj], r0
.attrs:
	mov r0, #7
	push pch
	push pcl
	b API_ATTR
	ld r0, [qj]
	add r0, #1
	st [qj], r0
	eq r0, #40
	bzf .poke
	b .attrs
.poke:
	ld r0, [qi]
	st $6f00, r0
	mov r0, #10
	st $6f01, r0
	mov r0, #35
	st $6f02, r0
	mov r0, #7
	st $6f03, r0
	push pch
	push pcl
	b API_POKE
	ld r0, [qi]
	add r0, #1
	st [qi], r0
	eq r0, #60
	bzf .done
	b .outer
.done:
	; The direct EINK_REFRESH wrapper also emits a short command. Repeated
	; no-change partial requests exercise its credits without inventing new
	; controller timing or raising any deadline.
	xor r0, r0
	st [qj], r0
.refreshes:
	mov r0, #0
	push pch
	push pcl
	b API_EINK_REFRESH
	ld r0, [qj]
	add r0, #1
	st [qj], r0
	eq r0, #40
	bzf .finish
	b .refreshes
.finish:
	; Exercise common zero/one/two-byte console command paths too.
	mov r0, #0
	mov r1, #12
	push pch
	push pcl
	b API_GOTOXY
	push pch
	push pcl
	b API_CLEOL
	mov r0, #<[s_done]
	st API_ARGS, r0
	mov r0, #>[s_done]
	st $6f01, r0
	push pch
	push pcl
	b API_PUTS
	pop pcl
	pop pch
