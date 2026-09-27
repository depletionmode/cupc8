; KRN-011: a program for $7000 (tools/mkprg.py) that calls entries of every
; kernel API group and leaves what they gave at $be00-$be3f for simtest
; testApiProgram, then returns to the terminal. Needs the HDMI card, the IO
; card and the storage card with an empty FAT image.

s_hello db "API HELLO"
s_name db "API.TXT"
s_name2 db "API2.TXT"
s_data db "hello"

main:
	ld r0, API_RUN			; 2 while a program runs
	st $be30, r0
	; ------------------------------------------------ group 0: system
	push pch
	push pcl
	b API_VERSION
	st $be00, r0
	push pch
	push pcl
	b API_BLOCK
	st $be01, r0
	st $be02, r1
	push pch
	push pcl
	b API_SLOTS
	st $be03, r0
	st $be04, r1

	; ------------------------------------------------ group 2: graphics
	mov r0, #1
	push pch
	push pcl
	b API_GFX_MODE
	mov r0, #5				; pixel 5,6 in colour 42
	st $6f00, r0
	xor r0, r0
	st $6f01, r0
	mov r0, #6
	st $6f02, r0
	mov r0, #42
	st $6f03, r0
	push pch
	push pcl
	b API_GFX_PIXEL
	mov r0, #5
	st $6f00, r0
	xor r0, r0
	st $6f01, r0
	mov r0, #6
	st $6f02, r0
	push pch
	push pcl
	b API_GFX_GETPIXEL
	st $be09, r0
	st $be0a, r1
	mov r0, #100			; a 10 x 5 rectangle at 100,50 in colour 7
	st $6f00, r0
	xor r0, r0
	st $6f01, r0
	mov r0, #50
	st $6f02, r0
	mov r0, #10
	st $6f03, r0
	xor r0, r0
	st $6f04, r0
	mov r0, #5
	st $6f05, r0
	mov r0, #7
	st $6f06, r0
	push pch
	push pcl
	b API_GFX_FILL_RECT
	mov r0, #104
	st $6f00, r0
	xor r0, r0
	st $6f01, r0
	mov r0, #52
	st $6f02, r0
	push pch
	push pcl
	b API_GFX_GETPIXEL
	st $be0b, r1
	push pch
	push pcl
	b API_GFX_VSYNC
	st $be0c, r0
	xor r0, r0
	push pch
	push pcl
	b API_GFX_MODE

	; ------------------------------------------------ group 3: e-ink (on HDMI)
	push pch
	push pcl
	b API_EINK_GET
	st $be0d, r0
	ld r0, $6f00
	st $be0e, r0
	ld r0, $6f05
	st $be0f, r0
	push pch
	push pcl
	b API_EINK_STATUS
	st $be10, r0
	ld r0, $6f02
	st $be11, r0
	push pch
	push pcl
	b API_EINK_AUTO
	st $be12, r0

	; ------------------------------------------------ group 4: storage
	push pch
	push pcl
	b API_ST_INFO
	st $be13, r0
	ld r0, $6f00
	st $be14, r0
	mov r0, #<[s_name]		; API.TXT, handle 1, write
	st $6f00, r0
	mov r0, #>[s_name]
	st $6f01, r0
	mov r0, #1
	mov r1, #1
	push pch
	push pcl
	b API_ST_OPEN
	st $be15, r0
	mov r0, #<[s_data]		; hello
	st $6f00, r0
	mov r0, #>[s_data]
	st $6f01, r0
	mov r0, #1
	mov r1, #5
	push pch
	push pcl
	b API_ST_WRITE
	st $be16, r0
	mov r0, #1
	push pch
	push pcl
	b API_ST_CLOSE
	st $be17, r0
	mov r0, #<[s_name]		; again, to read
	st $6f00, r0
	mov r0, #>[s_name]
	st $6f01, r0
	mov r0, #1
	mov r1, #0
	push pch
	push pcl
	b API_ST_OPEN
	st $be18, r0
	mov r0, #1				; from byte 1
	st $6f00, r0
	xor r0, r0
	st $6f01, r0
	st $6f02, r0
	st $6f03, r0
	mov r0, #1
	push pch
	push pcl
	b API_ST_SEEK
	st $be19, r0
	mov r0, #0x40			; into $be40
	st $6f00, r0
	mov r0, #0xbe
	st $6f01, r0
	mov r0, #1
	mov r1, #20
	push pch
	push pcl
	b API_ST_READ
	st $be1a, r0
	st $be1b, r1
	mov r0, #1
	push pch
	push pcl
	b API_ST_CLOSE
	mov r0, #<[s_name]		; API.TXT to API2.TXT
	st $6f00, r0
	mov r0, #>[s_name]
	st $6f01, r0
	mov r0, #<[s_name2]
	st $6f02, r0
	mov r0, #>[s_name2]
	st $6f03, r0
	push pch
	push pcl
	b API_ST_RENAME
	st $be1c, r0
	push pch
	push pcl
	b API_ST_DIR_FIRST
	st $be1d, r0
	ld r0, $6f00			; size, low byte
	st $be1e, r0
	ld r0, $6f05			; name length
	st $be1f, r0
	ld r0, $6f09			; the name's 4th character
	st $be20, r0
	push pch
	push pcl
	b API_ST_DIR_NEXT
	st $be21, r0
	mov r0, #<[s_name2]
	st $6f00, r0
	mov r0, #>[s_name2]
	st $6f01, r0
	push pch
	push pcl
	b API_ST_DELETE
	st $be22, r0
	mov r0, #<[s_name2]
	st $6f00, r0
	mov r0, #>[s_name2]
	st $6f01, r0
	mov r0, #2
	mov r1, #0
	push pch
	push pcl
	b API_ST_OPEN
	st $be23, r0

	; ------------------------------------------------ group 5's first blank entry, group 7
	push pch
	push pcl
	b $1213
	st $be24, r0
	ld r0, API_ERR
	st $be25, r0
	push pch
	push pcl
	b $12a3
	st $be27, r0

	; ------------------------------------------------ group 6: timers
	push pch
	push pcl
	b API_TICKS
	ld r0, $6f00
	st $be28, r0
	ld r0, $6f01
	st $be29, r0
	mov r0, #20
	mov r1, #0
	push pch
	push pcl
	b API_WAIT_MS
	st $be26, r0
	push pch
	push pcl
	b API_TICKS
	ld r0, $6f00
	st $be2c, r0
	ld r0, $6f01
	st $be2d, r0

	; ------------------------------------------------ group 1: console
	mov r0, #<[s_hello]
	st $6f00, r0
	mov r0, #>[s_hello]
	st $6f01, r0
	push pch
	push pcl
	b API_PUTS
	mov r0, #33				; !
	push pch
	push pcl
	b API_PUTC
	mov r0, #10
	mov r1, #20
	push pch
	push pcl
	b API_GOTOXY
	mov r0, #0x1e			; yellow on blue
	push pch
	push pcl
	b API_ATTR
	mov r0, #88				; X at 10,20
	push pch
	push pcl
	b API_PUTC
	mov r0, #0x07
	push pch
	push pcl
	b API_ATTR
	push pch
	push pcl
	b API_GETXY
	st $be05, r0
	ld r0, $6f00
	st $be06, r0
	ld r0, $6f01
	st $be07, r0
	push pch
	push pcl
	b API_POLLKEY
	st $be08, r0
	xor r0, r0				; P at 0,29 in attribute $4e
	st $6f00, r0
	mov r0, #29
	st $6f01, r0
	mov r0, #80
	st $6f02, r0
	mov r0, #0x4e
	st $6f03, r0
	push pch
	push pcl
	b API_POKE
	mov r0, #0
	mov r1, #22
	push pch
	push pcl
	b API_GOTOXY

	mov r0, #0xa5			; done
	st $be3f, r0
	pop pcl
	pop pch
