; SIM-002 ALU: ADD SUB AND OR XOR NOR, register (all Ra/Rb) and immediate.
; Results are 8 bits; the ALU never touches Z (manual 3.1).
main:
	mov r0, #200
	mov r1, #100
	add r0, r1
;@ r0=2c r1=64
	add r1, r0
;@ r0=2c r1=90
	add r0, r0
;@ r0=58
	add r1, r1
;@ r1=20
	sub r0, r1
;@ r0=38
	sub r1, r0
;@ r1=e8
	sub r0, r0
;@ r0=00
	sub r1, r1
;@ r1=00
	add r0, #0x7f
	add r1, #0xff
;@ r0=7f r1=ff
	add r1, #1
	sub r0, #0x80
;@ r0=ff r1=00
	sub r1, #1
;@ r1=ff
	mov r0, #0xf0
	mov r1, #0x3c
	and r0, r1
;@ r0=30
	or r1, r0
;@ r1=3c
	xor r0, r1
;@ r0=0c
	nor r1, r0
;@ r1=c3
	and r1, r1
	or r0, r0
;@ r0=0c r1=c3
	xor r0, r0
;@ r0=00
	nor r0, r0
;@ r0=ff
	and r0, #0x5a
	or r1, #0x0c
;@ r0=5a r1=cf
	xor r0, #0xff
	nor r1, #0x10
;@ r0=a5 r1=20
	xor r1, r1
	nor r1, #0
;@ r1=ff
	and r1, r0
;@ r1=a5
	mov r0, #0x0f
	or r0, r1
;@ r0=af
	xor r1, r0
;@ r1=0a
	nor r0, r1
;@ r0=50
	and r0, #0
	or r1, #0xf0
	xor r1, #0x0a
;@ r0=00 r1=f0 z=0
	halt
