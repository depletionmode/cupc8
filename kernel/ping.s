; ping- ICMP echo through the Wi-Fi card's raw ICMP socket (OPEN type 3,
; doc/proposals/kernel-api.md "Networking"), and the clock it and the DNS
; client (resolv.s) time themselves with.
;
; net ping HOST [COUNT] resolves HOST, then sends COUNT (4) echo requests-
; identifier $c8 and a number that changes each run, sequence 1..COUNT, a
; 32-byte payload, the Internet checksum computed here. A reply counts when
; it comes from HOST, its checksum is right, and it is an echo reply with our
; identifier and the sequence just sent; its round-trip time is printed. A
; request not answered in about a second is lost. The next request goes as
; soon as the last is answered (or lost). Then a summary.

%define PING_ID 200
%define PING_LEN 40
; a second, in ms
%define NET_WAIT_LO 232
%define NET_WAIT_HI 3

ping_s_ping db "\nping "
ping_s_seq db "seq "
ping_s_time db " time "
ping_s_ms db " ms\n"
ping_s_lost db " timeout\n"
ping_s_sent db " sent, "
ping_s_got db " received"
ping_s_range db ", "

ping_ip: resb 4
ping_seq: resb 1
ping_count: resb 1
ping_sent: resb 1
ping_got: resb 1
ping_id: resb 1
ping_t0: resb 2
ping_rtt: resb 2
ping_min: resb 2
ping_max: resb 2
ping_len: resb 1
ping_base: resb 1

; ------------------------------------------------------------ the clock
;
; The chipset's millisecond counter (MS_COUNT, $f206-$f209, memory-map.md):
; its low 16 bits are the time here, in ms. Reading MS_COUNT0 latches the
; rest, so MS_COUNT0 then MS_COUNT1 is one value.

; net_u16 = the counter's low 16 bits
net_now:
	ld r0, $f206
	st [net_u16], r0
	ld r0, $f207
	st [net_u16+1], r0
	pop pcl
	pop pch

; net_u16 = ms since net_t16
net_since:
	push pch
	push pcl
	b net_now
	push pch
	push pcl
	b net_sub16
	pop pcl
	pop pch

; r0 = 1 when a second has passed since net_t16
net_waited:
	push pch
	push pcl
	b net_since
	mov r0, #NET_WAIT_LO
	st [net_t16], r0
	mov r0, #NET_WAIT_HI
	st [net_t16+1], r0
	push pch
	push pcl
	b net_ge16
	pop pcl
	pop pch

; ------------------------------------------------------------ the checksum

; the Internet checksum (RFC 1071) of net_count bytes at net_ptr- the ones'
; complement of the ones' complement sum of its 16-bit words (most significant
; byte first; an odd byte is padded with 0), into net_ck (high), net_ck+1
; (low). Over a message with its checksum in place it is 0
net_cksum:
	xor r0, r0
	st [net_ck], r0
	st [net_ck+1], r0
	st [net_ck+2], r0
	st [net_pi], r0
.word:
	ld r1, [net_pi]
	ld r0, [net_count]
	eq r1, r0
	bzf .fold
	ldd r0, [net_ptr]+r1		; the high byte
	st [net_pc], r0
	add r1, #1
	ld r0, [net_count]
	eq r1, r0
	bzf .odd
	ldd r0, [net_ptr]+r1		; the low byte
	add r1, #1
	b .add
.odd:
	xor r0, r0
.add:
	st [net_pi], r1
	ld r1, [net_ck+1]
	add r1, r0
	st [net_ck+1], r1
	lt r1, r0
	bzf .lo_carry
	b .high
.lo_carry:
	ld r1, [net_ck]
	add r1, #1
	st [net_ck], r1
	eq r1, #0
	bzf .hi_carry1
	b .high
.hi_carry1:
	ld r1, [net_ck+2]
	add r1, #1
	st [net_ck+2], r1
.high:
	ld r0, [net_pc]
	ld r1, [net_ck]
	add r1, r0
	st [net_ck], r1
	lt r1, r0
	bzf .hi_carry2
	b .word
.hi_carry2:
	ld r1, [net_ck+2]
	add r1, #1
	st [net_ck+2], r1
	b .word
.fold:
	; the carries out of 16 bits go back in at the bottom (end-around)
	ld r0, [net_ck+2]
	eq r0, #0
	bzf .done
	xor r1, r1
	st [net_ck+2], r1
	ld r1, [net_ck+1]
	add r1, r0
	st [net_ck+1], r1
	lt r1, r0
	bzf .f_carry
	b .fold
.f_carry:
	ld r1, [net_ck]
	add r1, #1
	st [net_ck], r1
	eq r1, #0
	bzf .f_carry2
	b .fold
.f_carry2:
	mov r0, #1
	st [net_ck+2], r0
	b .fold
.done:
	ld r0, [net_ck]
	xor r0, #0xff
	st [net_ck], r0
	ld r0, [net_ck+1]
	xor r0, #0xff
	st [net_ck+1], r0
	pop pcl
	pop pch

; ------------------------------------------------------------ net ping

net_c_ping:
	push pch
	push pcl
	b net_word_host
	eq r0, #0
	bzf .usage
	mov r0, #4
	st [ping_count], r0
	mov r0, #3
	push pch
	push pcl
	b net_word
	ld r0, [net_wlen]
	eq r0, #0
	bzf .counted
	mov r0, #3			; COUNT, 1-255
	push pch
	push pcl
	b net_word_u16
	eq r0, #0
	bzf .usage
	ld r0, [net_u16+1]
	eq r0, #0
	bzf .count_low
	b .usage
.count_low:
	ld r0, [net_u16]
	eq r0, #0
	bzf .usage
	st [ping_count], r0
.counted:
	push pch
	push pcl
	b net_resolve
	eq r0, #0
	bzf .resolved
	b .error
.resolved:
	xor r1, r1
.keep_ip:
	ld r0, [net_ip]+r1
	st [ping_ip]+r1, r0
	add r1, #1
	eq r1, #4
	bzf .kept
	b .keep_ip
.kept:
	mov r0, #3			; ICMP
	push pch
	push pcl
	b net_open
	eq r0, #0
	bzf .opened
	b .error
.opened:
	ld r0, [ping_id]
	add r0, #1
	st [ping_id], r0
	xor r0, r0
	st [ping_sent], r0
	st [ping_got], r0
	st [ping_seq], r0
	st [ping_max], r0
	st [ping_max+1], r0
	mov r0, #0xff
	st [ping_min], r0
	st [ping_min+1], r0
	mov r0, #>[ping_s_ping]
	mov r1, #<[ping_s_ping]
	push pch
	push pcl
	b str_printstr
	mov r0, #<[ping_ip]
	st [net_ptr], r0
	mov r0, #>[ping_ip]
	st [net_ptr+1], r0
	push pch
	push pcl
	b net_print_quad
	mov r0, #10
	push pch
	push pcl
	b print_ascii_char

.next:
	ld r0, [ping_seq]
	ld r1, [ping_count]
	eq r0, r1
	bzf .summary
	add r0, #1
	st [ping_seq], r0
	push pch
	push pcl
	b ping_build
	push pch
	push pcl
	b net_now
	ld r0, [net_u16]
	st [ping_t0], r0
	ld r0, [net_u16+1]
	st [ping_t0+1], r0
	push pch
	push pcl
	b ping_send
	ld r0, [ping_sent]
	add r0, #1
	st [ping_sent], r0
.poll:
	push pch
	push pcl
	b ping_recv
	eq r0, #1
	bzf .reply
	ld r0, [ping_t0]
	st [net_t16], r0
	ld r0, [ping_t0+1]
	st [net_t16+1], r0
	push pch
	push pcl
	b net_waited
	eq r0, #1
	bzf .lost
	b .poll

.reply:
	; the round trip, in ms
	ld r0, [ping_t0]
	st [net_t16], r0
	ld r0, [ping_t0+1]
	st [net_t16+1], r0
	push pch
	push pcl
	b net_since
	ld r0, [net_u16]
	st [ping_rtt], r0
	ld r0, [net_u16+1]
	st [ping_rtt+1], r0
	ld r0, [ping_got]
	add r0, #1
	st [ping_got], r0
	; the shortest and longest
	ld r0, [ping_min]
	st [net_u16], r0
	ld r0, [ping_min+1]
	st [net_u16+1], r0
	ld r0, [ping_rtt]
	st [net_t16], r0
	ld r0, [ping_rtt+1]
	st [net_t16+1], r0
	push pch
	push pcl
	b net_ge16
	eq r0, #1
	bzf .new_min
	b .check_max
.new_min:
	ld r0, [ping_rtt]
	st [ping_min], r0
	ld r0, [ping_rtt+1]
	st [ping_min+1], r0
.check_max:
	ld r0, [ping_rtt]
	st [net_u16], r0
	ld r0, [ping_rtt+1]
	st [net_u16+1], r0
	ld r0, [ping_max]
	st [net_t16], r0
	ld r0, [ping_max+1]
	st [net_t16+1], r0
	push pch
	push pcl
	b net_ge16
	eq r0, #1
	bzf .new_max
	b .print_reply
.new_max:
	ld r0, [ping_rtt]
	st [ping_max], r0
	ld r0, [ping_rtt+1]
	st [ping_max+1], r0
.print_reply:
	; seq N time T ms
	push pch
	push pcl
	b ping_print_seq
	mov r0, #>[ping_s_time]
	mov r1, #<[ping_s_time]
	push pch
	push pcl
	b str_printstr
	ld r0, [ping_rtt]
	st [net_u16], r0
	ld r0, [ping_rtt+1]
	st [net_u16+1], r0
	push pch
	push pcl
	b net_print_u16
	mov r0, #>[ping_s_ms]
	mov r1, #<[ping_s_ms]
	push pch
	push pcl
	b str_printstr
	b .next

.lost:
	; seq N timeout
	push pch
	push pcl
	b ping_print_seq
	mov r0, #>[ping_s_lost]
	mov r1, #<[ping_s_lost]
	push pch
	push pcl
	b str_printstr
	b .next

.summary:
	; S sent, R received[, MIN-MAX ms]
	push pch
	push pcl
	b net_close
	ld r0, [ping_sent]
	push pch
	push pcl
	b term_print_u8
	mov r0, #>[ping_s_sent]
	mov r1, #<[ping_s_sent]
	push pch
	push pcl
	b str_printstr
	ld r0, [ping_got]
	push pch
	push pcl
	b term_print_u8
	mov r0, #>[ping_s_got]
	mov r1, #<[ping_s_got]
	push pch
	push pcl
	b str_printstr
	ld r0, [ping_got]
	eq r0, #0
	bzf .summary_end
	mov r0, #>[ping_s_range]
	mov r1, #<[ping_s_range]
	push pch
	push pcl
	b str_printstr
	ld r0, [ping_min]
	st [net_u16], r0
	ld r0, [ping_min+1]
	st [net_u16+1], r0
	push pch
	push pcl
	b net_print_u16
	mov r0, #45			; a dash
	push pch
	push pcl
	b print_ascii_char
	ld r0, [ping_max]
	st [net_u16], r0
	ld r0, [ping_max+1]
	st [net_u16+1], r0
	push pch
	push pcl
	b net_print_u16
	mov r0, #>[ping_s_ms]
	mov r1, #<[ping_s_ms]
	push pch
	push pcl
	b str_printstr
	pop pcl
	pop pch
.summary_end:
	mov r0, #10
	push pch
	push pcl
	b print_ascii_char
	pop pcl
	pop pch
.usage:
	mov r0, #NET_E_BADARG
.error:
	push pch
	push pcl
	b net_print_err
	pop pcl
	pop pch

; "seq N"
ping_print_seq:
	mov r0, #>[ping_s_seq]
	mov r1, #<[ping_s_seq]
	push pch
	push pcl
	b str_printstr
	ld r0, [ping_seq]
	push pch
	push pcl
	b term_print_u8
	pop pcl
	pop pch

; the echo request for ping_seq into net_pkt, checksum included
ping_build:
	mov r0, #8			; echo request, code 0
	st [net_pkt], r0
	xor r0, r0
	st [net_pkt+1], r0
	st [net_pkt+2], r0
	st [net_pkt+3], r0
	st [net_pkt+6], r0
	mov r0, #PING_ID
	st [net_pkt+4], r0
	ld r0, [ping_id]
	st [net_pkt+5], r0
	ld r0, [ping_seq]
	st [net_pkt+7], r0
	mov r1, #8			; the payload, 64 up
.payload:
	mov r0, r1
	add r0, #56
	st [net_pkt]+r1, r0
	add r1, #1
	eq r1, #PING_LEN
	bzf .sum
	b .payload
.sum:
	mov r0, #<[net_pkt]
	st [net_ptr], r0
	mov r0, #>[net_pkt]
	st [net_ptr+1], r0
	mov r0, #PING_LEN
	st [net_count], r0
	push pch
	push pcl
	b net_cksum
	ld r0, [net_ck]
	st [net_pkt+2], r0
	ld r0, [net_ck+1]
	st [net_pkt+3], r0
	pop pcl
	pop pch

; UDP_SENDTO the request in net_pkt to ping_ip (the port means nothing)
ping_send:
	mov r0, #0x18
	push pch
	push pcl
	b net_begin
	ld r0, [net_sock]
	push pch
	push pcl
	b net_send
	mov r0, #<[ping_ip]
	st [net_ptr], r0
	mov r0, #>[ping_ip]
	st [net_ptr+1], r0
	mov r0, #4
	st [net_count], r0
	push pch
	push pcl
	b net_sendp
	xor r0, r0
	push pch
	push pcl
	b net_send
	xor r0, r0
	push pch
	push pcl
	b net_send
	mov r0, #PING_LEN
	push pch
	push pcl
	b net_send
	mov r0, #<[net_pkt]
	st [net_ptr], r0
	mov r0, #>[net_pkt]
	st [net_ptr+1], r0
	mov r0, #PING_LEN
	st [net_count], r0
	push pch
	push pcl
	b net_sendp
	push pch
	push pcl
	b net_cs_off
	pop pcl
	pop pch

; RECVFROM one ICMP message (up to 64 bytes) into net_pkt- r0 = 1 when it is
; the reply to the request just sent, else 0 (nothing, or not ours)
ping_recv:
	mov r0, #0x1a
	push pch
	push pcl
	b net_begin
	ld r0, [net_sock]
	push pch
	push pcl
	b net_send
	mov r0, #64
	push pch
	push pcl
	b net_send
	push pch
	push pcl
	b net_cs_off
	mov r0, #7
	st [net_hn], r0
	mov r0, #64
	st [net_cap], r0
	mov r0, #<[net_pkt]
	st [net_dst], r0
	mov r0, #>[net_pkt]
	st [net_dst+1], r0
	push pch
	push pcl
	b net_readp
	ld r0, [net_rlen]
	lt r0, #8
	bzf .no
	sub r0, #7
	gt r0, #64
	bzf .no
	st [ping_len], r0
	b ping_match
.no:
	xor r0, r0
	pop pcl
	pop pch

; r0 = 1 when the ICMP message in net_pkt (ping_len bytes, from the address
; in net_buf) is the reply to the request just sent, else 0
ping_match:
	; from the host pinged (an IPv4 header in front, should the card leave one,
	; is skipped)
	xor r1, r1
.from:
	ld r0, [net_buf]+r1
	st [net_rb], r0
	ld r0, [ping_ip]+r1
	push r1
	ld r1, [net_rb]
	eq r0, r1
	pop r1
	bzf .from_next
	b .no
.from_next:
	add r1, #1
	eq r1, #4
	bzf .header
	b .from
.header:
	xor r0, r0
	st [ping_base], r0
	ld r0, [net_pkt]
	and r0, #0xf0
	eq r0, #0x40
	bzf .ip_header
	b .icmp
.ip_header:
	ld r0, [net_pkt]
	and r0, #15
	shl r0, #2
	st [ping_base], r0
.icmp:
	; at least the 8-byte header after the base
	ld r0, [ping_len]
	ld r1, [ping_base]
	lt r0, r1
	bzf .no
	sub r0, r1
	lt r0, #8
	bzf .no
	st [net_count], r0
	mov r0, #<[net_pkt]
	st [net_ptr], r0
	mov r0, #>[net_pkt]
	st [net_ptr+1], r0
	ld r0, [ping_base]
	push pch
	push pcl
	b net_ptr_add
	push pch
	push pcl
	b net_cksum
	ld r0, [net_ck]
	ld r1, [net_ck+1]
	or r0, r1
	eq r0, #0
	bzf .summed
	b .no
.summed:
	; an echo reply (type 0, code 0) with our identifier and sequence
	ld r1, [ping_base]
	ld r0, [net_pkt]+r1
	eq r0, #0
	bzf .type
	b .no
.type:
	add r1, #1
	ld r0, [net_pkt]+r1
	eq r0, #0
	bzf .code
	b .no
.code:
	add r1, #3
	ld r0, [net_pkt]+r1
	eq r0, #PING_ID
	bzf .id_hi
	b .no
.id_hi:
	add r1, #1
	ld r0, [net_pkt]+r1
	push r1
	ld r1, [ping_id]
	eq r0, r1
	pop r1
	bzf .id_lo
	b .no
.id_lo:
	add r1, #1
	ld r0, [net_pkt]+r1
	eq r0, #0
	bzf .seq_hi
	b .no
.seq_hi:
	add r1, #1
	ld r0, [net_pkt]+r1
	push r1
	ld r1, [ping_seq]
	eq r0, r1
	pop r1
	bzf .yes
.no:
	xor r0, r0
	pop pcl
	pop pch
.yes:
	mov r0, #1
	pop pcl
	pop pch
