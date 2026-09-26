; snake- a small game through the kernel API (doc/proposals/kernel-api.md),
; on either graphics card.
;
; HDMI: the GFX mode (320 x 240, 256 colours), 40 x 30 cells of 8 x 8
; pixels, a step every 110 ms. The e-ink card (API_GFX_MODE 2 answers 0
; there, $ff on HDMI): its native mode 2 (eink-card.md) in four greys, cells
; of 16 x 16 pixels, 40 x 30 of them centred on the 648 x 480 panel or 50 x 30
; filling the 800 x 480 one; white ground, a black snake, dark grey walls,
; the food light grey in a black ring, the score in the 8 x 16 font. E-paper
; is slow, so there a step is about half a second: after each move the game
; asks for a partial refresh (its own: the card's automatic refresh is off
; while it runs, and put back as it was at the end).
;
; Steer with W A S D (or the arrow keys), eat the food, don't hit the wall
; or yourself. Q quits. What is in a cell is read back from the screen
; (API_GFX_GETPIXEL, API_GFX2_GETPIXEL), so the picture is the game's only
; map.
;
; Build- python3 tools/mkprg.py examples/snake/snake.s -o build/SNAKE.PRG
; Run- exec "SNAKE.PRG"

%define BLACK 0
%define WALL 9
%define SNAKE 10
%define FOOD 12
%define WHITE 15
%define STEP_MS 110
; e-ink: the wait after each move's refresh (the refresh, about 0.4 s,
; runs meanwhile): 450 ms
%define EINK_STEP_LO 0xc2
%define EINK_STEP_HI 1

score_txt db "SCORE 000"
msg_over db "GAME OVER"
msg_again db "SPACE PLAYS AGAIN, Q QUITS"
msg_bye db "\nThanks for playing snake.\n"

bx: resb 256				; the snake, a ring of cells: bx/by[tl..hd]
by: resb 256
hd: resb 1
tl: resb 1
dir: resb 1					; 0 right, 1 down, 2 left, 3 up
grow: resb 1
score: resb 1
seed: resb 1
cx: resb 1
cy: resb 1
col: resb 1
size: resb 1
nx: resb 1
ny: resb 1
num: resb 1
dig: resb 1
k: resb 1
; the card's geometry and colours (set in main)
eink: resb 1				; 1 on the e-ink card
fw: resb 1					; the field's width in cells (its height is 30)
cs: resb 1					; a cell's size in pixels
ps: resb 1					; a piece's (snake, food) size in pixels
x0: resb 1					; e-ink: the field's left edge on the panel
ccl: resb 1					; the field's centre x, for the texts
cch: resb 1
c_bg: resb 1
c_wall: resb 1
c_snake: resb 1
c_food: resb 1
ring: resb 1				; e-ink: 1 draws the cell's outline, not a fill
txl: resb 1					; text: x, and y (HDMI's; e-ink's is twice it)
txh: resb 1
ty: resb 1
tpl: resb 1					; text: the string
tph: resb 1
auto: resb 6				; e-ink: the refresh policy as the game found it
gxy: resb 4					; getpixel2's x16, y16
ins: resb 1					; cell's inset

main:
	; a seed from the millisecond clock
	push pch
	push pcl
	b API_TICKS
	ld r0, $6f00
	st [seed], r0

	; which card: mode 2 is the e-ink card's (HDMI answers $ff, sends nothing)
	xor r0, r0
	st [eink], r0
	st [x0], r0
	st [ring], r0
	st [cch], r0
	mov r0, #2
	push pch
	push pcl
	b API_GFX_MODE
	eq r0, #0
	bzf .eink
	; HDMI: GFX mode's 320 x 240
	mov r0, #40
	st [fw], r0
	mov r0, #8
	st [cs], r0
	mov r0, #7
	st [ps], r0
	mov r0, #160
	st [ccl], r0
	mov r0, #BLACK
	st [c_bg], r0
	mov r0, #WALL
	st [c_wall], r0
	mov r0, #SNAKE
	st [c_snake], r0
	mov r0, #FOOD
	st [c_food], r0
	b new_game
.eink:
	mov r0, #1
	st [eink], r0
	mov r0, #16
	st [cs], r0
	mov r0, #14
	st [ps], r0
	mov r0, #3
	st [c_bg], r0
	mov r0, #1
	st [c_wall], r0
	xor r0, r0
	st [c_snake], r0
	mov r0, #2
	st [c_food], r0
	; the panel's width: (700, 0) is white on the 800 x 480 panel, off the
	; 648 x 480 one (GETPIXEL2 gives 0 there)
	mov r0, #0xbc				; 700 = $2bc
	st $6f00, r0
	mov r0, #2
	st $6f01, r0
	xor r0, r0
	st $6f02, r0
	st $6f03, r0
	push pch
	push pcl
	b getpixel2
	eq r1, #3
	bzf .wide
	mov r0, #40					; 648 wide- 40 cells, 4 pixels in, centre 324
	st [fw], r0
	mov r0, #4
	st [x0], r0
	mov r0, #0x44
	st [ccl], r0
	mov r0, #1
	st [cch], r0
	b .auto
.wide:
	mov r0, #50					; 800 wide- 50 cells, centre 400
	st [fw], r0
	mov r0, #0x90
	st [ccl], r0
	mov r0, #1
	st [cch], r0
	; the automatic refresh off while the game runs (it refreshes itself)
.auto:
	push pch
	push pcl
	b API_EINK_GET
	mov r1, #6
.save:
	eq r1, #0
	bzf .off
	sub r1, #1
	ld r0, $6f00+r1
	st [auto]+r1, r0
	b .save
.off:
	xor r0, r0
	st $6f00, r0				; on 0, the rest as they were
	push pch
	push pcl
	b API_EINK_AUTO

new_game:
	ld r0, [eink]
	add r0, #1					; mode 1 GFX (cleared to black), or 2 (to white)
	push pch
	push pcl
	b API_GFX_MODE

	; the walls
	ld r0, [c_wall]
	st [col], r0
	ld r0, [cs]
	st [size], r0
	xor r0, r0
	st [k], r0
.wall_x:
	ld r0, [k]
	st [cx], r0
	xor r0, r0
	st [cy], r0
	push pch
	push pcl
	b cell
	mov r0, #29
	st [cy], r0
	push pch
	push pcl
	b cell
	ld r0, [k]
	add r0, #1
	st [k], r0
	ld r1, [fw]
	eq r0, r1
	bzf .walls_y
	b .wall_x
.walls_y:
	mov r0, #1
	st [k], r0
.wall_y:
	ld r0, [k]
	st [cy], r0
	xor r0, r0
	st [cx], r0
	push pch
	push pcl
	b cell
	ld r0, [fw]
	sub r0, #1
	st [cx], r0
	push pch
	push pcl
	b cell
	ld r0, [k]
	add r0, #1
	st [k], r0
	eq r0, #29
	bzf .snake
	b .wall_y

	; the snake- three cells at (10..12, 15), heading right
.snake:
	ld r0, [c_snake]
	st [col], r0
	ld r0, [ps]
	st [size], r0
	xor r0, r0
	st [tl], r0
	st [dir], r0
	st [score], r0
	st [grow], r0
	mov r0, #2
	st [hd], r0
	xor r0, r0
	st [k], r0
.body:
	ld r0, [k]
	add r0, #10
	st [cx], r0
	mov r1, r0
	ld r0, [k]
	st [bx]+r0, r1
	mov r1, #15
	st [by]+r0, r1
	mov r0, #15
	st [cy], r0
	push pch
	push pcl
	b cell
	ld r0, [k]
	add r0, #1
	st [k], r0
	eq r0, #3
	bzf .ready
	b .body
.ready:
	push pch
	push pcl
	b place_food
	push pch
	push pcl
	b show_score
	ld r0, [eink]
	eq r0, #0
	bzf tick
	mov r0, #3					; e-ink- the field in its four greys
	push pch
	push pcl
	b API_EINK_REFRESH

	; ------------------------------------------------------------ the game
tick:
	ld r0, [eink]
	eq r0, #0
	bzf .hdmi
	xor r0, r0					; e-ink- a partial refresh shows the move
	push pch
	push pcl
	b API_EINK_REFRESH
	mov r0, #EINK_STEP_LO
	mov r1, #EINK_STEP_HI
	b .wait
.hdmi:
	mov r0, #STEP_MS
	xor r1, r1
.wait:
	push pch
	push pcl
	b API_WAIT_MS
	push pch
	push pcl
	b API_POLLKEY
	push pch
	push pcl
	b steer
	eq r0, #1					; Q
	bzf quit

	; the next cell from the head
	ld r0, [hd]
	ld r1, [bx]+r0
	st [nx], r1
	ld r1, [by]+r0
	st [ny], r1
	ld r0, [dir]
	eq r0, #0
	bzf .right
	eq r0, #1
	bzf .down
	eq r0, #2
	bzf .left
	ld r0, [ny]					; up
	sub r0, #1
	st [ny], r0
	b .look
.right:
	ld r0, [nx]
	add r0, #1
	st [nx], r0
	b .look
.down:
	ld r0, [ny]
	add r0, #1
	st [ny], r0
	b .look
.left:
	ld r0, [nx]
	sub r0, #1
	st [nx], r0

	; what is there
.look:
	ld r0, [nx]
	st [cx], r0
	ld r0, [ny]
	st [cy], r0
	push pch
	push pcl
	b cell_colour
	ld r0, [c_wall]
	eq r1, r0
	bzf game_over
	ld r0, [c_snake]
	eq r1, r0
	bzf game_over
	ld r0, [c_food]
	eq r1, r0
	bzf .eat
	b .move
.eat:
	mov r0, #1
	st [grow], r0

	; the head moves on
.move:
	ld r0, [hd]
	add r0, #1
	st [hd], r0
	ld r1, [nx]
	st [bx]+r0, r1
	ld r1, [ny]
	st [by]+r0, r1
	ld r0, [c_snake]
	st [col], r0
	ld r0, [ps]
	st [size], r0
	push pch
	push pcl
	b cell

	ld r0, [grow]
	eq r0, #0
	bzf .tail
	xor r0, r0
	st [grow], r0
	ld r0, [score]
	add r0, #1
	st [score], r0
	push pch
	push pcl
	b show_score
	push pch
	push pcl
	b place_food
	b tick

	; the tail follows
.tail:
	ld r0, [tl]
	ld r1, [bx]+r0
	st [cx], r1
	ld r1, [by]+r0
	st [cy], r1
	ld r0, [c_bg]
	st [col], r0
	push pch
	push pcl
	b cell
	ld r0, [tl]
	add r0, #1
	st [tl], r0
	b tick

	; ------------------------------------------------------------ the end
game_over:
	mov r0, #104
	st [ty], r0
	mov r0, #<[msg_over]
	mov r1, #>[msg_over]
	push pch
	push pcl
	b say
	mov r0, #116
	st [ty], r0
	mov r0, #<[score_txt]
	mov r1, #>[score_txt]
	push pch
	push pcl
	b say
	mov r0, #132
	st [ty], r0
	mov r0, #<[msg_again]
	mov r1, #>[msg_again]
	push pch
	push pcl
	b say
	ld r0, [eink]
	eq r0, #0
	bzf .wait
	xor r0, r0
	push pch
	push pcl
	b API_EINK_REFRESH
.wait:
	push pch
	push pcl
	b API_GETKEY
	eq r0, #32
	bzf new_game
	eq r0, #113					; q
	bzf quit
	eq r0, #81					; Q
	bzf quit
	b .wait

quit:
	ld r0, [eink]
	eq r0, #0
	bzf .text
	mov r1, #6					; e-ink- the refresh policy back as it was
.restore:
	eq r1, #0
	bzf .put
	sub r1, #1
	ld r0, [auto]+r1
	st $6f00+r1, r0
	b .restore
.put:
	push pch
	push pcl
	b API_EINK_AUTO
.text:
	xor r0, r0
	push pch
	push pcl
	b API_GFX_MODE
	mov r0, #7
	push pch
	push pcl
	b API_CLS
	mov r0, #<[msg_bye]
	mov r1, #>[msg_bye]
	st $6f00, r0
	st $6f01, r1
	push pch
	push pcl
	b API_PUTS
	pop pcl
	pop pch

	; ------------------------------------------------------------ helpers

; turn by the key in r0 (never straight back); r0 = 1 for Q, else 0
steer:
	st [k], r0
	eq r0, #113					; q
	bzf .quit
	eq r0, #81					; Q
	bzf .quit
	eq r0, #100					; d
	bzf .r
	eq r0, #131					; right arrow
	bzf .r
	eq r0, #115					; s
	bzf .d
	eq r0, #129					; down arrow
	bzf .d
	eq r0, #97					; a
	bzf .l
	eq r0, #130					; left arrow
	bzf .l
	eq r0, #119					; w
	bzf .u
	eq r0, #128					; up arrow
	bzf .u
	b .none
.r:
	ld r0, [dir]
	eq r0, #2
	bzf .none
	xor r0, r0
	b .set
.d:
	ld r0, [dir]
	eq r0, #3
	bzf .none
	mov r0, #1
	b .set
.l:
	ld r0, [dir]
	eq r0, #0
	bzf .none
	mov r0, #2
	b .set
.u:
	ld r0, [dir]
	eq r0, #1
	bzf .none
	mov r0, #3
.set:
	st [dir], r0
.none:
	xor r0, r0
	pop pcl
	pop pch
.quit:
	mov r0, #1
	pop pcl
	pop pch

; fill cell (cx, cy) with col, size x size pixels: from its top left on
; HDMI; centred in it on e-ink (an outline instead with ring set)
cell:
	ld r0, [eink]
	eq r0, #0
	bzf .hdmi
	ld r0, [cs]					; the inset, (cs - size) / 2
	ld r1, [size]
	sub r0, r1
	shr r0, #1
	st [ins], r0
	ld r0, [cx]					; x = x0 + 16 cx + inset, the low byte of
	shl r0, #4					; 16 cx is a multiple of 16, so no carry
	ld r1, [x0]
	add r0, r1
	ld r1, [ins]
	add r0, r1
	st $6f00, r0
	ld r0, [cx]
	shr r0, #4
	st $6f01, r0
	ld r0, [cy]					; y = 16 cy + inset
	shl r0, #4
	ld r1, [ins]
	add r0, r1
	st $6f02, r0
	ld r0, [cy]
	shr r0, #4
	st $6f03, r0
	ld r0, [size]
	st $6f04, r0
	st $6f06, r0
	xor r0, r0
	st $6f05, r0
	st $6f07, r0
	ld r0, [col]
	st $6f08, r0
	ld r0, [ring]
	eq r0, #0
	bzf .fill2
	push pch
	push pcl
	b API_GFX2_RECT
	pop pcl
	pop pch
.fill2:
	push pch
	push pcl
	b API_GFX2_FILL_RECT
	pop pcl
	pop pch
.hdmi:
	ld r0, [cx]
	shl r0, #3
	st $6f00, r0				; x low
	xor r1, r1
	ld r0, [cx]
	gt r0, #31
	bzf .hi
	b .x_done
.hi:
	mov r1, #1
.x_done:
	st $6f01, r1				; x high
	ld r0, [cy]
	shl r0, #3
	st $6f02, r0
	ld r0, [size]
	st $6f03, r0
	xor r0, r0
	st $6f04, r0
	ld r0, [size]
	st $6f05, r0
	ld r0, [col]
	st $6f06, r0
	push pch
	push pcl
	b API_GFX_FILL_RECT
	pop pcl
	pop pch

; r1 = the colour in cell (cx, cy): the pixel 3, 3 into it on HDMI, its
; centre on e-ink
cell_colour:
	ld r0, [eink]
	eq r0, #0
	bzf .hdmi
	ld r0, [cx]
	shl r0, #4
	ld r1, [x0]
	add r0, r1
	add r0, #8
	st $6f00, r0
	ld r0, [cx]
	shr r0, #4
	st $6f01, r0
	ld r0, [cy]
	shl r0, #4
	add r0, #8
	st $6f02, r0
	ld r0, [cy]
	shr r0, #4
	st $6f03, r0
	b getpixel2
.hdmi:
	ld r0, [cx]
	shl r0, #3
	add r0, #3
	st $6f00, r0
	xor r1, r1
	ld r0, [cx]
	gt r0, #31
	bzf .hi
	b .x_done
.hi:
	mov r1, #1
.x_done:
	st $6f01, r1
	ld r0, [cy]
	shl r0, #3
	add r0, #3
	st $6f02, r0
	push pch
	push pcl
	b API_GFX_GETPIXEL
	pop pcl
	pop pch

; r1 = the grey at API_ARGS[0..3] (x16, y16). The card answers once it has
; run everything before, so not while the refresh it was asked for holds
; it: ask again until it answers.
getpixel2:
	mov r1, #4
.keep:
	eq r1, #0
	bzf .ask
	sub r1, #1
	ld r0, $6f00+r1
	st [gxy]+r1, r0
	b .keep
.ask:
	mov r1, #4
.put:
	eq r1, #0
	bzf .call
	sub r1, #1
	ld r0, [gxy]+r1
	st $6f00+r1, r0
	b .put
.call:
	push pch
	push pcl
	b API_GFX2_GETPIXEL
	eq r0, #0
	bzf .got
	b .ask
.got:
	pop pcl
	pop pch

; food in a free cell inside the walls
place_food:
	push pch
	push pcl
	b rand
	ld r1, [fw]
	sub r1, #2
	push pch
	push pcl
	b modulo
	add r0, #1
	st [cx], r0
	push pch
	push pcl
	b rand
	mov r1, #28
	push pch
	push pcl
	b modulo
	add r0, #1
	st [cy], r0
	push pch
	push pcl
	b cell_colour
	ld r0, [c_bg]
	eq r1, r0
	bzf .free
	b place_food
.free:
	ld r0, [c_food]
	st [col], r0
	ld r0, [ps]
	st [size], r0
	push pch
	push pcl
	b cell
	ld r0, [eink]
	eq r0, #0
	bzf .done
	mov r0, #1					; e-ink- a black ring round it
	st [ring], r0
	xor r0, r0
	st [col], r0
	push pch
	push pcl
	b cell
	xor r0, r0
	st [ring], r0
.done:
	pop pcl
	pop pch

; r0 = the next random byte (seed * 5 + 1)
rand:
	ld r0, [seed]
	mov r1, r0
	shl r0, #2
	add r0, r1
	add r0, #1
	st [seed], r0
	pop pcl
	pop pch

; r0 = r0 mod r1
modulo:
	st [k], r1
.again:
	ld r1, [k]
	lt r0, r1
	bzf .done
	sub r0, r1
	b .again
.done:
	pop pcl
	pop pch

; the score into score_txt, then at the top left over the wall
show_score:
	ld r0, [score]
	st [num], r0
	mov r1, #6
	push pch
	push pcl
	b digit_100
	mov r1, #7
	push pch
	push pcl
	b digit_10
	ld r1, [num]
	add r1, #48
	mov r0, #8
	st [score_txt]+r0, r1
	ld r0, [x0]					; x 8 on HDMI, a cell in on e-ink
	ld r1, [cs]
	add r0, r1
	st [txl], r0
	xor r0, r0
	st [txh], r0
	st [ty], r0
	mov r0, #<[score_txt]
	mov r1, #>[score_txt]
	push pch
	push pcl
	b text
	pop pcl
	pop pch

; the hundreds of num into score_txt[r1], num keeps the rest
digit_100:
	mov r0, #48
	st [dig], r0
.h:
	ld r0, [num]
	gt r0, #99
	bzf .sub
	b .out
.sub:
	sub r0, #100
	st [num], r0
	ld r0, [dig]
	add r0, #1
	st [dig], r0
	b .h
.out:
	mov r0, r1
	ld r1, [dig]
	st [score_txt]+r0, r1
	pop pcl
	pop pch

; the tens of num into score_txt[r1], num keeps the rest
digit_10:
	mov r0, #48
	st [dig], r0
.t:
	ld r0, [num]
	gt r0, #9
	bzf .sub
	b .out
.sub:
	sub r0, #10
	st [num], r0
	ld r0, [dig]
	add r0, #1
	st [dig], r0
	b .t
.out:
	mov r0, r1
	ld r1, [dig]
	st [score_txt]+r0, r1
	pop pcl
	pop pch

; the NUL-terminated string at r1 (high), r0 (low), centred on the field at
; row ty: x = the centre - 4 x its length
say:
	st [tpl], r0
	st [tph], r1
	xor r1, r1					; its length x 4
.len:
	ldd r0, [tpl]+r1
	eq r0, #0
	bzf .x
	add r1, #1
	b .len
.x:
	shl r1, #2
	ld r0, [ccl]
	lt r0, r1					; the low byte borrows
	sub r0, r1
	st [txl], r0
	ld r0, [cch]
	bzf .borrow
	b .hi
.borrow:
	sub r0, #1
.hi:
	st [txh], r0
	ld r0, [tpl]
	ld r1, [tph]
; the string at r1 (high), r0 (low) at txh:txl, ty: white on the wall colour
; in 8 x 8 on HDMI; white on black in 8 x 16 on e-ink, at y = 2 ty
text:
	st [tpl], r0
	st [tph], r1
	ld r0, [txl]
	st $6f00, r0
	ld r0, [txh]
	st $6f01, r0
	ld r0, [eink]
	eq r0, #0
	bzf .hdmi
	ld r0, [ty]
	shl r0, #1
	st $6f02, r0
	ld r0, [ty]
	shr r0, #7
	st $6f03, r0
	mov r0, #3
	st $6f04, r0
	xor r0, r0
	st $6f05, r0
	ld r0, [tpl]
	st $6f07, r0
	ld r0, [tph]
	st $6f08, r0
	push pch
	push pcl
	b API_GFX2_TEXT16
	pop pcl
	pop pch
.hdmi:
	ld r0, [ty]
	st $6f02, r0
	mov r0, #WHITE
	st $6f03, r0
	mov r0, #WALL
	st $6f04, r0
	ld r0, [tpl]
	st $6f06, r0
	ld r0, [tph]
	st $6f07, r0
	push pch
	push pcl
	b API_GFX_TEXT8
	pop pcl
	pop pch
