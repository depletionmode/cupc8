; KRN-012: a program `exec` runs from the storage card (tools/mkprg.py).
; Its 300 bytes of data make the file span three of exec's 128-byte chunks;
; it prints NATIVE OK if they all came in (their sum is 226 mod 256), else
; NATIVE BAD. (The kernel loads BASIC over it once it ends, so the test
; cannot look at $7000 afterwards.)

s_ok db "NATIVE OK"
s_bad db "NATIVE BAD"
t0 db 3,10,17,24,31,38,45,52,59,66,73,80,87,94,101,108,115,122,129,136
t1 db 143,150,157,164,171,178,185,192,199,206,213,220,227,234,241,248,255,6,13,20
t2 db 27,34,41,48,55,62,69,76,83,90,97,104,111,118,125,132,139,146,153,160
t3 db 167,174,181,188,195,202,209,216,223,230,237,244,251,2,9,16,23,30,37,44
t4 db 51,58,65,72,79,86,93,100,107,114,121,128,135,142,149,156,163,170,177,184
t5 db 191,198,205,212,219,226,233,240,247,254,5,12,19,26,33,40,47,54,61,68
t6 db 75,82,89,96,103,110,117,124,131,138,145,152,159,166,173,180,187,194,201,208
t7 db 215,222,229,236,243,250,1,8,15,22,29,36,43,50,57,64,71,78,85,92
t8 db 99,106,113,120,127,134,141,148,155,162,169,176,183,190,197,204,211,218,225,232
t9 db 239,246,253,4,11,18,25,32,39,46,53,60,67,74,81,88,95,102,109,116
t10 db 123,130,137,144,151,158,165,172,179,186,193,200,207,214,221,228,235,242,249,0
t11 db 7,14,21,28,35,42,49,56,63,70,77,84,91,98,105,112,119,126,133,140
t12 db 147,154,161,168,175,182,189,196,203,210,217,224,231,238,245,252,3,10,17,24
t13 db 31,38,45,52,59,66,73,80,87,94,101,108,115,122,129,136,143,150,157,164
t14 db 171,178,185,192,199,206,213,220,227,234,241,248,255,6,13,20,27,34,41,48

sum: resb 1
ptr: resb 2
left: resb 2

main:
	mov r0, #<[t0]
	st [ptr], r0
	mov r0, #>[t0]
	st [ptr+1], r0
	xor r0, r0
	st [sum], r0
	mov r0, #44				; 300 bytes
	st [left], r0
	mov r0, #1
	st [left+1], r0
.byte:
	ldd r0, [ptr]
	ld r1, [sum]
	add r1, r0
	st [sum], r1
	ld r0, [ptr]
	add r0, #1
	st [ptr], r0
	eq r0, #0
	bzf .ptr_hi
	b .count
.ptr_hi:
	ld r0, [ptr+1]
	add r0, #1
	st [ptr+1], r0
.count:
	ld r0, [left]
	eq r0, #0
	sub r0, #1
	st [left], r0
	bzf .left_hi
	b .more
.left_hi:
	ld r0, [left+1]
	sub r0, #1
	st [left+1], r0
.more:
	ld r0, [left]
	ld r1, [left+1]
	or r0, r1
	eq r0, #0
	bzf .summed
	b .byte
.summed:
	ld r0, [sum]
	eq r0, #226
	bzf .ok
	mov r0, #<[s_bad]
	st $6f00, r0
	mov r0, #>[s_bad]
	st $6f01, r0
	b .print
.ok:
	mov r0, #<[s_ok]
	st $6f00, r0
	mov r0, #>[s_ok]
	st $6f01, r0
.print:
	push pch
	push pcl
	b API_PUTS
	pop pcl
	pop pch
