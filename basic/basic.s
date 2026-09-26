; CUPC/8 BASIC as a program for $7000 (doc/proposals/basic-program.md):
; built by basic/build.sh (tools/mkprg.py, kernel/api.inc in front), kept in
; the ROM image (memory-map.md, "ROM image layout") or as BASIC.PRG on the SD
; card. The kernel copies it to $7000 at boot and again after a native program
; has run there, and calls main; it talks to the machine only through the
; kernel API.
;
; The kernel's terminal reads the lines and runs its own commands (help, dir,
; del, net, refresh, exec). Every other line comes here (main sets the hook,
; API_TERM_HOOK): a numbered line (the program editor), new, run, list, clr,
; save, load; anything else is "invalid cmd".
;
; The program is text at $c000-$dfff, the top 8 KB of the user area
; (memory-map.md): "BA" at $c000, the end at $c002 (two bytes, low first: the
; offset from $c000 of the 0 after the last line, 4 for an empty program),
; then from $c004 the lines in line-number order, each as typed, ending in a
; CR, then the 0 (bas_cmd_line keeps them so). It is not in BASIC's own memory,
; so it outlives a native program that stays below $c000: main keeps it when
; "BA" and the end are right (and the 0 is there), else starts empty. A
; program for $7000 bigger than 20 KB goes over it.

%define PROG_HI #0xc0

bas_line: resb 80			; the line from the terminal
bas_full: resb 1			; the last line was refused (PROGRAM FULL)
bas_src: resb 2				; the hook's pointer
bas_i: resb 1				; bas_find: where in its table
bas_k: resb 1				;   the word's number there
bas_j: resb 1				;   and where in the line
ub_vbank: resb 1			; the RAM_BANK BASIC's PEEK and POKE see (ubasic.s)
bas_list_i: resb 2
bas_list_p: resb 2
bas_p: resb 2				; the last typed line's place ($c004 after new)
bas_ln: resb 2				; the typed line's number
bas_new: resb 1			; the typed line's length with its CR, 0 for just a number
bas_d: resb 2				; what bas_add adds
ub_name: resb 14			; SAVE, LOAD, exec: the file's name
bas_cmds db "new run clr list save load "

; the terminal hands the lines here - the kernel calls main after loading
; BASIC: the program at $c000 kept or started empty, then the hook set
main:
	ld r0, $c000			; "BA" ...
	eq r0, #66
	bzf .b
	b .new
.b:
	ld r0, $c001
	eq r0, #65
	bzf .a
	b .new
.a:
	ld r1, $c003			; ... an end of 4 to $1fff ...
	gt r1, #0x1f
	bzf .new
	ld r0, $c002
	st [bas_p], r0
	eq r1, #0
	bzf .low
	b .at
.low:
	lt r0, #4
	bzf .new
.at:
	add r1, PROG_HI			; ... and the 0 there
	st [bas_p+1], r1
	ldd r0, [bas_p]
	eq r0, #0
	bzf .kept
.new:
	push pch
	push pcl
	b bas_cmd_new
.kept:
	mov r0, #2				; the window as the kernel leaves it, bank 2
	st [ub_vbank], r0
	mov r0, #4				; lines are looked for from the first
	st [bas_p], r0
	mov r0, PROG_HI
	st [bas_p+1], r0
	mov r0, #<bas_hook
	mov r1, #>bas_hook
	push pch
	push pcl
	b API_TERM_HOOK
	pop pcl
	pop pch

; the terminal's hook (API_TERM_HOOK): r0 = 0, a line at the pointer in
; API_ARGS; r0 = 1, exec "NAME" found a file with no program header: its
; name at the pointer, a BASIC program to load and run
bas_hook:
	push r0
	ld r0, API_ARGS
	st [bas_src], r0
	ld r0, $6f01
	st [bas_src+1], r0
	xor r1, r1				; the line into bas_line (79 bytes and a 0 at most)
.copy:
	ldd r0, [bas_src]+r1
	st [bas_line]+r1, r0
	eq r0, #0
	bzf .copied
	add r1, #1
	eq r1, #79
	bzf .cut
	b .copy
.cut:
	xor r0, r0
	st [bas_line]+r1, r0
.copied:
	pop r0
	eq r0, #1
	bzf bas_exec
; a line: a command, a numbered line, or neither
bas_parse:
	mov r0, #<[bas_cmds]
	mov r1, #>[bas_cmds]
	push pch
	push pcl
	b bas_find
	eq r0, #1
	bzf bas_cmd_new
	eq r0, #2
	bzf bas_cmd_run
	eq r0, #3
	bzf bas_cmd_clr
	eq r0, #4
	bzf bas_cmd_list
	eq r0, #5
	bzf ub_cmd_save
	eq r0, #6
	bzf ub_cmd_load
	mov r0, #>[bas_line]
	mov r1, #<[bas_line]
	push pch
	push pcl
	b str_atoi
	gt r1, #0x7f			; a line number is 1-32767
	bzf .invalid
	or r0, r1
	eq r0, #0
	bzf .invalid
	b bas_cmd_line
.invalid:
	bas_s_invalid_cmd db "\nERROR: invalid cmd!\n"
	mov r0, #>[bas_s_invalid_cmd]
	mov r1, #<[bas_s_invalid_cmd]
	b str_printstr


; the line's first word (up to a space, CR, LF or its end) in the table of
; words at r0 (low), r1 (high), each followed by a space: r0 = its number
; there, from 1, or 0
bas_find:
	st [bas_src], r0
	st [bas_src+1], r1
	xor r0, r0
	st [bas_i], r0
	mov r0, #1
	st [bas_k], r0
.word:
	xor r0, r0
	st [bas_j], r0
.char:
	ld r1, [bas_i]
	ldd r0, [bas_src]+r1
	eq r0, #0				; the table's end
	bzf .none
	eq r0, #32				; the word's end
	bzf .end
	ld r1, [bas_j]
	ld r1, [bas_line]+r1
	eq r0, r1
	bzf .same
	b .skip
.same:
	ld r0, [bas_i]
	add r0, #1
	st [bas_i], r0
	ld r0, [bas_j]
	add r0, #1
	st [bas_j], r0
	b .char
.end:
	ld r1, [bas_j]			; the line's word ends here too?
	ld r0, [bas_line]+r1
	eq r0, #32
	bzf .found
	eq r0, #13
	bzf .found
	eq r0, #10
	bzf .found
	eq r0, #0
	bzf .found
.skip:
	ld r1, [bas_i]			; on past this word's space
.past:
	ldd r0, [bas_src]+r1
	add r1, #1
	eq r0, #32
	bzf .next
	b .past
.next:
	st [bas_i], r1
	ld r0, [bas_k]
	add r0, #1
	st [bas_k], r0
	b .word
.found:
	ld r0, [bas_k]
	pop pcl
	pop pch
.none:
	xor r0, r0
	pop pcl
	pop pch

; list - print the program as it is kept, each line's CR as a new line
bas_cmd_list:
	mov r0, #4				; from the first line
	st [bas_list_i], r0
	xor r0, r0
	st [bas_list_i+1], r0
.loop:
	ld r1, [bas_list_i]			; stop at the end
	ld r0, $c002
	eq r1, r0
	bzf .lo_same
	b .byte
.lo_same:
	ld r1, [bas_list_i+1]
	ld r0, $c003
	eq r1, r0
	bzf .done
.byte:
	ld r0, [bas_list_i]
	st [bas_list_p], r0
	ld r0, [bas_list_i+1]
	add r0, PROG_HI
	st [bas_list_p+1], r0
	ldd r0, [bas_list_p]
	eq r0, #13
	bzf .newline
	b .put
.newline:
	mov r0, #10
.put:
	push pch
	push pcl
	b API_PUTC
	ld r0, [bas_list_i]
	add r0, #1
	st [bas_list_i], r0
	eq r0, #0
	bzf .carry
	b .loop
.carry:
	ld r0, [bas_list_i+1]
	add r0, #1
	st [bas_list_i+1], r0
	b .loop
.done:
	pop pcl
	pop pch

; ------------------------------------------------------------ program editing
; A typed line into the program, which is kept in line-number order: it goes
; in its place, replaces the line of its number, and a line number alone
; (spaces after it are fine) deletes that line. The rest of the program moves
; by the difference (API_MEM_CPY, a memmove); PROGRAM FULL if the program
; would end past $dfff. A line numbered above the last one typed is looked
; for from that one's place on (bas_p), so a program typed or loaded in
; order is quick. The work is in API_ARGS ($6f00): +2 the old line's end
; while looking, then API_MEM_CPY's dst, src and len; +6 the new end.
bas_cmd_line:
	xor r0, r0
	st [bas_full], r0
	mov r0, #>[bas_line]
	mov r1, #<[bas_line]
	push pch
	push pcl
	b bas_cmp				; 2 if above the last typed line
	push r0
	ld r0, [n_a]
	st [bas_ln], r0
	ld r0, [n_a+1]
	st [bas_ln+1], r0
	pop r0
	eq r0, #2
	bzf .find
	mov r0, #4				; else from the first line
	st [bas_p], r0
	mov r0, PROG_HI
	st [bas_p+1], r0
.find:
	ld r0, [bas_p]			; the old line's end - the place, for now
	st $6f02, r0
	ld r0, [bas_p+1]
	st $6f03, r0
	ldd r0, [bas_p]
	eq r0, #0
	bzf .placed				; the program's end
	ld r0, [bas_p+1]
	ld r1, [bas_p]
	push pch
	push pcl
	b bas_cmp
	eq r0, #2
	bzf .placed				; a bigger number - the typed line goes before it
	push r0
	xor r1, r1
.eol:
	ldd r0, [bas_p]+r1
	add r1, #1
	eq r0, #13
	bzf .eol_found
	b .eol
.eol_found:
	st [bas_d], r1			; past the line's CR
	xor r0, r0
	st [bas_d+1], r0
	mov r1, #2
	push pch
	push pcl
	b bas_add
	pop r0
	eq r0, #0
	bzf .placed				; the same number - the typed line replaces it
	ld r0, $6f02			; a smaller number - on to the next line
	st [bas_p], r0
	ld r0, $6f03
	st [bas_p+1], r0
	b .find
.placed:
	; the bytes from the old line's end to the program's 0, that included -
	; the end + 1 less (the end - $c000)
	ld r0, $c002
	ld r1, $6f02
	lt r0, r1				; a borrow
	sub r0, r1
	st $6f04, r0
	ld r0, $c003
	add r0, PROG_HI
	ld r1, $6f03
	sub r0, r1
	bzf .borrow
	b .count_hi
.borrow:
	sub r0, #1
.count_hi:
	st $6f05, r0
	mov r0, #1
	st [bas_d], r0
	xor r0, r0
	st [bas_d+1], r0
	mov r1, #4
	push pch
	push pcl
	b bas_add
	; the typed line's length with its CR, 0 for a line number alone
	xor r1, r1
.len:
	ld r0, [bas_line]+r1
	add r1, #1
	eq r0, #13
	bzf .len_done
	b .len
.len_done:
	st [bas_new], r1
	xor r1, r1
.number:
	ld r0, [bas_line]+r1
	add r1, #1
	sub r0, #48
	lt r0, #10
	bzf .number
.spaces:					; then only spaces up to the CR?
	eq r0, #221				; the CR, 13 - 48
	bzf .delete
	eq r0, #240				; a space, 32 - 48
	bzf .space
	b .text
.space:
	ld r0, [bas_line]+r1
	add r1, #1
	sub r0, #48
	b .spaces
.delete:
	xor r0, r0
	st [bas_new], r0
.text:
	; the program grows by k - the typed line's length less the old line's
	; (under 80 each, so the low bytes do) - sign-extended into bas_d
	ld r0, [bas_new]
	ld r1, $6f02
	sub r0, r1
	ld r1, [bas_p]
	add r0, r1
	st [bas_d], r0
	xor r1, r1
	gt r0, #0x7f
	bzf .negative
	b .signed
.negative:
	mov r1, #0xff
.signed:
	st [bas_d+1], r1
	ld r0, $c002			; the new end, at most $1fff
	st $6f06, r0
	ld r0, $c003
	st $6f07, r0
	mov r1, #6
	push pch
	push pcl
	b bas_add
	ld r0, $6f07
	gt r0, #0x1f
	bzf .full
	ld r0, $6f06
	st $c002, r0
	ld r0, $6f07
	st $c003, r0
	ld r0, $6f02			; the rest to the old line's end + k
	st $6f00, r0
	ld r0, $6f03
	st $6f01, r0
	xor r1, r1
	push pch
	push pcl
	b bas_add
	push pch
	push pcl
	b API_MEM_CPY
	ld r0, [bas_p]			; the typed line into its place
	st $6f00, r0
	ld r0, [bas_p+1]
	st $6f01, r0
	mov r0, #<[bas_line]
	st $6f02, r0
	mov r0, #>[bas_line]
	st $6f03, r0
	ld r0, [bas_new]
	st $6f04, r0
	xor r0, r0
	st $6f05, r0
	push pch
	push pcl
	b API_MEM_CPY
	pop pcl
	pop pch
.full:
	mov r0, #1
	st [bas_full], r0
	bas_s_full db "\nPROGRAM FULL\n"
	mov r0, #>[bas_s_full]
	mov r1, #<[bas_s_full]
	push pch
	push pcl
	b str_printstr
.done:
	pop pcl
	pop pch

; the number the text at r0 (high), r1 (low) starts with, into n_a, against
; the typed line's (bas_ln) - r0 0 the same, 1 less, 2 greater
bas_cmp:
	push pch
	push pcl
	b str_atoi
	st [n_a], r0
	st [n_a+1], r1
	ld r0, [bas_ln]
	st [n_b], r0
	ld r0, [bas_ln+1]
	st [n_b+1], r0
	b n16_cmp

; the 16 bits at API_ARGS + r1 plus bas_d
bas_add:
	ld r0, $6f00+r1
	push r1
	ld r1, [bas_d]
	add r0, r1
	lt r0, r1				; carried
	pop r1
	st $6f00+r1, r0
	add r1, #1
	ld r0, $6f00+r1
	bzf .carry
	b .high
.carry:
	add r0, #1
.high:
	push r1
	ld r1, [bas_d+1]
	add r0, r1
	pop r1
	st $6f00+r1, r0
	pop pcl
	pop pch

bas_cmd_run:
	; run the program

	mov r0, PROG_HI
	mov r1, #4
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
	push pch
	push pcl
	b ubasic_gfx_done

	bas_s_done db "\nDONE.\n"
	mov r0, #>[bas_s_done]
	mov r1, #<[bas_s_done]
	push pch
	push pcl
	b str_printstr

.done:
	pop pcl
	pop pch

; new - an empty program: "BA", the end 4, the 0
bas_cmd_new:
	mov r0, #66
	st $c000, r0
	mov r0, #65
	st $c001, r0
	mov r0, #4
	st $c002, r0
	st [bas_p], r0			; lines are looked for from the first
	xor r0, r0
	st $c003, r0
	st $c004, r0
	mov r0, PROG_HI
	st [bas_p+1], r0
	pop pcl
	pop pch

; clr - clear the screen (light grey on black)
bas_cmd_clr:
	mov r0, #0x07
	b API_CLS

; exec "NAME" of a BASIC program (the hook's r0 = 1): its name into ub_name,
; then LOAD and RUN
bas_exec:
	xor r1, r1
.name:
	ld r0, [bas_line]+r1
	st [ub_name]+r1, r0
	eq r0, #0
	bzf .load
	add r1, #1
	eq r1, #13				; longer than 8.3 - the card refuses 13
	bzf .cut
	b .name
.cut:
	xor r0, r0
	st [ub_name]+r1, r0
.load:
	push pch
	push pcl
	b ub_load_file
	eq r0, #0
	bzf bas_cmd_run
	b API_ST_PERROR

; print the string at r0 (high), r1 (low)
str_printstr:
	st API_ARGS, r1
	st $6f01, r0
	b API_PUTS
