; SIM-002 LD ST LDD STD, direct and indexed, every register combination.
; LD Ra,$a+Rb and ST $a+Ra,Rb: the indexed register is the other one.
; LDD/STD indexed are post-indexed: [[addr] + index], a 16-bit sum.
main:
	mov r0, #0x11
	mov r1, #0x22
	st $2000, r0
	st $2001, r1
;@ m2000=11 m2001=22
	ld r1, $2000
	ld r0, $2001
;@ r0=22 r1=11
	mov r0, #3
	mov r1, #0x44
	st $2000+r0, r1
;@ m2003=44
	mov r1, #2
	mov r0, #0x55
	st $2000+r1, r0
;@ m2002=55
	mov r0, #0
	ld r0, $2000+r1
;@ r0=55
	mov r0, #3
	ld r1, $2000+r0
;@ r1=44
	mov r0, #0x03
	st $2010, r0
	mov r0, #0x20
	st $2011, r0
	ldd r1, $2010
;@ r1=44
	mov r0, #0x99
	std $2010, r0
;@ m2003=99
	mov r0, #0x00
	st $2020, r0
	mov r0, #0x30
	st $2021, r0
	mov r1, #2
	mov r0, #0x77
	std $2020+r1, r0
;@ m3002=77
	mov r0, #0
	ldd r0, $2020+r1
;@ r0=77
	mov r0, #2
	mov r1, #0x66
	std $2020+r0, r1
;@ m3002=66
	mov r1, #0
	mov r0, #2
	ldd r1, $2020+r0
;@ r1=66
	mov r0, #0xff
	st $2020, r0
	mov r1, #2
	mov r0, #0x5a
	std $2020+r1, r0
;@ m3101=5a
	mov r0, #0
	ldd r0, $2020+r1
;@ r0=5a
	halt
