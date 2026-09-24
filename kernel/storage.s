; Storage driver - the storage card (doc/hardware/storage-card.md).
;
; The card runs the medium (a microSD card in M1) and the FAT file system,
; so these are thin wrappers over its commands - a command frame, then a
; READ frame for the answer. The card may take a long time (an SD card is
; busy for up to 250 ms on a write), so a READ that says "not ready" is
; repeated, up to 65280 times (a few seconds).
;
; Arguments and results are in memory -
;   st_h      handle 0-3
;   st_mode   0 read, 1 write (create or truncate), 2 append
;   st_name   an 8.3 name, NUL-terminated
;   st_n      bytes to write from st_buf, or to read
;   st_rbuf   the last answer (st_rlen bytes). F_READ puts n' at st_rbuf, the
;             data after it. A directory entry is size (4 bytes, low first),
;             attributes, name length, name.
; Each returns an error code in r0, 0 = ok (codes in storage-card.md, and
; ST_E_NOCARD, ST_E_TIMEOUT, ST_E_POWER below). st_print_err prints its message.
;
; Writing needs a 3 A USB-C source (SYSCTL bit 1, PWR_HI; power.md): below
; it, opening a file to write or append, and deleting one, return ST_E_POWER
; before the card is asked. A brown-out in the middle of a write can leave the
; file system damaged; one in the middle of a read loses nothing, so reading
; stays allowed.

%define ST_E_NOCARD #12
%define ST_E_TIMEOUT #11
%define ST_E_POWER #13
%define ST_CFG_DIV2 16

st_spi: resb 1
st_tmp: resb 1
st_try: resb 2
st_ri: resb 1
st_rlen: resb 1
st_rbuf: resb 256
st_h: resb 1
st_mode: resb 1
st_n: resb 1
st_name: resb 14
st_buf: resb 128

st_s_nomedium db "\nno SD card\n"
st_s_nocard db "\nno storage card\n"
st_s_notfound db "\nfile not found\n"
st_s_full db "\ncard full\n"
st_s_wp db "\nwrite protected\n"
st_s_unmounted db "\nno file system on the card\n"
st_s_exists db "\nfile exists\n"
st_s_badname db "\nbad file name\n"
st_s_error db "\ncard error\n"
st_s_power db "\nUSB power under 3A: SD writes off\n"

storage_init:
	mov r0, #0xff
	st [st_spi], r0
	xor r0, r0
	st [st_tmp], r0
.scan:
	ld r0, [st_tmp]
	ld r1, $0002+r0
	eq r1, #4				; card type 4 is storage
	bzf .found
	ld r0, [st_tmp]
	add r0, #1
	st [st_tmp], r0
	lt r0, #6
	bzf .scan
	b .done					; no storage card fitted
.found:
	ld r0, [st_tmp]
	shl r0, #4
	st [st_spi], r0
	mov r1, #ST_CFG_DIV2
	st $f10f+r0, r1
.done:
	pop pcl
	pop pch

; one byte out (r0), the byte that came back in r0
st_send:
	st [st_tmp], r0
	ld r0, [st_spi]
	ld r1, [st_tmp]
	st $f100+r0, r1
	mov r1, #1
	st $f102+r0, r1
.spi_wait:					; SPI_RX is only valid once SPI_STAT says done
	ld r1, $f103+r0
	eq r1, #0
	bzf .spi_wait
	ld r1, $f101+r0
	st [st_tmp], r1
	ld r0, [st_tmp]
	pop pcl
	pop pch

st_cs_on:
	ld r0, [st_spi]
	mov r1, #1
	st $f104+r0, r1
	pop pcl
	pop pch

st_cs_off:
	ld r0, [st_spi]
	mov r1, #0
	st $f104+r0, r1
	pop pcl
	pop pch

; start a command frame - CS on, then the opcode in r0
st_cmd:
	push r0
	push pch
	push pcl
	b st_cs_on
	pop r0
	push pch
	push pcl
	b st_send
	pop pcl
	pop pch

; the answer into st_rbuf and st_rlen; r0 = 0, or ST_E_TIMEOUT. RESP_LEN 0 means
; not ready yet (slot.md) - end the frame and ask again
st_resp:
	xor r0, r0
	st [st_try], r0
	st [st_try+1], r0
	st [st_rlen], r0
.again:
	mov r0, #0xfe
	push pch
	push pcl
	b st_cmd
	mov r0, #0
	push pch
	push pcl
	b st_send				; RESP_LEN
	eq r0, #0
	bzf .not_ready
	st [st_rlen], r0
	xor r0, r0
	st [st_ri], r0
.loop:
	ld r0, [st_ri]
	ld r1, [st_rlen]
	eq r0, r1
	bzf .done
	mov r0, #0
	push pch
	push pcl
	b st_send
	ld r1, [st_ri]
	st [st_rbuf]+r1, r0
	add r1, #1
	st [st_ri], r1
	b .loop
.done:
	push pch
	push pcl
	b st_cs_off
	xor r0, r0
	pop pcl
	pop pch
.not_ready:
	push pch
	push pcl
	b st_cs_off
	ld r0, [st_try]
	add r0, #1
	st [st_try], r0
	eq r0, #0
	bzf .carry
	b .again
.carry:
	ld r0, [st_try+1]
	add r0, #1
	st [st_try+1], r0
	eq r0, #255
	bzf .timeout
	b .again
.timeout:
	mov r0, ST_E_TIMEOUT
	pop pcl
	pop pch

; end the command frame, then its one-byte answer (an error code) in r0
st_err_answer:
	push pch
	push pcl
	b st_cs_off
	push pch
	push pcl
	b st_resp
	eq r0, #0
	bzf .answered
	b .done
.answered:
	ld r0, [st_rlen]
	eq r0, #1
	bzf .one
	mov r0, #9				; not an error code - an I/O error
	b .done
.one:
	ld r0, [st_rbuf]
.done:
	pop pcl
	pop pch

; the name - its length, then its characters
st_send_name:
	xor r1, r1
.len:
	ld r0, [st_name]+r1
	eq r0, #0
	bzf .send
	add r1, #1
	eq r1, #13
	bzf .send
	b .len
.send:
	st [st_ri], r1
	mov r0, r1
	push pch
	push pcl
	b st_send
	xor r1, r1
	push r1
.loop:
	pop r1
	ld r0, [st_ri]
	eq r1, r0
	bzf .done
	ld r0, [st_name]+r1
	add r1, #1
	push r1
	push pch
	push pcl
	b st_send
	b .loop
.done:
	pop pcl
	pop pch

; ------------------------------------------------------------ the commands

; ST_INFO - media, err, flags, free KB (4), total KB (4) in st_rbuf
st_info:
	ld r0, [st_spi]
	eq r0, #0xff
	bzf .nocard
	mov r0, #0x01
	push pch
	push pcl
	b st_cmd
	push pch
	push pcl
	b st_cs_off
	push pch
	push pcl
	b st_resp
	pop pcl
	pop pch
.nocard:
	mov r0, ST_E_NOCARD
	pop pcl
	pop pch

; F_OPEN st_h, st_mode, st_name
st_open:
	ld r0, [st_spi]
	eq r0, #0xff
	bzf .nocard
	ld r0, [st_mode]
	eq r0, #0
	bzf .allowed				; reading - any source
	ld r0, $f203				; writing - PWR_HI (a 3 A source)
	and r0, #2
	eq r0, #0
	bzf .weak
.allowed:
	mov r0, #0x10
	push pch
	push pcl
	b st_cmd
	ld r0, [st_h]
	push pch
	push pcl
	b st_send
	ld r0, [st_mode]
	push pch
	push pcl
	b st_send
	push pch
	push pcl
	b st_send_name
	b st_err_answer
.weak:
	mov r0, ST_E_POWER
	pop pcl
	pop pch
.nocard:
	mov r0, ST_E_NOCARD
	pop pcl
	pop pch

; F_READ st_h, st_n bytes - st_n = the bytes read (fewer at the end of the
; file), the data at st_rbuf+1
st_read:
	ld r0, [st_spi]
	eq r0, #0xff
	bzf .nocard
	mov r0, #0x11
	push pch
	push pcl
	b st_cmd
	ld r0, [st_h]
	push pch
	push pcl
	b st_send
	ld r0, [st_n]
	push pch
	push pcl
	b st_send
	push pch
	push pcl
	b st_cs_off
	push pch
	push pcl
	b st_resp
	eq r0, #0
	bzf .answered
	b .done
.answered:
	ld r0, [st_rbuf]
	eq r0, #0xff				; n' = $ff - an error, its code next
	bzf .error
	st [st_n], r0
	xor r0, r0
	b .done
.error:
	ld r0, [st_rbuf+1]
	b .done
.nocard:
	mov r0, ST_E_NOCARD
.done:
	pop pcl
	pop pch

; F_WRITE st_h, st_n bytes of st_buf (at most 128)
st_write:
	ld r0, [st_spi]
	eq r0, #0xff
	bzf .nocard
	mov r0, #0x12
	push pch
	push pcl
	b st_cmd
	ld r0, [st_h]
	push pch
	push pcl
	b st_send
	ld r0, [st_n]
	push pch
	push pcl
	b st_send
	xor r1, r1
	push r1
.loop:
	pop r1
	ld r0, [st_n]
	eq r1, r0
	bzf .sent
	ld r0, [st_buf]+r1
	add r1, #1
	push r1
	push pch
	push pcl
	b st_send
	b .loop
.sent:
	b st_err_answer
.nocard:
	mov r0, ST_E_NOCARD
	pop pcl
	pop pch

; F_CLOSE st_h - flushes the file to the card
st_close:
	ld r0, [st_spi]
	eq r0, #0xff
	bzf .nocard
	mov r0, #0x13
	push pch
	push pcl
	b st_cmd
	ld r0, [st_h]
	push pch
	push pcl
	b st_send
	b st_err_answer
.nocard:
	mov r0, ST_E_NOCARD
	pop pcl
	pop pch

; F_DELETE st_name - a write to the file system: needs PWR_HI, as st_open
st_delete:
	ld r0, [st_spi]
	eq r0, #0xff
	bzf .nocard
	ld r0, $f203
	and r0, #2
	eq r0, #0
	bzf .weak
	mov r0, #0x17
	push pch
	push pcl
	b st_cmd
	push pch
	push pcl
	b st_send_name
	b st_err_answer
.weak:
	mov r0, ST_E_POWER
	pop pcl
	pop pch
.nocard:
	mov r0, ST_E_NOCARD
	pop pcl
	pop pch

; DIR_FIRST and DIR_NEXT - r0 = 0 and the entry in st_rbuf, $ff after the
; last one, or an error
st_dir_first:
	mov r0, #0x15
	b st_dir
st_dir_next:
	mov r0, #0x16
st_dir:
	st [st_tmp+0], r0
	ld r0, [st_spi]
	eq r0, #0xff
	bzf .nocard
	ld r0, [st_tmp+0]
	push pch
	push pcl
	b st_cmd
	push pch
	push pcl
	b st_cs_off
	push pch
	push pcl
	b st_resp
	eq r0, #0
	bzf .answered
	b .done
.answered:
	ld r0, [st_rlen]
	eq r0, #1				; one byte - $ff (the end) or an error
	bzf .short
	xor r0, r0
	b .done
.short:
	ld r0, [st_rbuf]
	b .done
.nocard:
	mov r0, ST_E_NOCARD
.done:
	pop pcl
	pop pch

; print the message for error r0
st_print_err:
	eq r0, #1
	bzf .nomedium
	eq r0, #12
	bzf .nocard
	eq r0, #3
	bzf .notfound
	eq r0, #5
	bzf .full
	eq r0, #6
	bzf .wp
	eq r0, #2
	bzf .unmounted
	eq r0, #4
	bzf .exists
	eq r0, #8
	bzf .badname
	eq r0, #13
	bzf .power
	mov r0, #>[st_s_error]
	mov r1, #<[st_s_error]
	b .print
.nomedium:
	mov r0, #>[st_s_nomedium]
	mov r1, #<[st_s_nomedium]
	b .print
.nocard:
	mov r0, #>[st_s_nocard]
	mov r1, #<[st_s_nocard]
	b .print
.notfound:
	mov r0, #>[st_s_notfound]
	mov r1, #<[st_s_notfound]
	b .print
.full:
	mov r0, #>[st_s_full]
	mov r1, #<[st_s_full]
	b .print
.wp:
	mov r0, #>[st_s_wp]
	mov r1, #<[st_s_wp]
	b .print
.unmounted:
	mov r0, #>[st_s_unmounted]
	mov r1, #<[st_s_unmounted]
	b .print
.exists:
	mov r0, #>[st_s_exists]
	mov r1, #<[st_s_exists]
	b .print
.badname:
	mov r0, #>[st_s_badname]
	mov r1, #<[st_s_badname]
	b .print
.power:
	mov r0, #>[st_s_power]
	mov r1, #<[st_s_power]
.print:
	push pch
	push pcl
	b str_printstr
	pop pcl
	pop pch
