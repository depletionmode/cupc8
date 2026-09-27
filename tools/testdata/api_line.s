; KRN-033: the API entries BASIC as a program brought (kernel/sys.s): it
; prints the storage error $03's message (API_ST_PERROR: "file not found"),
; reads a line (API_READLINE) into $be40 and leaves r0, r1 at $be00-$be01,
; clears the terminal's hook (API_TERM_HOOK 0, 0: r0 at $be02; the kernel
; loads BASIC again after the program, which sets it again), then $be3f = $a5.
; Its results are above BASIC ($7000-$9fff), which comes back over it.

main:
	mov r0, #3
	push pch
	push pcl
	b API_ST_PERROR
	mov r0, #0x40
	st API_ARGS, r0
	mov r0, #0xbe
	st $6f01, r0
	push pch
	push pcl
	b API_READLINE
	st $be00, r0
	st $be01, r1
	xor r0, r0
	xor r1, r1
	push pch
	push pcl
	b API_TERM_HOOK
	st $be02, r0
	mov r0, #0xa5
	st $be3f, r0
	pop pcl
	pop pch
