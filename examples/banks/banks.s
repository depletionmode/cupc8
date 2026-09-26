; banks- a test of banked RAM for the loader and the API
; (doc/proposals/extended-ram.md). The window at $8000-$bfff shows one of
; 32 banks of 16 KB, chosen by RAM_BANK ($f205, API_BANK_SET).
;
; It marks normal memory ($8000 in bank 2), writes a signature into each of
; the 28 extra banks (4-31), at both ends of the window, reads them all
; back (one mark per bank, . good, X bad), checks normal memory kept its
; mark, and copies a byte from bank 5 to bank 30 with API_BANK_FAR_COPY.
;
; Build- python3 tools/mkprg.py examples/banks/banks.s -o build/BANKS.PRG
; Run- exec "BANKS.PRG"

msg_hi db "\nBank switching test. Window $8000-$bfff, banks of 16 KB\nBanks in all "
msg_wr db "\nWriting a signature into banks 4 to 31 ...\nReading them back  "
msg_ok db "\nAll 28 extra banks kept their own data.\n"
msg_bad db "\nBanks with wrong data "
msg_home db "Normal memory (bank 2) kept its mark "
msg_fc db "far_copy from bank 5 to bank 30 "
msg_yes db "yes\n"
msg_no db "NO\n"
msg_bye db "\nPress a key to return to the terminal.\n"

bank: resb 1
errs: resb 1
num: resb 1
dig: resb 1

main:
	mov r0, #<[msg_hi]
	mov r1, #>[msg_hi]
	push pch
	push pcl
	b puts
	push pch
	push pcl
	b API_BANK_COUNT
	push pch
	push pcl
	b print3

	; mark normal memory- $8000 of bank 2, the power-on bank
	mov r0, #2
	push pch
	push pcl
	b API_BANK_SET
	mov r0, #0x5a
	st $8000, r0

	mov r0, #<[msg_wr]
	mov r1, #>[msg_wr]
	push pch
	push pcl
	b puts

	; write- bank number at $8000, bank number + 100 at $bfff
	mov r0, #4
	st [bank], r0
.write:
	ld r0, [bank]
	push pch
	push pcl
	b API_BANK_SET
	ld r0, [bank]
	st $8000, r0
	add r0, #100
	st $bfff, r0
	ld r0, [bank]
	add r0, #1
	st [bank], r0
	eq r0, #32
	bzf .verify
	b .write

	; read back, one mark per bank
.verify:
	xor r0, r0
	st [errs], r0
	mov r0, #4
	st [bank], r0
.check:
	ld r0, [bank]
	push pch
	push pcl
	b API_BANK_SET
	ld r0, $8000
	ld r1, [bank]
	eq r0, r1
	bzf .check_top
	b .bad
.check_top:
	ld r0, $bfff
	ld r1, [bank]
	add r1, #100
	eq r0, r1
	bzf .good
.bad:
	ld r0, [errs]
	add r0, #1
	st [errs], r0
	mov r0, #88
	b .mark
.good:
	mov r0, #46
.mark:
	push pch
	push pcl
	b API_PUTC
	ld r0, [bank]
	add r0, #1
	st [bank], r0
	eq r0, #32
	bzf .summary
	b .check

.summary:
	ld r0, [errs]
	eq r0, #0
	bzf .all_ok
	mov r0, #<[msg_bad]
	mov r1, #>[msg_bad]
	push pch
	push pcl
	b puts
	ld r0, [errs]
	push pch
	push pcl
	b print3
	mov r0, #10
	push pch
	push pcl
	b API_PUTC
	b .home
.all_ok:
	mov r0, #<[msg_ok]
	mov r1, #>[msg_ok]
	push pch
	push pcl
	b puts

	; normal memory- back to bank 2, the mark must still be there
.home:
	mov r0, #2
	push pch
	push pcl
	b API_BANK_SET
	mov r0, #<[msg_home]
	mov r1, #>[msg_home]
	push pch
	push pcl
	b puts
	ld r0, $8000
	eq r0, #0x5a
	push pch
	push pcl
	b yes_no

	; far_copy- the byte at bank 5 offset 0 (5) to bank 30 offset $1000
	mov r0, #5
	st $6f00, r0				; source bank
	xor r0, r0
	st $6f01, r0				; source offset
	st $6f02, r0
	mov r0, #30
	st $6f03, r0				; destination bank
	xor r0, r0
	st $6f04, r0				; destination offset $1000
	mov r0, #0x10
	st $6f05, r0
	mov r0, #1
	st $6f06, r0				; length 1
	xor r0, r0
	st $6f07, r0
	push pch
	push pcl
	b API_BANK_FAR_COPY
	mov r0, #<[msg_fc]
	mov r1, #>[msg_fc]
	push pch
	push pcl
	b puts
	mov r0, #30
	push pch
	push pcl
	b API_BANK_SET
	ld r0, $9000
	eq r0, #5
	push pch
	push pcl
	b yes_no
	mov r0, #2					; leave the power-on bank selected
	push pch
	push pcl
	b API_BANK_SET

	mov r0, #<[msg_bye]
	mov r1, #>[msg_bye]
	push pch
	push pcl
	b puts
	push pch
	push pcl
	b API_GETKEY
	pop pcl
	pop pch

; print yes if the last compare was equal, NO if not
yes_no:
	bzf .yes
	mov r0, #<[msg_no]
	mov r1, #>[msg_no]
	b .say
.yes:
	mov r0, #<[msg_yes]
	mov r1, #>[msg_yes]
.say:
	push pch
	push pcl
	b puts
	pop pcl
	pop pch

; print the NUL-terminated string at r1 (high), r0 (low)
puts:
	st $6f00, r0			; API_ARGS
	st $6f01, r1
	push pch
	push pcl
	b API_PUTS
	pop pcl
	pop pch

; print r0 as three decimal digits
print3:
	st [num], r0
	mov r0, #48
	st [dig], r0
.hundreds:
	ld r0, [num]
	gt r0, #99
	bzf .sub100
	b .h_out
.sub100:
	sub r0, #100
	st [num], r0
	ld r0, [dig]
	add r0, #1
	st [dig], r0
	b .hundreds
.h_out:
	ld r0, [dig]
	push pch
	push pcl
	b API_PUTC
	mov r0, #48
	st [dig], r0
.tens:
	ld r0, [num]
	gt r0, #9
	bzf .sub10
	b .t_out
.sub10:
	sub r0, #10
	st [num], r0
	ld r0, [dig]
	add r0, #1
	st [dig], r0
	b .tens
.t_out:
	ld r0, [dig]
	push pch
	push pcl
	b API_PUTC
	ld r0, [num]
	add r0, #48
	push pch
	push pcl
	b API_PUTC
	pop pcl
	pop pch
