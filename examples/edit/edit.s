; edit- a full-screen text editor, a user program for the kernel API
; (doc/proposals/kernel-api.md).
;
; Asks for a file name (8.3), loads the file from the SD card (or starts a
; new one), and edits it on the 80 x 30 text screen: row 0 the status, rows
; 1-28 the text, row 29 the keys. Type to insert; Enter, Backspace, Delete;
; the arrows, Home, End, PgUp, PgDn move; F2 saves; Esc quits (twice when
; there are unsaved changes). Lines longer than the screen scroll sideways.
;
; Both graphics cards: only the console API, the attributes $07 and $70, and
; a CLS only at the start and the end (on e-paper a CLS is a full refresh).
; The e-ink card refreshes the rows that changed by itself.
;
; The text is a gap buffer at $8000-$bfff (16 KB; BASIC's program at
; $c000-$dfff is left alone): the text before the cursor from $8000 to
; gap_s, the text after it from gap_e to $bfff. A file bigger than that is
; not opened. The file's CR LF line ends are LF inside, and CR LF again on
; the card.
;
; Build- the API's names (kernel/api.inc) first, then this, for $7000:
;   python3 tools/mkprg.py examples/edit/edit.s -o build/EDIT.PRG
; Run- exec "EDIT.PRG" from the SD card.

%define BUF_HI 0x80
%define END_HI 0xc0
%define ROWS 28
%define FILE_H 1
%define ATTR_TEXT 0x07
%define ATTR_BAR 0x70

s_ask db "\nEDIT- file name: "
s_badname db "\nedit: a name of 8.3 (up to 12 characters)\n"
s_big db "\nedit: the file is bigger than 16 KB\n"
s_title db " EDIT "
s_mod db " *"
s_line db "  line "
s_col db " col "
s_keys db " F2 save   Esc quit   arrows Home End PgUp PgDn move"
s_new db "  new file"
s_saved db "  saved"
s_nosave db "  save failed"
s_full db "  no room left"
s_sure db "  unsaved! Esc quits, F2 saves"
pw db 16, 39, 232, 3, 100, 0, 10, 0, 1, 0

fname: resb 80
gap_s: resb 2			; the gap: the cursor is at gap_s
gap_e: resb 2
cur_line: resb 2		; the cursor's line, from 0
cur_col: resb 2			; its column, from 0 (calc_col)
line_st: resb 2			; where its line starts (calc_col)
want_col: resb 2		; the column up and down aim for
top_p: resb 2			; the first text row's line (before the gap)
top_line: resb 2
left_col: resb 2		; the text column at screen column 0
rd_p: resb 2			; rd_next's place
count: resb 2
ua: resb 2			; cmp16, sub16, print_dec
ub: resb 2
vp: resb 2			; inc16, dec16
msg: resb 2			; a message for the status line, or 0
ch: resb 1
row: resb 1
rown: resb 1
redraw: resb 1			; 0 none, 1 the cursor's row, 2 the screen
modified: resb 1
vert: resb 1			; the last key moved up or down
confirm: resb 1			; Esc once with unsaved changes
lead: resb 1
dig: resb 1
pwi: resb 1
key: resb 1
pgn: resb 1
io_n: resb 1
io_i: resb 1
io_err: resb 1
rowbuf: resb 81
iobuf: resb 130

main:
	mov r0, #<[s_ask]
	mov r1, #>[s_ask]
	push pch
	push pcl
	b puts
	mov r0, #<[fname]
	st $6f00, r0
	mov r0, #>[fname]
	st $6f01, r0
	push pch
	push pcl
	b API_READLINE
	eq r1, #0
	bzf .out
	gt r1, #12
	bzf .badname
	xor r0, r0
	st [fname]+r1, r0		; the CR after the name ends it

	push pch
	push pcl
	b load
	eq r0, #0
	bzf .loaded
	mov r0, #<[s_big]
	mov r1, #>[s_big]
	push pch
	push pcl
	b puts
.out:
	pop pcl
	pop pch
.badname:
	mov r0, #<[s_badname]
	mov r1, #>[s_badname]
	push pch
	push pcl
	b puts
	pop pcl
	pop pch

.loaded:
	xor r0, r0
	st [top_line], r0
	st [top_line+1], r0
	st [left_col], r0
	st [left_col+1], r0
	st [modified], r0
	st [vert], r0
	st [confirm], r0
	st [top_p], r0
	mov r0, #BUF_HI
	st [top_p+1], r0
	mov r0, #ATTR_TEXT
	push pch
	push pcl
	b API_ATTR
	mov r0, #ATTR_TEXT
	push pch
	push pcl
	b API_CLS
	push pch
	push pcl
	b draw_keys
	mov r0, #2
	st [redraw], r0

.loop:
	push pch
	push pcl
	b calc_col
	ld r0, [vert]
	eq r0, #0
	bzf .want
	b .adjust
.want:
	ld r0, [cur_col]
	st [want_col], r0
	ld r0, [cur_col+1]
	st [want_col+1], r0
.adjust:
	push pch
	push pcl
	b adjust_left
	push pch
	push pcl
	b adjust_top
	ld r0, [redraw]
	eq r0, #2
	bzf .full
	eq r0, #1
	bzf .one
	b .status
.full:
	push pch
	push pcl
	b draw_all
	b .status
.one:
	push pch
	push pcl
	b draw_cur
.status:
	push pch
	push pcl
	b draw_status

	; the cursor: column cur_col - left_col, row cur_line - top_line + 1
	ld r0, [cur_col]
	st [ua], r0
	ld r0, [cur_col+1]
	st [ua+1], r0
	ld r0, [left_col]
	st [ub], r0
	ld r0, [left_col+1]
	st [ub+1], r0
	push pch
	push pcl
	b sub16
	ld r0, [cur_line]
	ld r1, [top_line]
	sub r0, r1
	add r0, #1
	mov r1, r0
	ld r0, [ua]
	push pch
	push pcl
	b API_GOTOXY

	push pch
	push pcl
	b API_GETKEY
	st [key], r0
	xor r0, r0
	st [redraw], r0
	st [vert], r0
	st [msg], r0
	st [msg+1], r0
	ld r0, [confirm]
	eq r0, #0
	bzf .dispatch
	xor r0, r0
	st [confirm], r0
	ld r0, [key]
	eq r0, #27
	bzf .quit

.dispatch:
	ld r0, [key]
	eq r0, #27
	bzf .esc
	eq r0, #0x92
	bzf .save
	eq r0, #13
	bzf .enter
	eq r0, #8
	bzf .bs
	eq r0, #0x7f
	bzf .del
	eq r0, #0x80
	bzf .up
	eq r0, #0x81
	bzf .down
	eq r0, #0x82
	bzf .left
	eq r0, #0x83
	bzf .right
	eq r0, #0x84
	bzf .home
	eq r0, #0x85
	bzf .end
	eq r0, #0x86
	bzf .pgup
	eq r0, #0x87
	bzf .pgdn
	eq r0, #9
	bzf .ins
	lt r0, #32
	bzf .loop
	gt r0, #126
	bzf .loop
.ins:
	push pch
	push pcl
	b insert
	eq r0, #0
	bzf .full_buf
	mov r0, #1
	st [modified], r0
	st [redraw], r0
	b .loop
.enter:
	mov r0, #10
	push pch
	push pcl
	b insert
	eq r0, #0
	bzf .full_buf
	mov r0, #1
	st [modified], r0
	mov r0, #2
	st [redraw], r0
	b .loop
.full_buf:
	mov r0, #<[s_full]
	st [msg], r0
	mov r0, #>[s_full]
	st [msg+1], r0
	b .loop
.bs:
	push pch
	push pcl
	b backspace
	b .edited
.del:
	push pch
	push pcl
	b delete
.edited:
	st [redraw], r0
	eq r0, #0
	bzf .loop
	mov r0, #1
	st [modified], r0
	b .loop
.left:
	push pch
	push pcl
	b move_left
	b .loop
.right:
	push pch
	push pcl
	b move_right
	b .loop
.home:
	ld r0, [cur_col]
	st [count], r0
	ld r0, [cur_col+1]
	st [count+1], r0
	push pch
	push pcl
	b left_n
	b .loop
.end:
	push pch
	push pcl
	b go_end
	b .loop
.up:
	mov r0, #1
	st [vert], r0
	push pch
	push pcl
	b go_up
	b .loop
.down:
	mov r0, #1
	st [vert], r0
	push pch
	push pcl
	b go_down
	b .loop
.pgup:
	mov r0, #1
	st [vert], r0
	mov r0, #27
	st [pgn], r0
.pgup_n:
	push pch
	push pcl
	b go_up
	ld r0, [pgn]
	sub r0, #1
	st [pgn], r0
	eq r0, #0
	bzf .loop
	b .pgup_n
.pgdn:
	mov r0, #1
	st [vert], r0
	mov r0, #27
	st [pgn], r0
.pgdn_n:
	push pch
	push pcl
	b go_down
	ld r0, [pgn]
	sub r0, #1
	st [pgn], r0
	eq r0, #0
	bzf .loop
	b .pgdn_n
.save:
	push pch
	push pcl
	b save
	b .loop
.esc:
	ld r0, [modified]
	eq r0, #0
	bzf .quit
	mov r0, #1
	st [confirm], r0
	mov r0, #<[s_sure]
	st [msg], r0
	mov r0, #>[s_sure]
	st [msg+1], r0
	b .loop
.quit:
	mov r0, #ATTR_TEXT
	push pch
	push pcl
	b API_ATTR
	mov r0, #ATTR_TEXT
	push pch
	push pcl
	b API_CLS
	pop pcl
	pop pch

; ------------------------------------------------------------ the gap buffer

; the cursor left one (the byte before the gap to after it)
move_left:
	ld r0, [gap_s]
	eq r0, #0
	bzf .lo0
	b .go
.lo0:
	ld r0, [gap_s+1]
	eq r0, #BUF_HI
	bzf .no
.go:
	mov r0, #<[gap_s]
	mov r1, #>[gap_s]
	push pch
	push pcl
	b dec16
	mov r0, #<[gap_e]
	mov r1, #>[gap_e]
	push pch
	push pcl
	b dec16
	ldd r0, [gap_s]
	std [gap_e], r0
	eq r0, #10
	bzf .lf
	pop pcl
	pop pch
.lf:
	mov r0, #<[cur_line]
	mov r1, #>[cur_line]
	push pch
	push pcl
	b dec16
.no:
	pop pcl
	pop pch

; the cursor right one (the byte after the gap to before it)
move_right:
	ld r0, [gap_e]
	eq r0, #0
	bzf .lo0
	b .go
.lo0:
	ld r0, [gap_e+1]
	eq r0, #END_HI
	bzf .no
.go:
	ldd r0, [gap_e]
	std [gap_s], r0
	st [ch], r0
	mov r0, #<[gap_s]
	mov r1, #>[gap_s]
	push pch
	push pcl
	b inc16
	mov r0, #<[gap_e]
	mov r1, #>[gap_e]
	push pch
	push pcl
	b inc16
	ld r0, [ch]
	eq r0, #10
	bzf .lf
	pop pcl
	pop pch
.lf:
	mov r0, #<[cur_line]
	mov r1, #>[cur_line]
	push pch
	push pcl
	b inc16
.no:
	pop pcl
	pop pch

; byte r0 in at the cursor; r0 = 1, or 0 when the gap is used up
insert:
	st [ch], r0
	ld r0, [gap_s]
	ld r1, [gap_e]
	eq r0, r1
	bzf .lo_eq
	b .room
.lo_eq:
	ld r0, [gap_s+1]
	ld r1, [gap_e+1]
	eq r0, r1
	bzf .full
.room:
	ld r0, [ch]
	std [gap_s], r0
	mov r0, #<[gap_s]
	mov r1, #>[gap_s]
	push pch
	push pcl
	b inc16
	ld r0, [ch]
	eq r0, #10
	bzf .lf
	mov r0, #1
	pop pcl
	pop pch
.lf:
	mov r0, #<[cur_line]
	mov r1, #>[cur_line]
	push pch
	push pcl
	b inc16
	mov r0, #1
	pop pcl
	pop pch
.full:
	xor r0, r0
	pop pcl
	pop pch

; the byte before the cursor out; r0 = what to redraw (0, 1 the row, 2 all)
backspace:
	ld r0, [gap_s]
	eq r0, #0
	bzf .lo0
	b .go
.lo0:
	ld r0, [gap_s+1]
	eq r0, #BUF_HI
	bzf .no
.go:
	mov r0, #<[gap_s]
	mov r1, #>[gap_s]
	push pch
	push pcl
	b dec16
	ldd r0, [gap_s]
	eq r0, #10
	bzf .lf
	mov r0, #1
	pop pcl
	pop pch
.lf:
	mov r0, #<[cur_line]
	mov r1, #>[cur_line]
	push pch
	push pcl
	b dec16
	mov r0, #2
	pop pcl
	pop pch
.no:
	xor r0, r0
	pop pcl
	pop pch

; the byte after the cursor out; r0 as backspace's
delete:
	ld r0, [gap_e]
	eq r0, #0
	bzf .lo0
	b .go
.lo0:
	ld r0, [gap_e+1]
	eq r0, #END_HI
	bzf .no
.go:
	ldd r0, [gap_e]
	st [ch], r0
	mov r0, #<[gap_e]
	mov r1, #>[gap_e]
	push pch
	push pcl
	b inc16
	ld r0, [ch]
	eq r0, #10
	bzf .lf
	mov r0, #1
	pop pcl
	pop pch
.lf:
	mov r0, #2
	pop pcl
	pop pch
.no:
	xor r0, r0
	pop pcl
	pop pch

; cur_col = the cursor's column, line_st = where its line starts
calc_col:
	ld r0, [gap_s]
	st [line_st], r0
	ld r0, [gap_s+1]
	st [line_st+1], r0
	xor r0, r0
	st [cur_col], r0
	st [cur_col+1], r0
.loop:
	ld r0, [line_st]
	eq r0, #0
	bzf .lo0
	b .dec
.lo0:
	ld r0, [line_st+1]
	eq r0, #BUF_HI
	bzf .done
.dec:
	mov r0, #<[line_st]
	mov r1, #>[line_st]
	push pch
	push pcl
	b dec16
	ldd r0, [line_st]
	eq r0, #10
	bzf .lf
	mov r0, #<[cur_col]
	mov r1, #>[cur_col]
	push pch
	push pcl
	b inc16
	b .loop
.lf:
	mov r0, #<[line_st]
	mov r1, #>[line_st]
	push pch
	push pcl
	b inc16
.done:
	pop pcl
	pop pch

; left count times (to the text's start at most)
left_n:
	ld r0, [count]
	ld r1, [count+1]
	or r0, r1
	eq r0, #0
	bzf .done
	push pch
	push pcl
	b move_left
	mov r0, #<[count]
	mov r1, #>[count]
	push pch
	push pcl
	b dec16
	b left_n
.done:
	pop pcl
	pop pch

; right count times, stopping at the line's end
right_upto:
	ld r0, [count]
	ld r1, [count+1]
	or r0, r1
	eq r0, #0
	bzf .done
	ld r0, [gap_e]
	eq r0, #0
	bzf .lo0
	b .peek
.lo0:
	ld r0, [gap_e+1]
	eq r0, #END_HI
	bzf .done
.peek:
	ldd r0, [gap_e]
	eq r0, #10
	bzf .done
	push pch
	push pcl
	b move_right
	mov r0, #<[count]
	mov r1, #>[count]
	push pch
	push pcl
	b dec16
	b right_upto
.done:
	pop pcl
	pop pch

go_end:
	mov r0, #0xff
	st [count], r0
	st [count+1], r0
	push pch
	push pcl
	b right_upto
	pop pcl
	pop pch

; up a line, to want_col or the line's end
go_up:
	ld r0, [cur_line]
	ld r1, [cur_line+1]
	or r0, r1
	eq r0, #0
	bzf .done
	push pch
	push pcl
	b calc_col
	; the column and the LF before it: the end of the line above
	ld r0, [cur_col]
	st [count], r0
	ld r0, [cur_col+1]
	st [count+1], r0
	mov r0, #<[count]
	mov r1, #>[count]
	push pch
	push pcl
	b inc16
	push pch
	push pcl
	b left_n
	push pch
	push pcl
	b calc_col
	; its length past want_col, left
	ld r0, [cur_col]
	st [ua], r0
	ld r0, [cur_col+1]
	st [ua+1], r0
	ld r0, [want_col]
	st [ub], r0
	ld r0, [want_col+1]
	st [ub+1], r0
	push pch
	push pcl
	b cmp16
	eq r0, #1
	bzf .back
	b .done
.back:
	push pch
	push pcl
	b sub16
	ld r0, [ua]
	st [count], r0
	ld r0, [ua+1]
	st [count+1], r0
	push pch
	push pcl
	b left_n
.done:
	pop pcl
	pop pch

; down a line, to want_col or the line's end (the last line: to its end)
go_down:
	push pch
	push pcl
	b go_end
	ld r0, [gap_e]
	eq r0, #0
	bzf .lo0
	b .next
.lo0:
	ld r0, [gap_e+1]
	eq r0, #END_HI
	bzf .done
.next:
	push pch
	push pcl
	b move_right
	ld r0, [want_col]
	st [count], r0
	ld r0, [want_col+1]
	st [count+1], r0
	push pch
	push pcl
	b right_upto
.done:
	pop pcl
	pop pch

; ------------------------------------------------------------ the screen

; left_col so the cursor's column is on the screen
adjust_left:
	ld r0, [cur_col]
	st [ua], r0
	ld r0, [cur_col+1]
	st [ua+1], r0
	ld r0, [left_col]
	st [ub], r0
	ld r0, [left_col+1]
	st [ub+1], r0
	push pch
	push pcl
	b cmp16
	eq r0, #0xff
	bzf .back
	push pch
	push pcl
	b sub16
	ld r0, [ua+1]
	eq r0, #0
	bzf .lo
	b .fwd
.lo:
	ld r0, [ua]
	lt r0, #80
	bzf .done
.fwd:
	; left_col = cur_col - 79
	ld r0, [cur_col]
	st [ua], r0
	ld r0, [cur_col+1]
	st [ua+1], r0
	mov r0, #79
	st [ub], r0
	xor r0, r0
	st [ub+1], r0
	push pch
	push pcl
	b sub16
	ld r0, [ua]
	st [left_col], r0
	ld r0, [ua+1]
	st [left_col+1], r0
	b .moved
.back:
	ld r0, [cur_col]
	st [left_col], r0
	ld r0, [cur_col+1]
	st [left_col+1], r0
.moved:
	mov r0, #2
	st [redraw], r0
.done:
	pop pcl
	pop pch

; top_line and top_p so the cursor's line is on the screen
adjust_top:
	ld r0, [cur_line]
	st [ua], r0
	ld r0, [cur_line+1]
	st [ua+1], r0
	ld r0, [top_line]
	st [ub], r0
	ld r0, [top_line+1]
	st [ub+1], r0
	push pch
	push pcl
	b cmp16
	eq r0, #0xff
	bzf .up
	push pch
	push pcl
	b sub16
	ld r0, [ua+1]
	eq r0, #0
	bzf .lo
	b .down
.lo:
	ld r0, [ua]
	lt r0, #ROWS
	bzf .done
.down:
	; the cursor's line on the last row: top_line = cur_line - 27, and
	; top_p 27 lines back from the cursor's line
	ld r0, [cur_line]
	st [ua], r0
	ld r0, [cur_line+1]
	st [ua+1], r0
	mov r0, #27
	st [ub], r0
	xor r0, r0
	st [ub+1], r0
	push pch
	push pcl
	b sub16
	ld r0, [ua]
	st [top_line], r0
	ld r0, [ua+1]
	st [top_line+1], r0
	ld r0, [line_st]
	st [top_p], r0
	ld r0, [line_st+1]
	st [top_p+1], r0
	mov r0, #27
	st [pgn], r0
.back:
	push pch
	push pcl
	b prev_line
	ld r0, [pgn]
	sub r0, #1
	st [pgn], r0
	eq r0, #0
	bzf .moved
	b .back
.up:
	ld r0, [cur_line]
	st [top_line], r0
	ld r0, [cur_line+1]
	st [top_line+1], r0
	ld r0, [line_st]
	st [top_p], r0
	ld r0, [line_st+1]
	st [top_p+1], r0
.moved:
	mov r0, #2
	st [redraw], r0
.done:
	pop pcl
	pop pch

; top_p from a line's start to the start of the line before it
prev_line:
	mov r0, #<[top_p]
	mov r1, #>[top_p]
	push pch
	push pcl
	b dec16
.scan:
	ld r0, [top_p]
	eq r0, #0
	bzf .lo0
	b .dec
.lo0:
	ld r0, [top_p+1]
	eq r0, #BUF_HI
	bzf .done
.dec:
	mov r0, #<[top_p]
	mov r1, #>[top_p]
	push pch
	push pcl
	b dec16
	ldd r0, [top_p]
	eq r0, #10
	bzf .lf
	b .scan
.lf:
	mov r0, #<[top_p]
	mov r1, #>[top_p]
	push pch
	push pcl
	b inc16
.done:
	pop pcl
	pop pch

; rd_p's byte, then on: r0 = it and r1 = 0, or r1 = 1 at the text's end
rd_next:
	ld r0, [rd_p]
	ld r1, [gap_s]
	eq r0, r1
	bzf .lo_eq
	b .end_chk
.lo_eq:
	ld r0, [rd_p+1]
	ld r1, [gap_s+1]
	eq r0, r1
	bzf .jump
	b .end_chk
.jump:
	ld r0, [gap_e]
	st [rd_p], r0
	ld r0, [gap_e+1]
	st [rd_p+1], r0
.end_chk:
	ld r0, [rd_p]
	eq r0, #0
	bzf .lo0
	b .get
.lo0:
	ld r0, [rd_p+1]
	eq r0, #END_HI
	bzf .eof
.get:
	ldd r0, [rd_p]
	st [ch], r0
	mov r0, #<[rd_p]
	mov r1, #>[rd_p]
	push pch
	push pcl
	b inc16
	ld r0, [ch]
	xor r1, r1
	pop pcl
	pop pch
.eof:
	mov r1, #1
	pop pcl
	pop pch

; screen row `row`: the line at rd_p from left_col, 80 columns (rd_p is left
; at the next line)
draw_row:
	xor r0, r0
	ld r1, [row]
	push pch
	push pcl
	b API_GOTOXY
	xor r0, r0
	st [rown], r0
	ld r0, [left_col]
	st [count], r0
	ld r0, [left_col+1]
	st [count+1], r0
.skip:
	ld r0, [count]
	ld r1, [count+1]
	or r0, r1
	eq r0, #0
	bzf .take
	push pch
	push pcl
	b rd_next
	eq r1, #1
	bzf .end
	eq r0, #10
	bzf .end
	mov r0, #<[count]
	mov r1, #>[count]
	push pch
	push pcl
	b dec16
	b .skip
.take:
	push pch
	push pcl
	b rd_next
	eq r1, #1
	bzf .end
	eq r0, #10
	bzf .end
	ld r1, [rown]
	eq r1, #80
	bzf .take			; past the screen's edge
	lt r0, #32
	bzf .ctl
	b .put
.ctl:
	mov r0, #32			; a tab or other control code: a space
.put:
	st [rowbuf]+r1, r0
	add r1, #1
	st [rown], r1
	b .take
.end:
	ld r1, [rown]
	xor r0, r0
	st [rowbuf]+r1, r0
	mov r0, #<[rowbuf]
	mov r1, #>[rowbuf]
	push pch
	push pcl
	b puts
	ld r0, [rown]
	eq r0, #80
	bzf .done
	push pch
	push pcl
	b API_CLEOL
.done:
	pop pcl
	pop pch

; every text row
draw_all:
	ld r0, [top_p]
	st [rd_p], r0
	ld r0, [top_p+1]
	st [rd_p+1], r0
	mov r0, #1
	st [row], r0
.loop:
	push pch
	push pcl
	b draw_row
	ld r0, [row]
	add r0, #1
	st [row], r0
	eq r0, #29
	bzf .done
	b .loop
.done:
	pop pcl
	pop pch

; the cursor's row
draw_cur:
	ld r0, [line_st]
	st [rd_p], r0
	ld r0, [line_st+1]
	st [rd_p+1], r0
	ld r0, [cur_line]
	ld r1, [top_line]
	sub r0, r1
	add r0, #1
	st [row], r0
	push pch
	push pcl
	b draw_row
	pop pcl
	pop pch

; row 0: the name, * when changed, line and column, a message
draw_status:
	xor r0, r0
	xor r1, r1
	push pch
	push pcl
	b API_GOTOXY
	mov r0, #ATTR_BAR
	push pch
	push pcl
	b API_ATTR
	mov r0, #<[s_title]
	mov r1, #>[s_title]
	push pch
	push pcl
	b puts
	mov r0, #<[fname]
	mov r1, #>[fname]
	push pch
	push pcl
	b puts
	ld r0, [modified]
	eq r0, #0
	bzf .where
	mov r0, #<[s_mod]
	mov r1, #>[s_mod]
	push pch
	push pcl
	b puts
.where:
	mov r0, #<[s_line]
	mov r1, #>[s_line]
	push pch
	push pcl
	b puts
	ld r0, [cur_line]
	st [ua], r0
	ld r0, [cur_line+1]
	st [ua+1], r0
	push pch
	push pcl
	b print_dec1
	mov r0, #<[s_col]
	mov r1, #>[s_col]
	push pch
	push pcl
	b puts
	ld r0, [cur_col]
	st [ua], r0
	ld r0, [cur_col+1]
	st [ua+1], r0
	push pch
	push pcl
	b print_dec1
	ld r0, [msg]
	ld r1, [msg+1]
	or r0, r1
	eq r0, #0
	bzf .end
	ld r0, [msg]
	ld r1, [msg+1]
	push pch
	push pcl
	b puts
.end:
	push pch
	push pcl
	b API_CLEOL
	mov r0, #ATTR_TEXT
	push pch
	push pcl
	b API_ATTR
	pop pcl
	pop pch

; row 29: the keys
draw_keys:
	xor r0, r0
	mov r1, #29
	push pch
	push pcl
	b API_GOTOXY
	mov r0, #ATTR_BAR
	push pch
	push pcl
	b API_ATTR
	mov r0, #<[s_keys]
	mov r1, #>[s_keys]
	push pch
	push pcl
	b puts
	push pch
	push pcl
	b API_CLEOL
	mov r0, #ATTR_TEXT
	push pch
	push pcl
	b API_ATTR
	pop pcl
	pop pch

; ua + 1 in decimal, no leading zeros
print_dec1:
	mov r0, #<[ua]
	mov r1, #>[ua]
	push pch
	push pcl
	b inc16
	xor r0, r0
	st [lead], r0
	st [pwi], r0
.digit:
	ld r1, [pwi]
	ld r0, [pw]+r1
	st [ub], r0
	add r1, #1
	ld r0, [pw]+r1
	st [ub+1], r0
	mov r0, #48
	st [dig], r0
.sub:
	push pch
	push pcl
	b cmp16
	eq r0, #0xff
	bzf .out
	push pch
	push pcl
	b sub16
	ld r0, [dig]
	add r0, #1
	st [dig], r0
	b .sub
.out:
	ld r0, [dig]
	eq r0, #48
	bzf .zero
	b .put
.zero:
	ld r0, [lead]
	eq r0, #1
	bzf .put
	ld r0, [pwi]
	eq r0, #8
	bzf .put
	b .next
.put:
	mov r0, #1
	st [lead], r0
	ld r0, [dig]
	push pch
	push pcl
	b API_PUTC
.next:
	ld r0, [pwi]
	add r0, #2
	st [pwi], r0
	eq r0, #10
	bzf .done
	b .digit
.done:
	pop pcl
	pop pch

; ------------------------------------------------------------ the file

; fname into the buffer (CRs dropped), the gap before it: r0 = 0, or 1 when
; it does not fit. No file: an empty text, "new file"
load:
	xor r0, r0
	st [gap_s], r0
	st [gap_e], r0
	st [cur_line], r0
	st [cur_line+1], r0
	mov r0, #BUF_HI
	st [gap_s+1], r0
	mov r0, #END_HI
	st [gap_e+1], r0
	mov r0, #<[fname]
	st $6f00, r0
	mov r0, #>[fname]
	st $6f01, r0
	mov r0, #FILE_H
	xor r1, r1
	push pch
	push pcl
	b API_ST_OPEN
	eq r0, #0
	bzf .read
	mov r0, #<[s_new]
	st [msg], r0
	mov r0, #>[s_new]
	st [msg+1], r0
	xor r0, r0
	pop pcl
	pop pch
.read:
	mov r0, #<[iobuf]
	st $6f00, r0
	mov r0, #>[iobuf]
	st $6f01, r0
	mov r0, #FILE_H
	mov r1, #128
	push pch
	push pcl
	b API_ST_READ
	eq r0, #0
	bzf .got
	b .close
.got:
	eq r1, #0
	bzf .close
	st [io_n], r1
	xor r0, r0
	st [io_i], r0
.byte:
	ld r1, [io_i]
	ld r0, [io_n]
	eq r0, r1
	bzf .read
	ld r0, [iobuf]+r1
	add r1, #1
	st [io_i], r1
	eq r0, #13
	bzf .byte
	push pch
	push pcl
	b insert
	eq r0, #0
	bzf .big
	b .byte
.big:
	mov r0, #FILE_H
	push pch
	push pcl
	b API_ST_CLOSE
	mov r0, #1
	pop pcl
	pop pch
.close:
	mov r0, #FILE_H
	push pch
	push pcl
	b API_ST_CLOSE
	; the text to the buffer's end (length gap_s - $8000), the gap before it
	ld r0, [gap_s]
	st [ub], r0
	ld r0, [gap_s+1]
	sub r0, #BUF_HI
	st [ub+1], r0
	xor r0, r0
	st [ua], r0
	mov r0, #END_HI
	st [ua+1], r0
	push pch
	push pcl
	b sub16
	ld r0, [ua]
	st $6f00, r0
	st [gap_e], r0
	ld r0, [ua+1]
	st $6f01, r0
	st [gap_e+1], r0
	xor r0, r0
	st $6f02, r0
	st [gap_s], r0
	mov r0, #BUF_HI
	st $6f03, r0
	st [gap_s+1], r0
	ld r0, [ub]
	st $6f04, r0
	ld r0, [ub+1]
	st $6f05, r0
	push pch
	push pcl
	b API_MEM_CPY
	xor r0, r0
	st [cur_line], r0
	st [cur_line+1], r0
	pop pcl
	pop pch

; the text to fname, each LF as CR LF
save:
	xor r0, r0
	st [io_err], r0
	st [io_n], r0
	mov r0, #<[fname]
	st $6f00, r0
	mov r0, #>[fname]
	st $6f01, r0
	mov r0, #FILE_H
	mov r1, #1
	push pch
	push pcl
	b API_ST_OPEN
	eq r0, #0
	bzf .opened
	b .failed
.opened:
	xor r0, r0
	st [rd_p], r0
	mov r0, #BUF_HI
	st [rd_p+1], r0
.loop:
	push pch
	push pcl
	b rd_next
	eq r1, #1
	bzf .end
	eq r0, #10
	bzf .crlf
	push pch
	push pcl
	b out_byte
	b .loop
.crlf:
	mov r0, #13
	push pch
	push pcl
	b out_byte
	mov r0, #10
	push pch
	push pcl
	b out_byte
	b .loop
.end:
	push pch
	push pcl
	b out_flush
	mov r0, #FILE_H
	push pch
	push pcl
	b API_ST_CLOSE
	eq r0, #0
	bzf .closed
	st [io_err], r0
.closed:
	ld r0, [io_err]
	eq r0, #0
	bzf .ok
.failed:
	mov r0, #<[s_nosave]
	st [msg], r0
	mov r0, #>[s_nosave]
	st [msg+1], r0
	pop pcl
	pop pch
.ok:
	xor r0, r0
	st [modified], r0
	mov r0, #<[s_saved]
	st [msg], r0
	mov r0, #>[s_saved]
	st [msg+1], r0
	pop pcl
	pop pch

; byte r0 to iobuf; written when 128 are there
out_byte:
	ld r1, [io_n]
	st [iobuf]+r1, r0
	add r1, #1
	st [io_n], r1
	eq r1, #128
	bzf .flush
	pop pcl
	pop pch
.flush:
	push pch
	push pcl
	b out_flush
	pop pcl
	pop pch

; iobuf's io_n bytes to the file (an error into io_err)
out_flush:
	ld r0, [io_n]
	eq r0, #0
	bzf .done
	mov r0, #<[iobuf]
	st $6f00, r0
	mov r0, #>[iobuf]
	st $6f01, r0
	mov r0, #FILE_H
	ld r1, [io_n]
	push pch
	push pcl
	b API_ST_WRITE
	eq r0, #0
	bzf .written
	st [io_err], r0
.written:
	xor r0, r0
	st [io_n], r0
.done:
	pop pcl
	pop pch

; ------------------------------------------------------------ 16 bits

; the 16-bit number at r0 (low), r1 (high) plus one
inc16:
	st [vp], r0
	st [vp+1], r1
	ldd r0, [vp]
	add r0, #1
	std [vp], r0
	eq r0, #0
	bzf .carry
	pop pcl
	pop pch
.carry:
	mov r1, #1
	ldd r0, [vp]+r1
	add r0, #1
	std [vp]+r1, r0
	pop pcl
	pop pch

; the 16-bit number at r0 (low), r1 (high) minus one
dec16:
	st [vp], r0
	st [vp+1], r1
	ldd r0, [vp]
	eq r0, #0
	bzf .borrow
	sub r0, #1
	std [vp], r0
	pop pcl
	pop pch
.borrow:
	mov r0, #0xff
	std [vp], r0
	mov r1, #1
	ldd r0, [vp]+r1
	sub r0, #1
	std [vp]+r1, r0
	pop pcl
	pop pch

; r0 = 0 if ua = ub, 1 if ua > ub, $ff if ua < ub
cmp16:
	ld r0, [ua+1]
	ld r1, [ub+1]
	eq r0, r1
	bzf .low
	gt r0, r1
	bzf .gt
	b .lt
.low:
	ld r0, [ua]
	ld r1, [ub]
	eq r0, r1
	bzf .eq
	gt r0, r1
	bzf .gt
.lt:
	mov r0, #0xff
	pop pcl
	pop pch
.gt:
	mov r0, #1
	pop pcl
	pop pch
.eq:
	xor r0, r0
	pop pcl
	pop pch

; ua = ua - ub
sub16:
	ld r0, [ua]
	ld r1, [ub]
	lt r0, r1				; a borrow (ZF lasts to the bzf)
	sub r0, r1
	st [ua], r0
	ld r0, [ua+1]
	ld r1, [ub+1]
	sub r0, r1
	bzf .borrow
	st [ua+1], r0
	pop pcl
	pop pch
.borrow:
	sub r0, #1
	st [ua+1], r0
	pop pcl
	pop pch

puts:
	st $6f00, r0			; API_ARGS
	st $6f01, r1
	push pch
	push pcl
	b API_PUTS
	pop pcl
	pop pch
