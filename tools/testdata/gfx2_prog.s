; KRN-019: a program that draws in the e-ink card's native mode 2 through
; the kernel API: API_GFX_MODE 2, API_CLS 3 (white), then every API_GFX2
; entry. It leaves what they gave at $be00-$be11:
;   $be00 API_GFX_MODE 2
;   $be01 PIXEL (10, 20) grey 0          $be02 FILL_RECT (100, 50) 20 x 10 grey 1
;   $be03 RECT (200, 50) 30 x 20 grey 0  $be04 LINE (0, 400) - (640, 400) grey 2
;   $be05 BLIT1 (300, 100) 16 x 2        $be06 BLIT2 (300, 110) 8 x 1
;   $be07 TEXT16 "Hi" (400, 200)         $be08 TEXT8 "A" (400, 250) on grey 2
;   $be09, $be0a GETPIXEL (10, 20): r0, r1   $be0b GETPIXEL (105, 55): r1
;   $be0c BLIT1 1021 wide (too wide)     $be0d BLIT1 800 x 100 (too big)
;   $be0e BLIT1 1020 x 1 (the widest), from $7000, at (0, 470)
;   $be0f VSCROLL down 8 rows, grey 1
;   $be10 GETPIXEL (10, 28): r1          $be11 GETPIXEL (0, 0): r1
; On HDMI every r0 is $ff.

t_pixel db 10,0,20,0,0
t_fill db 100,0,50,0,20,0,10,0,1
t_rect db 200,0,50,0,30,0,20,0,0
t_line db 0,0,144,1,128,2,144,1,2
t_blit1 db 44,1,100,0,16,0,2,0,0,3
pic1 db 240,15,170,85
t_blit2 db 44,1,110,0,8,0,1,0
pic2 db 27,228
t_text16 db 144,1,200,0,0,255
s_hi db "Hi"
t_text8 db 144,1,250,0,0,2
s_a db "A"
t_get1 db 10,0,20,0
t_get2 db 105,0,55,0
t_big1 db 0,0,0,0,253,3,1,0,0,3
t_big2 db 0,0,0,0,32,3,100,0,0,3
t_edge db 0,0,214,1,252,3,1,0,0,255
t_vscroll db 248,255,1
t_get3 db 10,0,28,0
t_get4 db 0,0,0,0
cp: resb 2

main:
	mov r0, #2
	push pch
	push pcl
	b API_GFX_MODE
	st $be00, r0
	mov r0, #3
	push pch
	push pcl
	b API_CLS

	mov r0, #<[t_pixel]
	mov r1, #>[t_pixel]
	push pch
	push pcl
	b setargs
	push pch
	push pcl
	b API_GFX2_PIXEL
	st $be01, r0

	mov r0, #<[t_fill]
	mov r1, #>[t_fill]
	push pch
	push pcl
	b setargs
	push pch
	push pcl
	b API_GFX2_FILL_RECT
	st $be02, r0

	mov r0, #<[t_rect]
	mov r1, #>[t_rect]
	push pch
	push pcl
	b setargs
	push pch
	push pcl
	b API_GFX2_RECT
	st $be03, r0

	mov r0, #<[t_line]
	mov r1, #>[t_line]
	push pch
	push pcl
	b setargs
	push pch
	push pcl
	b API_GFX2_LINE
	st $be04, r0

	mov r0, #<[t_blit1]
	mov r1, #>[t_blit1]
	push pch
	push pcl
	b setargs
	mov r0, #<[pic1]
	st $6f0a, r0
	mov r0, #>[pic1]
	st $6f0b, r0
	push pch
	push pcl
	b API_GFX2_BLIT1
	st $be05, r0

	mov r0, #<[t_blit2]
	mov r1, #>[t_blit2]
	push pch
	push pcl
	b setargs
	mov r0, #<[pic2]
	st $6f08, r0
	mov r0, #>[pic2]
	st $6f09, r0
	push pch
	push pcl
	b API_GFX2_BLIT2
	st $be06, r0

	mov r0, #<[t_text16]
	mov r1, #>[t_text16]
	push pch
	push pcl
	b setargs
	mov r0, #<[s_hi]
	st $6f07, r0
	mov r0, #>[s_hi]
	st $6f08, r0
	push pch
	push pcl
	b API_GFX2_TEXT16
	st $be07, r0

	mov r0, #<[t_text8]
	mov r1, #>[t_text8]
	push pch
	push pcl
	b setargs
	mov r0, #<[s_a]
	st $6f07, r0
	mov r0, #>[s_a]
	st $6f08, r0
	push pch
	push pcl
	b API_GFX2_TEXT8
	st $be08, r0

	mov r0, #<[t_get1]
	mov r1, #>[t_get1]
	push pch
	push pcl
	b setargs
	push pch
	push pcl
	b API_GFX2_GETPIXEL
	st $be09, r0
	st $be0a, r1

	mov r0, #<[t_get2]
	mov r1, #>[t_get2]
	push pch
	push pcl
	b setargs
	push pch
	push pcl
	b API_GFX2_GETPIXEL
	st $be0b, r1

	mov r0, #<[t_big1]
	mov r1, #>[t_big1]
	push pch
	push pcl
	b setargs
	push pch
	push pcl
	b blit_here
	st $be0c, r0

	mov r0, #<[t_big2]
	mov r1, #>[t_big2]
	push pch
	push pcl
	b setargs
	push pch
	push pcl
	b blit_here
	st $be0d, r0

	mov r0, #<[t_edge]
	mov r1, #>[t_edge]
	push pch
	push pcl
	b setargs
	push pch
	push pcl
	b blit_here
	st $be0e, r0

	mov r0, #<[t_vscroll]
	mov r1, #>[t_vscroll]
	push pch
	push pcl
	b setargs
	push pch
	push pcl
	b API_GFX2_VSCROLL
	st $be0f, r0

	mov r0, #<[t_get3]
	mov r1, #>[t_get3]
	push pch
	push pcl
	b setargs
	push pch
	push pcl
	b API_GFX2_GETPIXEL
	st $be10, r1

	mov r0, #<[t_get4]
	mov r1, #>[t_get4]
	push pch
	push pcl
	b setargs
	push pch
	push pcl
	b API_GFX2_GETPIXEL
	st $be11, r1
	pop pcl
	pop pch

; API_GFX2_BLIT1 of the picture at $7000 (this program's own bytes)
blit_here:
	xor r0, r0
	st $6f0a, r0
	mov r0, #0x70
	st $6f0b, r0
	b API_GFX2_BLIT1

; API_ARGS = the 12 bytes at r0 (low), r1 (high)
setargs:
	st [cp], r0
	st [cp+1], r1
	xor r1, r1
.loop:
	ldd r0, [cp]+r1
	st $6f00+r1, r0
	add r1, #1
	eq r1, #12
	bzf .done
	b .loop
.done:
	pop pcl
	pop pch
