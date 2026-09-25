; Network driver - the Wi-Fi card (doc/hardware/wifi-card.md).
;
; The card runs the whole stack, so this is framing- send a command frame,
; then a READ frame for the answer. On top of that, in CUPC/8 assembly (doc/
; proposals/kernel-api.md, "Networking"): the terminal's "net" command, the
; DNS client (resolv.s), ping (ping.s) and the net group of the kernel API
; (api_net_*, at the end of this file).
;
; Frames are stored as byte blobs in .data and sent with net_frame, or built
; with net_begin / net_send / net_cs_off.
;
; The assembler takes any code line with a colon as a label, so comments on
; code lines avoid colons.

%define SLOT_TABLE $0002
%define NET_CFG_DIV2 16
%define NET_TIMEOUT 64

; the API block (kernel-api.md)- 32 bytes of arguments and results, the error
%define API_ARGS $6f00
%define API_ERR $6f20

; errors- the net API's r0, and what the terminal prints (net_print_err)
%define NET_E_NOCARD 1
%define NET_E_POWER 2
%define NET_E_TIMEOUT 3
%define NET_E_FAILED 4
%define NET_E_NOSOCK 5
%define NET_E_NXDOMAIN 6
%define NET_E_NOANSWER 7
%define NET_E_MALFORMED 8
%define NET_E_BADARG 9
%define NET_E_NODNS 10
%define NET_E_DNSTIME 11
%define NET_E_DNSERR 12

; NET_STATUS
net_f_status db 1
; EVENTS
net_f_events db 31
; NET_CONFIG_GET
net_f_cfgget db 9

net_s_joined db "\njoined, address "
net_s_link db "\nlink "
net_s_up db "up, address "
net_s_down db "down\n"
net_s_failed db "\nconnect failed\n"
; "GET / HTTP/1.0" CR LF "Host" colon space, in numbers (the assembler has no \r)
net_s_get1 db 71, 69, 84, 32, 47, 32, 72, 84, 84, 80, 47, 49, 46, 48, 13, 10, 72, 111, 115, 116, 58, 32, 0
net_s_get2 db 13, 10, 13, 10, 0
; the errors' messages, in the order of their numbers (net_print_err)
net_s_nocard db "\nno wifi card\n"
net_s_weak db "\nUSB power under 3A: net off\n"
net_s_timeout db "\nnet timeout\n"
net_s_cfgerr db "\nno answer from the card\n"
net_s_nosock db "\nno free socket\n"
net_s_nxdomain db "\nname not found\n"
net_s_noanswer db "\nno address for that name\n"
net_s_malformed db "\nbad answer from the DNS server\n"
net_s_usage db "\nnet join SSID PASSWORD | net get HOST [PORT] | net\nnet lookup NAME | net ping HOST [COUNT]\nnet config [dns IP [PORT] | ip IP MASK GW | dhcp | save]\n"
net_s_nodns db "\nno DNS server\n"
net_s_dnstime db "\nDNS server not answering\n"
net_s_dnserr db "\nDNS server error\n"
net_s_mode db "\nmode "
net_s_dhcp db "dhcp"
net_s_static db "static, ip "
net_s_mask db " mask "
net_s_gw db " gw "
net_s_dns db "\ndns "
net_s_fromdhcp db "from dhcp"
net_s_port db " port "
net_s_saved db "\nsaved\n"
net_s_notsaved db "\nnot saved\n"
net_s_nl db "\n"

; words of the command line
net_w_join db "join"
net_w_get db "get"
net_w_lookup db "lookup"
net_w_ping db "ping"
net_w_config db "config"
net_w_dns db "dns"
net_w_ip db "ip"
net_w_dhcp db "dhcp"
net_w_save db "save"

; 10000, 1000, 100, 10, little-endian, for net_print_u16
net_pow db 16, 39, 232, 3, 100, 0, 10, 0

net_spi: resb 1
net_tmp: resb 2
net_ptr: resb 2
net_count: resb 1
net_buf: resb 64
net_retry: resb 2
net_tries: resb 1
net_line: resb 2                ; the typed line (term.s sets it, it is assembled after this file)
net_want: resb 1                ; net_word, the word wanted
net_wn: resb 1                  ;   the word being scanned
net_si: resb 1                  ;   index into the line
net_di: resb 1                  ;   index into net_wbuf
net_ch: resb 1
net_wlen: resb 1
net_wbuf: resb 64
net_host: resb 64
net_hlen: resb 1
net_port: resb 2
net_op: resb 1                  ; net_begin, net_op2
net_arg: resb 1
net_sock: resb 1                ; the socket a terminal command uses
net_ip: resb 4                  ; an address- parsed, resolved
net_dst: resb 2                 ; net_readp- where the data goes
net_cap: resb 1                 ;   how much of it to keep
net_hn: resb 1                  ;   header bytes first, into net_buf
net_rlen: resb 1                ;   RESP_LEN (0, no answer)
net_ri: resb 1
net_rb: resb 1
net_cfg: resb 20                ; NET_CONFIG(_GET)- mode, ip, mask, gw, dns, port16, save(d)
net_u16: resb 2                 ; 16-bit arithmetic- net_u16 op net_t16
net_t16: resb 2
net_pi: resb 1                  ; parsing and printing
net_pn: resb 1
net_pv: resb 1
net_pd: resb 1
net_pc: resb 1
net_pz: resb 1
net_wi: resb 1                  ; net config ip- the word
net_pkt: resb 256               ; a datagram- DNS answers, ICMP messages
net_a0: resb 1                  ; the API caller's r0 and r1
net_a1: resb 1
net_ticks: resb 2               ; ping.s's clock- quarter milliseconds while it runs
net_clk_n: resb 1               ;   how many use it
net_irq_r0: resb 1               ; ping.s's tick handler
net_irq_f: resb 1
net_irq_a: resb 2
net_ck: resb 3                  ; ping.s's checksum- sum high, low, carries

net_init:
	mov r0, #0xff
	st [net_spi], r0
	xor r0, r0
	st [net_clk_n], r0		; RAM powers up with junk
	st [net_tmp], r0
.scan:
	ld r0, [net_tmp]
	ld r1, SLOT_TABLE+r0
	eq r1, #3				; card type 3 is Wi-Fi
	bzf .found
	ld r0, [net_tmp]
	add r0, #1
	st [net_tmp], r0
	lt r0, #6
	bzf .scan
	b .done
.found:
	ld r0, [net_tmp]
	shl r0, #4
	st [net_spi], r0
	mov r1, #NET_CFG_DIV2
	st $f10f+r0, r1
	; IRQ_n while events wait, so a program can WAI for them (the net API)
	mov r0, #0xf2
	mov r1, #1
	push pch
	push pcl
	b net_op2
.done:
	pop pcl
	pop pch

net_send:
	st [net_tmp], r0
	ld r0, [net_spi]
	ld r1, [net_tmp]
	st $f100+r0, r1
	mov r1, #1
	st $f102+r0, r1
.spi_wait:					; SPI_RX is only valid once SPI_STAT says done
	ld r1, $f103+r0
	eq r1, #0
	bzf .spi_wait
	ld r1, $f101+r0
	st [net_tmp], r1
	ld r0, [net_tmp]
	pop pcl
	pop pch

net_cs_on:
	ld r0, [net_spi]
	mov r1, #1
	st $f104+r0, r1
	pop pcl
	pop pch

net_cs_off:
	ld r0, [net_spi]
	mov r1, #0
	st $f104+r0, r1
	pop pcl
	pop pch

; open a command frame with the opcode r0
net_begin:
	st [net_op], r0
	push pch
	push pcl
	b net_cs_on
	ld r0, [net_op]
	push pch
	push pcl
	b net_send
	pop pcl
	pop pch

; the two-byte command frame r0, r1 (opcode, argument)
net_op2:
	st [net_arg], r1
	push pch
	push pcl
	b net_begin
	ld r0, [net_arg]
	push pch
	push pcl
	b net_send
	push pch
	push pcl
	b net_cs_off
	pop pcl
	pop pch

; net_ptr + 1
net_ptr_inc:
	ld r0, [net_ptr]
	add r0, #1
	st [net_ptr], r0
	eq r0, #0
	bzf .carry
	pop pcl
	pop pch
.carry:
	ld r0, [net_ptr+1]
	add r0, #1
	st [net_ptr+1], r0
	pop pcl
	pop pch

; net_ptr + r0
net_ptr_add:
	ld r1, [net_ptr]
	add r1, r0
	st [net_ptr], r1
	lt r1, r0
	bzf .carry
	pop pcl
	pop pch
.carry:
	ld r0, [net_ptr+1]
	add r0, #1
	st [net_ptr+1], r0
	pop pcl
	pop pch

; send net_count bytes from net_ptr, in a frame the caller opened
net_sendp:
.loop:
	ld r0, [net_count]
	eq r0, #0
	bzf .done
	ldd r0, [net_ptr]
	push pch
	push pcl
	b net_send
	push pch
	push pcl
	b net_ptr_inc
	ld r0, [net_count]
	sub r0, #1
	st [net_count], r0
	b .loop
.done:
	pop pcl
	pop pch

; send the frame at net_ptr, net_count bytes
net_frame:
	push pch
	push pcl
	b net_cs_on
	push pch
	push pcl
	b net_sendp
	push pch
	push pcl
	b net_cs_off
	pop pcl
	pop pch

; READ frame- the response into net_buf (64 bytes, the rest is dropped)
net_read:
	mov r0, #64
	st [net_hn], r0
	xor r0, r0
	st [net_cap], r0
	b net_readp

; READ frame of any length- the first net_hn bytes go to net_buf, the rest to
; net_dst, up to net_cap of them. net_rlen is RESP_LEN, or 0 when the card
; never had the answer ready (255 tries)
net_readp:
	xor r0, r0
	st [net_tries], r0
	st [net_rlen], r0
.again:
	push pch
	push pcl
	b net_cs_on
	mov r0, #0xfe
	push pch
	push pcl
	b net_send
	mov r0, #0
	push pch
	push pcl
	b net_send			; RESP_LEN
	eq r0, #0
	bzf .not_ready
	st [net_rlen], r0
	xor r0, r0
	st [net_ri], r0
.loop:
	ld r0, [net_ri]
	ld r1, [net_rlen]
	eq r0, r1
	bzf .done
	mov r0, #0
	push pch
	push pcl
	b net_send
	st [net_rb], r0
	ld r1, [net_ri]
	ld r0, [net_hn]
	lt r1, r0
	bzf .head
	sub r1, r0			; the data byte's index
	ld r0, [net_cap]
	lt r1, r0
	bzf .keep
	b .next
.keep:
	ld r0, [net_rb]
	std [net_dst]+r1, r0
	b .next
.head:
	ld r0, [net_rb]
	st [net_buf]+r1, r0
.next:
	ld r0, [net_ri]
	add r0, #1
	st [net_ri], r0
	b .loop
.not_ready:
	push pch
	push pcl
	b net_cs_off
	ld r0, [net_tries]
	add r0, #1
	st [net_tries], r0
	eq r0, #255
	bzf .gone
	b .again
.done:
	push pch
	push pcl
	b net_cs_off
.gone:
	pop pcl
	pop pch

; r0 = 0 when the card can be used, else NET_E_NOCARD or NET_E_POWER (the
; radio needs a 3 A source- SYSCTL bit 1, PWR_HI; doc/hardware/power.md)
net_ready:
	ld r0, [net_spi]
	eq r0, #0xff
	bzf .none
	ld r0, $f203
	and r0, #2
	eq r0, #0
	bzf .weak
	xor r0, r0
	pop pcl
	pop pch
.none:
	mov r0, #NET_E_NOCARD
	pop pcl
	pop pch
.weak:
	mov r0, #NET_E_POWER
	pop pcl
	pop pch

; OPEN socket type r0- net_sock is the socket, r0 = 0, or NET_E_NOSOCK
net_open:
	mov r1, r0
	mov r0, #0x10
	push pch
	push pcl
	b net_op2
	mov r0, #1
	st [net_count], r0
	push pch
	push pcl
	b net_read
	ld r0, [net_buf]
	st [net_sock], r0
	lt r0, #4
	bzf .ok
	mov r0, #NET_E_NOSOCK
	pop pcl
	pop pch
.ok:
	xor r0, r0
	pop pcl
	pop pch

; CLOSE net_sock
net_close:
	mov r0, #0x17
	ld r1, [net_sock]
	push pch
	push pcl
	b net_op2
	pop pcl
	pop pch

; NET_CONFIG_GET into net_cfg- r0 = 0, or NET_E_FAILED (no answer from the card)
net_cfg_get:
	mov r0, #<[net_f_cfgget]
	st [net_ptr], r0
	mov r0, #>[net_f_cfgget]
	st [net_ptr+1], r0
	mov r0, #1
	st [net_count], r0
	push pch
	push pcl
	b net_frame
	xor r0, r0
	st [net_hn], r0
	mov r0, #20
	st [net_cap], r0
	mov r0, #<[net_cfg]
	st [net_dst], r0
	mov r0, #>[net_cfg]
	st [net_dst+1], r0
	push pch
	push pcl
	b net_readp
	ld r0, [net_rlen]
	eq r0, #20
	bzf .ok
	mov r0, #NET_E_FAILED
	pop pcl
	pop pch
.ok:
	xor r0, r0
	pop pcl
	pop pch

; NET_CONFIG from net_cfg (20 bytes, the last is save)
net_cfg_set:
	mov r0, #8
	push pch
	push pcl
	b net_begin
	mov r0, #<[net_cfg]
	st [net_ptr], r0
	mov r0, #>[net_cfg]
	st [net_ptr+1], r0
	mov r0, #20
	st [net_count], r0
	push pch
	push pcl
	b net_sendp
	push pch
	push pcl
	b net_cs_off
	pop pcl
	pop pch

; ------------------------------------------------------------ 16-bit numbers

; net_u16 + net_t16- r0 = 1 when it carried out of 16 bits (the sum is then
; not kept whole)
net_add16:
	ld r0, [net_u16]
	ld r1, [net_t16]
	add r0, r1
	st [net_u16], r0
	lt r0, r1
	bzf .carry
	b .high
.carry:
	ld r0, [net_u16+1]
	add r0, #1
	st [net_u16+1], r0
	eq r0, #0
	bzf .out
.high:
	ld r0, [net_u16+1]
	ld r1, [net_t16+1]
	add r0, r1
	st [net_u16+1], r0
	lt r0, r1
	bzf .out
	xor r0, r0
	pop pcl
	pop pch
.out:
	mov r0, #1
	pop pcl
	pop pch

; net_u16 - net_t16 (mod 65536)
net_sub16:
	ld r0, [net_u16]
	ld r1, [net_t16]
	lt r0, r1
	bzf .borrow
	sub r0, r1
	st [net_u16], r0
	ld r0, [net_u16+1]
	b .high
.borrow:
	sub r0, r1
	st [net_u16], r0
	ld r0, [net_u16+1]
	sub r0, #1
.high:
	ld r1, [net_t16+1]
	sub r0, r1
	st [net_u16+1], r0
	pop pcl
	pop pch

; r0 = 1 when net_u16 >= net_t16, else 0
net_ge16:
	ld r0, [net_u16+1]
	ld r1, [net_t16+1]
	gt r0, r1
	bzf .yes
	lt r0, r1
	bzf .no
	ld r0, [net_u16]
	ld r1, [net_t16]
	lt r0, r1
	bzf .no
.yes:
	mov r0, #1
	pop pcl
	pop pch
.no:
	xor r0, r0
	pop pcl
	pop pch

; the decimal number at net_ptr (up to a NUL) into net_u16- r0 = 1 when it is
; one (digits only, at least one, under 65536), else 0
net_parse_u16:
	xor r0, r0
	st [net_u16], r0
	st [net_u16+1], r0
	st [net_pi], r0
	ldd r0, [net_ptr]
	eq r0, #0
	bzf .bad
.digit:
	ld r1, [net_pi]
	ldd r0, [net_ptr]+r1
	eq r0, #0
	bzf .good
	lt r0, #48
	bzf .bad
	gt r0, #57
	bzf .bad
	sub r0, #48
	st [net_pd], r0
	; times 10- n added to itself 9 times
	ld r0, [net_u16]
	st [net_t16], r0
	ld r0, [net_u16+1]
	st [net_t16+1], r0
	mov r0, #9
	st [net_pn], r0
.times10:
	push pch
	push pcl
	b net_add16
	eq r0, #1
	bzf .bad
	ld r0, [net_pn]
	sub r0, #1
	st [net_pn], r0
	eq r0, #0
	bzf .add_digit
	b .times10
.add_digit:
	ld r0, [net_pd]
	st [net_t16], r0
	xor r0, r0
	st [net_t16+1], r0
	push pch
	push pcl
	b net_add16
	eq r0, #1
	bzf .bad
	ld r0, [net_pi]
	add r0, #1
	st [net_pi], r0
	b .digit
.good:
	mov r0, #1
	pop pcl
	pop pch
.bad:
	xor r0, r0
	pop pcl
	pop pch

; the dotted quad at net_ptr (up to a NUL) into net_ip- r0 = 1 when it is one
; (four numbers 0-255, up to three digits each, three dots), else 0
net_parse_ip:
	xor r0, r0
	st [net_pi], r0
	st [net_pn], r0
.part:
	xor r0, r0
	st [net_pv], r0
	st [net_pd], r0
.char:
	ld r1, [net_pi]
	ldd r0, [net_ptr]+r1
	eq r0, #46			; a dot
	bzf .dot
	eq r0, #0
	bzf .end
	lt r0, #48
	bzf .bad
	gt r0, #57
	bzf .bad
	sub r0, #48
	st [net_pc], r0
	ld r0, [net_pd]
	add r0, #1
	st [net_pd], r0
	eq r0, #4
	bzf .bad
	ld r0, [net_pv]
	gt r0, #25
	bzf .bad
	mov r1, r0			; v * 10 = v * 8 + v * 2
	shl r0, #3
	shl r1, #1
	add r0, r1
	ld r1, [net_pc]
	add r0, r1
	lt r0, r1			; past 255
	bzf .bad
	st [net_pv], r0
	ld r0, [net_pi]
	add r0, #1
	st [net_pi], r0
	b .char
.dot:
	ld r0, [net_pd]
	eq r0, #0
	bzf .bad
	ld r1, [net_pn]
	eq r1, #3
	bzf .bad
	ld r0, [net_pv]
	st [net_ip]+r1, r0
	add r1, #1
	st [net_pn], r1
	ld r0, [net_pi]
	add r0, #1
	st [net_pi], r0
	b .part
.end:
	ld r0, [net_pd]
	eq r0, #0
	bzf .bad
	ld r1, [net_pn]
	eq r1, #3
	bzf .last
	b .bad
.last:
	ld r0, [net_pv]
	st [net_ip]+r1, r0
	mov r0, #1
	pop pcl
	pop pch
.bad:
	xor r0, r0
	pop pcl
	pop pch

; print the 4 bytes at net_ptr as a dotted quad
net_print_quad:
	xor r0, r0
	st [net_pi], r0
.loop:
	ld r1, [net_pi]
	ldd r0, [net_ptr]+r1
	push pch
	push pcl
	b str_printuint8
	ld r1, [net_pi]
	add r1, #1
	st [net_pi], r1
	eq r1, #4
	bzf .done
	mov r0, #46
	push pch
	push pcl
	b print_ascii_char
	b .loop
.done:
	pop pcl
	pop pch

; print net_u16 in decimal (net_u16 is used up)
net_print_u16:
	xor r0, r0
	st [net_pi], r0
	st [net_pz], r0
.power:
	ld r1, [net_pi]
	eq r1, #8
	bzf .last
	ld r0, [net_pow]+r1
	st [net_t16], r0
	add r1, #1
	ld r0, [net_pow]+r1
	st [net_t16+1], r0
	xor r0, r0
	st [net_pc], r0
.sub:
	push pch
	push pcl
	b net_ge16
	eq r0, #0
	bzf .digit
	push pch
	push pcl
	b net_sub16
	ld r0, [net_pc]
	add r0, #1
	st [net_pc], r0
	b .sub
.digit:
	ld r0, [net_pc]
	ld r1, [net_pz]
	or r1, r0			; a digit other than 0 printed yet
	st [net_pz], r1
	eq r1, #0
	bzf .skip
	add r0, #48
	push pch
	push pcl
	b print_ascii_char
.skip:
	ld r1, [net_pi]
	add r1, #2
	st [net_pi], r1
	b .power
.last:
	ld r0, [net_u16]
	add r0, #48
	push pch
	push pcl
	b print_ascii_char
	pop pcl
	pop pch

; ------------------------------------------------------------ the command line

; word r0 of the typed line (0 is "net") into net_wbuf, NUL-terminated, and
; its length into net_wlen (0, there is no such word)
net_word:
	st [net_want], r0
	xor r0, r0
	st [net_si], r0
	st [net_wn], r0
	st [net_wlen], r0
	st [net_wbuf], r0
.skip:
	ld r1, [net_si]
	ldd r1, [net_line]+r1
	eq r1, #0
	bzf .end
	gt r1, #32
	bzf .word
	ld r0, [net_si]
	add r0, #1
	st [net_si], r0
	b .skip
.word:
	xor r0, r0
	st [net_di], r0
.copy:
	ld r1, [net_si]
	ldd r1, [net_line]+r1
	gt r1, #32
	bzf .char
	b .word_end
.char:
	st [net_ch], r1
	ld r0, [net_si]
	add r0, #1
	st [net_si], r0
	ld r0, [net_wn]
	ld r1, [net_want]
	eq r0, r1
	bzf .keep
	b .copy
.keep:
	ld r1, [net_di]
	eq r1, #63
	bzf .copy			; too long, the rest is dropped
	ld r0, [net_ch]
	st [net_wbuf]+r1, r0
	add r1, #1
	st [net_di], r1
	b .copy
.word_end:
	ld r0, [net_wn]
	ld r1, [net_want]
	eq r0, r1
	bzf .found
	add r0, #1
	st [net_wn], r0
	b .skip
.found:
	ld r1, [net_di]
	st [net_wlen], r1
	xor r0, r0
	st [net_wbuf]+r1, r0
.end:
	pop pcl
	pop pch

; r0 = 1 when net_wbuf is the string at r0 (high), r1 (low), else 0
net_wordis:
	st [net_ptr+1], r0
	st [net_ptr], r1
	xor r0, r0
	st [net_ri], r0
.loop:
	ld r1, [net_ri]
	ldd r0, [net_ptr]+r1
	st [net_rb], r0
	ld r0, [net_wbuf]+r1
	ld r1, [net_rb]
	eq r0, r1
	bzf .same
	xor r0, r0
	pop pcl
	pop pch
.same:
	eq r0, #0
	bzf .equal
	ld r0, [net_ri]
	add r0, #1
	st [net_ri], r0
	b .loop
.equal:
	mov r0, #1
	pop pcl
	pop pch

; word r0 of the line as a dotted quad into net_ip- r0 = 1 when it is one
net_word_ip:
	push pch
	push pcl
	b net_word
	mov r0, #<[net_wbuf]
	st [net_ptr], r0
	mov r0, #>[net_wbuf]
	st [net_ptr+1], r0
	push pch
	push pcl
	b net_parse_ip
	pop pcl
	pop pch

; word r0 of the line as a number into net_u16- r0 = 1 when it is one
net_word_u16:
	push pch
	push pcl
	b net_word
	mov r0, #<[net_wbuf]
	st [net_ptr], r0
	mov r0, #>[net_wbuf]
	st [net_ptr+1], r0
	push pch
	push pcl
	b net_parse_u16
	pop pcl
	pop pch

; word 2 of the line (the host) into net_host and net_hlen- r0 = its length
net_word_host:
	mov r0, #2
	push pch
	push pcl
	b net_word
	xor r1, r1
.copy:
	ld r0, [net_wbuf]+r1
	st [net_host]+r1, r0
	add r1, #1
	eq r0, #0
	bzf .done
	b .copy
.done:
	ld r0, [net_wlen]
	st [net_hlen], r0
	pop pcl
	pop pch

; send net_wlen, then the bytes of net_wbuf (a length-prefixed string)
net_send_word:
	ld r0, [net_wlen]
	push pch
	push pcl
	b net_send
	xor r0, r0
	st [net_di], r0
.loop:
	ld r1, [net_di]
	ld r0, [net_wlen]
	eq r1, r0
	bzf .done
	ld r0, [net_wbuf]+r1
	add r1, #1
	st [net_di], r1
	push pch
	push pcl
	b net_send
	b .loop
.done:
	pop pcl
	pop pch

; send the NUL-terminated string at net_ptr
net_send_str:
.loop:
	ldd r0, [net_ptr]
	eq r0, #0
	bzf .done
	push pch
	push pcl
	b net_send
	push pch
	push pcl
	b net_ptr_inc
	b .loop
.done:
	pop pcl
	pop pch

; send the NUL-terminated string at net_ptr as len8 and its bytes (up to 63)
net_send_pstr:
	xor r1, r1
.len:
	ldd r0, [net_ptr]+r1
	eq r0, #0
	bzf .counted
	eq r1, #63
	bzf .counted
	add r1, #1
	b .len
.counted:
	st [net_count], r1
	mov r0, r1
	push pch
	push pcl
	b net_send
	push pch
	push pcl
	b net_sendp
	pop pcl
	pop pch

; print the IPv4 address at net_buf+2 (NET_STATUS's ip[4]), and a new line
net_print_ip:
	mov r0, #<[net_buf+2]
	st [net_ptr], r0
	mov r0, #>[net_buf+2]
	st [net_ptr+1], r0
	push pch
	push pcl
	b net_print_quad
	mov r0, #10
	push pch
	push pcl
	b print_ascii_char
	pop pcl
	pop pch

; NET_STATUS into net_buf, state, rssi, ip[4], gw[4], dns[4]
net_status:
	mov r0, #<[net_f_status]
	st [net_ptr], r0
	mov r0, #>[net_f_status]
	st [net_ptr+1], r0
	mov r0, #1
	st [net_count], r0
	push pch
	push pcl
	b net_frame
	mov r0, #14
	st [net_count], r0
	push pch
	push pcl
	b net_read
	pop pcl
	pop pch

; EVENTS into net_buf- count, then (code, sock) pairs
net_events:
	mov r0, #<[net_f_events]
	st [net_ptr], r0
	mov r0, #>[net_f_events]
	st [net_ptr+1], r0
	mov r0, #1
	st [net_count], r0
	push pch
	push pcl
	b net_frame
	mov r0, #33
	st [net_count], r0
	push pch
	push pcl
	b net_read
	pop pcl
	pop pch

; print what error r0 (NET_E_*, 1-12) means- its message is the r0th of the
; strings from net_s_nocard on
net_print_err:
	st [net_pn], r0
	mov r0, #<[net_s_nocard]
	st [net_ptr], r0
	mov r0, #>[net_s_nocard]
	st [net_ptr+1], r0
.skip:
	ld r0, [net_pn]
	sub r0, #1
	st [net_pn], r0
	eq r0, #0
	bzf .print
.to_nul:
	ldd r0, [net_ptr]
	st [net_rb], r0
	push pch
	push pcl
	b net_ptr_inc
	ld r0, [net_rb]
	eq r0, #0
	bzf .skip
	b .to_nul
.print:
	ld r0, [net_ptr+1]
	ld r1, [net_ptr]
	push pch
	push pcl
	b str_printstr
	pop pcl
	pop pch

; ------------------------------------------------------------ the command

; net                     the link, up and its address, or down
; net join SSID PASSWORD  join, keep the credentials (the card joins them at power-up)
; net get HOST [PORT]     an HTTP/1.0 GET of / (port 80 unless given); prints the reply
; net lookup NAME         the address the DNS client (resolv.s) finds
; net ping HOST [COUNT]   ICMP echo (ping.s)
; net config ...          the card's IP and DNS settings
net_cmd:
	push pch
	push pcl
	b net_ready
	eq r0, #0
	bzf .ready
	push pch
	push pcl
	b net_print_err
	b .done
.ready:
	mov r0, #1
	push pch
	push pcl
	b net_word
	ld r0, [net_wlen]
	eq r0, #0
	bzf .status
	mov r0, #>[net_w_join]
	mov r1, #<[net_w_join]
	push pch
	push pcl
	b net_wordis
	eq r0, #1
	bzf .join
	mov r0, #>[net_w_get]
	mov r1, #<[net_w_get]
	push pch
	push pcl
	b net_wordis
	eq r0, #1
	bzf .get
	mov r0, #>[net_w_lookup]
	mov r1, #<[net_w_lookup]
	push pch
	push pcl
	b net_wordis
	eq r0, #1
	bzf .lookup
	mov r0, #>[net_w_ping]
	mov r1, #<[net_w_ping]
	push pch
	push pcl
	b net_wordis
	eq r0, #1
	bzf .ping
	mov r0, #>[net_w_config]
	mov r1, #<[net_w_config]
	push pch
	push pcl
	b net_wordis
	eq r0, #1
	bzf .config
	b .usage

.join:
	push pch
	push pcl
	b net_c_join
	b .done
.get:
	push pch
	push pcl
	b net_c_get
	b .done
.lookup:
	push pch
	push pcl
	b net_c_lookup
	b .done
.ping:
	push pch
	push pcl
	b net_c_ping
	b .done
.config:
	push pch
	push pcl
	b net_c_config
	b .done

.status:
	push pch
	push pcl
	b net_status
	mov r0, #>[net_s_link]
	mov r1, #<[net_s_link]
	push pch
	push pcl
	b str_printstr
	ld r0, [net_buf]
	eq r0, #2
	bzf .status_up
	mov r0, #>[net_s_down]
	mov r1, #<[net_s_down]
	push pch
	push pcl
	b str_printstr
	b .done
.status_up:
	mov r0, #>[net_s_up]
	mov r1, #<[net_s_up]
	push pch
	push pcl
	b str_printstr
	push pch
	push pcl
	b net_print_ip
	b .done
.usage:
	mov r0, #NET_E_BADARG
	push pch
	push pcl
	b net_print_err
.done:
	pop pcl
	pop pch

; ---------------------------------------------------- net join SSID PASSWORD
net_c_join:
	mov r0, #4			; JOIN ssid, psk, save
	push pch
	push pcl
	b net_begin
	mov r0, #2
	push pch
	push pcl
	b net_word
	push pch
	push pcl
	b net_send_word
	mov r0, #3
	push pch
	push pcl
	b net_word
	push pch
	push pcl
	b net_send_word
	mov r0, #1			; save
	push pch
	push pcl
	b net_send
	push pch
	push pcl
	b net_cs_off

	; wait for the link (NET_STATUS byte 0 = 2)
	mov r0, #0
	st [net_retry], r0
	st [net_retry+1], r0
.link_wait:
	push pch
	push pcl
	b net_status
	ld r0, [net_buf]
	eq r0, #2
	bzf .link_up
	push pch
	push pcl
	b net_backoff
	ld r0, [net_retry+1]
	eq r0, #NET_TIMEOUT
	bzf .timeout
	b .link_wait
.link_up:
	mov r0, #>[net_s_joined]
	mov r1, #<[net_s_joined]
	push pch
	push pcl
	b str_printstr
	push pch
	push pcl
	b net_print_ip
	pop pcl
	pop pch
.timeout:
	mov r0, #NET_E_TIMEOUT
	push pch
	push pcl
	b net_print_err
	pop pcl
	pop pch

; ---------------------------------------------------- net lookup NAME
net_c_lookup:
	push pch
	push pcl
	b net_word_host
	eq r0, #0
	bzf .usage
	push pch
	push pcl
	b net_resolve
	eq r0, #0
	bzf .found
	push pch
	push pcl
	b net_print_err
	pop pcl
	pop pch
.found:
	mov r0, #10
	push pch
	push pcl
	b print_ascii_char
	mov r0, #>[net_host]
	mov r1, #<[net_host]
	push pch
	push pcl
	b str_printstr
	mov r0, #32
	push pch
	push pcl
	b print_ascii_char
	mov r0, #<[net_ip]
	st [net_ptr], r0
	mov r0, #>[net_ip]
	st [net_ptr+1], r0
	push pch
	push pcl
	b net_print_quad
	mov r0, #10
	push pch
	push pcl
	b print_ascii_char
	pop pcl
	pop pch
.usage:
	mov r0, #NET_E_BADARG
	push pch
	push pcl
	b net_print_err
	pop pcl
	pop pch

; ---------------------------------------------------- net get HOST [PORT]
; the host is resolved by the kernel's DNS client (a dotted quad is used as
; it is), then CONNECT to that address
net_c_get:
	push pch
	push pcl
	b net_word_host
	eq r0, #0
	bzf .usage

	; the port, 80, or the third word
	mov r0, #80
	st [net_port], r0
	xor r0, r0
	st [net_port+1], r0
	mov r0, #3
	push pch
	push pcl
	b net_word
	ld r0, [net_wlen]
	eq r0, #0
	bzf .port_done
	mov r0, #3
	push pch
	push pcl
	b net_word_u16
	eq r0, #0
	bzf .usage
	ld r0, [net_u16]
	st [net_port], r0
	ld r0, [net_u16+1]
	st [net_port+1], r0
.port_done:
	push pch
	push pcl
	b net_resolve
	eq r0, #0
	bzf .resolved
	b .error

.resolved:
	; drop old events, then OPEN TCP
	push pch
	push pcl
	b net_events
	xor r0, r0
	push pch
	push pcl
	b net_open
	eq r0, #0
	bzf .opened
	b .error
.opened:

	; CONNECT socket, address, port
	mov r0, #0x11
	push pch
	push pcl
	b net_begin
	ld r0, [net_sock]
	push pch
	push pcl
	b net_send
	mov r0, #<[net_ip]
	st [net_ptr], r0
	mov r0, #>[net_ip]
	st [net_ptr+1], r0
	mov r0, #4
	st [net_count], r0
	push pch
	push pcl
	b net_sendp
	ld r0, [net_port]
	push pch
	push pcl
	b net_send
	ld r0, [net_port+1]
	push pch
	push pcl
	b net_send
	push pch
	push pcl
	b net_cs_off

	; wait for CONNECTED ($10) or CONN_FAILED ($11) on the socket
	mov r0, #0
	st [net_retry], r0
	st [net_retry+1], r0
.conn_wait:
	push pch
	push pcl
	b net_events
	xor r1, r1
.event:
	ld r0, [net_buf]		; count
	add r0, r0			; two bytes each
	lt r1, r0
	bzf .event_check
	b .no_event
.event_check:
	st [net_ri], r1
	add r1, #1
	ld r0, [net_buf+1]+r1		; the socket
	ld r1, [net_sock]
	eq r0, r1
	bzf .ours
.next_event:
	ld r1, [net_ri]
	add r1, #2
	b .event
.ours:
	ld r1, [net_ri]
	ld r0, [net_buf+1]+r1		; the code
	eq r0, #16
	bzf .connected
	eq r0, #17
	bzf .failed
	b .next_event
.no_event:
	push pch
	push pcl
	b net_backoff
	ld r0, [net_retry+1]
	eq r0, #NET_TIMEOUT
	bzf .timeout
	b .conn_wait
.connected:

	; SEND "GET / HTTP/1.0\r\nHost, HOST\r\n\r\n"
	mov r0, #20
	push pch
	push pcl
	b net_begin
	ld r0, [net_sock]
	push pch
	push pcl
	b net_send
	ld r0, [net_hlen]
	add r0, #26			; 22 before the host, 4 after
	push pch
	push pcl
	b net_send
	mov r0, #<[net_s_get1]
	st [net_ptr], r0
	mov r0, #>[net_s_get1]
	st [net_ptr+1], r0
	push pch
	push pcl
	b net_send_str
	mov r0, #<[net_host]
	st [net_ptr], r0
	mov r0, #>[net_host]
	st [net_ptr+1], r0
	push pch
	push pcl
	b net_send_str
	mov r0, #<[net_s_get2]
	st [net_ptr], r0
	mov r0, #>[net_s_get2]
	st [net_ptr+1], r0
	push pch
	push pcl
	b net_send_str
	push pch
	push pcl
	b net_cs_off
	mov r0, #10
	push pch
	push pcl
	b print_ascii_char

	; print what arrives until the server closes (or nothing comes for ~2 s)
	mov r0, #0
	st [net_retry], r0
	st [net_retry+1], r0
.rx_wait:
	mov r0, #22			; SOCK_STATUS
	ld r1, [net_sock]
	push pch
	push pcl
	b net_op2
	mov r0, #5
	st [net_count], r0
	push pch
	push pcl
	b net_read
	ld r0, [net_buf+1]		; rx_avail, low byte
	eq r0, #0
	bzf .rx_empty
	b .rx_data
.rx_empty:
	ld r0, [net_buf+2]
	eq r0, #0
	bzf .rx_none
	b .rx_data
.rx_none:
	ld r0, [net_buf]
	eq r0, #4			; the server closed and everything is read
	bzf .rx_done
	eq r0, #0
	bzf .rx_done
	push pch
	push pcl
	b net_backoff
	ld r0, [net_retry+1]
	eq r0, #NET_TIMEOUT
	bzf .rx_done
	b .rx_wait
.rx_data:
	mov r0, #21			; RECV socket, 60 bytes
	push pch
	push pcl
	b net_begin
	ld r0, [net_sock]
	push pch
	push pcl
	b net_send
	mov r0, #60
	push pch
	push pcl
	b net_send
	push pch
	push pcl
	b net_cs_off
	mov r0, #61
	st [net_count], r0
	push pch
	push pcl
	b net_read
	xor r0, r0
	st [net_tmp+1], r0
.print:
	ld r1, [net_tmp+1]
	ld r0, [net_buf]		; byte 0 is the count
	lt r1, r0
	bzf .print_one
	b .rx_wait
.print_one:
	ld r1, [net_tmp+1]
	add r1, #1
	ld r0, [net_buf]+r1
	push pch
	push pcl
	b print_ascii_char
	ld r1, [net_tmp+1]
	add r1, #1
	st [net_tmp+1], r1
	b .print
.rx_done:
	push pch
	push pcl
	b net_close
	pop pcl
	pop pch

.failed:
	push pch
	push pcl
	b net_close
	mov r0, #>[net_s_failed]
	mov r1, #<[net_s_failed]
	push pch
	push pcl
	b str_printstr
	pop pcl
	pop pch
.timeout:
	push pch
	push pcl
	b net_close
	mov r0, #NET_E_TIMEOUT
	b .error
.usage:
	mov r0, #NET_E_BADARG
.error:
	push pch
	push pcl
	b net_print_err
	pop pcl
	pop pch

; ---------------------------------------------------- net config ...
; net config                 the settings
; net config dns IP [PORT]   this DNS server (port 53 unless given)
; net config ip IP MASK GW   a static address
; net config dhcp            an address from DHCP
; net config save            keep the settings on the card (applied at power-up)
net_c_config:
	push pch
	push pcl
	b net_cfg_get
	eq r0, #0
	bzf .got
	b .error
.got:
	xor r0, r0
	st [net_cfg+19], r0		; not saved, unless "save"
	mov r0, #2
	push pch
	push pcl
	b net_word
	ld r0, [net_wlen]
	eq r0, #0
	bzf .show
	mov r0, #>[net_w_dns]
	mov r1, #<[net_w_dns]
	push pch
	push pcl
	b net_wordis
	eq r0, #1
	bzf .dns
	mov r0, #>[net_w_ip]
	mov r1, #<[net_w_ip]
	push pch
	push pcl
	b net_wordis
	eq r0, #1
	bzf .ip
	mov r0, #>[net_w_dhcp]
	mov r1, #<[net_w_dhcp]
	push pch
	push pcl
	b net_wordis
	eq r0, #1
	bzf .dhcp
	mov r0, #>[net_w_save]
	mov r1, #<[net_w_save]
	push pch
	push pcl
	b net_wordis
	eq r0, #1
	bzf .save
	b .usage

.dns:
	mov r0, #3
	push pch
	push pcl
	b net_word_ip
	eq r0, #0
	bzf .usage
	xor r1, r1
.dns_copy:
	ld r0, [net_ip]+r1
	st [net_cfg+13]+r1, r0
	add r1, #1
	eq r1, #4
	bzf .dns_port
	b .dns_copy
.dns_port:
	mov r0, #53
	st [net_cfg+17], r0
	xor r0, r0
	st [net_cfg+18], r0
	mov r0, #4
	push pch
	push pcl
	b net_word
	ld r0, [net_wlen]
	eq r0, #0
	bzf .set
	mov r0, #4
	push pch
	push pcl
	b net_word_u16
	eq r0, #0
	bzf .usage
	ld r0, [net_u16]
	st [net_cfg+17], r0
	ld r0, [net_u16+1]
	st [net_cfg+18], r0
	b .set

.ip:
	mov r0, #3			; address, mask, gateway- words 3, 4, 5 into net_cfg 1, 5, 9
	st [net_wi], r0
.ip_word:
	ld r0, [net_wi]
	push pch
	push pcl
	b net_word_ip
	eq r0, #0
	bzf .usage
	ld r0, [net_wi]		; net_cfg + 4 * (word - 3) + 1
	sub r0, #3
	shl r0, #2
	add r0, #1
	st [net_pv], r0
	xor r1, r1
.ip_copy:
	ld r0, [net_ip]+r1
	push r1
	ld r1, [net_pv]
	st [net_cfg]+r1, r0
	add r1, #1
	st [net_pv], r1
	pop r1
	add r1, #1
	eq r1, #4
	bzf .ip_next
	b .ip_copy
.ip_next:
	ld r0, [net_wi]
	add r0, #1
	st [net_wi], r0
	eq r0, #6
	bzf .ip_done
	b .ip_word
.ip_done:
	mov r0, #1
	st [net_cfg], r0
	b .set

.dhcp:
	xor r0, r0
	st [net_cfg], r0
	b .set

.save:
	mov r0, #1
	st [net_cfg+19], r0

.set:
	push pch
	push pcl
	b net_cfg_set
	push pch
	push pcl
	b net_cfg_get
	eq r0, #0
	bzf .show
	b .error

	; mode dhcp | mode static, ip A mask M gw G
	; dns from dhcp | dns A, port P
	; saved | not saved
.show:
	mov r0, #>[net_s_mode]
	mov r1, #<[net_s_mode]
	push pch
	push pcl
	b str_printstr
	ld r0, [net_cfg]
	eq r0, #1
	bzf .static
	mov r0, #>[net_s_dhcp]
	mov r1, #<[net_s_dhcp]
	push pch
	push pcl
	b str_printstr
	b .show_dns
.static:
	mov r0, #>[net_s_static]
	mov r1, #<[net_s_static]
	push pch
	push pcl
	b str_printstr
	mov r0, #<[net_cfg+1]
	st [net_ptr], r0
	mov r0, #>[net_cfg+1]
	st [net_ptr+1], r0
	push pch
	push pcl
	b net_print_quad
	mov r0, #>[net_s_mask]
	mov r1, #<[net_s_mask]
	push pch
	push pcl
	b str_printstr
	mov r0, #<[net_cfg+5]
	st [net_ptr], r0
	mov r0, #>[net_cfg+5]
	st [net_ptr+1], r0
	push pch
	push pcl
	b net_print_quad
	mov r0, #>[net_s_gw]
	mov r1, #<[net_s_gw]
	push pch
	push pcl
	b str_printstr
	mov r0, #<[net_cfg+9]
	st [net_ptr], r0
	mov r0, #>[net_cfg+9]
	st [net_ptr+1], r0
	push pch
	push pcl
	b net_print_quad
.show_dns:
	mov r0, #>[net_s_dns]
	mov r1, #<[net_s_dns]
	push pch
	push pcl
	b str_printstr
	ld r0, [net_cfg+13]
	ld r1, [net_cfg+14]
	or r0, r1
	ld r1, [net_cfg+15]
	or r0, r1
	ld r1, [net_cfg+16]
	or r0, r1
	eq r0, #0
	bzf .dns_dhcp
	mov r0, #<[net_cfg+13]
	st [net_ptr], r0
	mov r0, #>[net_cfg+13]
	st [net_ptr+1], r0
	push pch
	push pcl
	b net_print_quad
	b .show_port
.dns_dhcp:
	mov r0, #>[net_s_fromdhcp]
	mov r1, #<[net_s_fromdhcp]
	push pch
	push pcl
	b str_printstr
.show_port:
	mov r0, #>[net_s_port]
	mov r1, #<[net_s_port]
	push pch
	push pcl
	b str_printstr
	ld r0, [net_cfg+17]
	st [net_u16], r0
	ld r0, [net_cfg+18]
	st [net_u16+1], r0
	push pch
	push pcl
	b net_print_u16
	ld r0, [net_cfg+19]
	eq r0, #0
	bzf .not_saved
	mov r0, #>[net_s_saved]
	mov r1, #<[net_s_saved]
	b .show_end
.not_saved:
	mov r0, #>[net_s_notsaved]
	mov r1, #<[net_s_notsaved]
.show_end:
	push pch
	push pcl
	b str_printstr
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

; count one more try in the 16-bit net_retry; callers give up once the high
; byte reaches NET_TIMEOUT (64*256 tries, ~2s at 12MHz)
net_backoff:
	ld r0, [net_retry]
	add r0, #1
	st [net_retry], r0
	eq r0, #0
	bzf .carry
	b .done
.carry:
	ld r0, [net_retry+1]
	add r0, #1
	st [net_retry+1], r0
.done:
	pop pcl
	pop pch

; ------------------------------------------------------------ the net API
;
; Group 5 of the kernel API (kernel/api.s, doc/proposals/kernel-api.md).
; Called like any kernel routine (push pch, push pcl, b API_NET_...). Small
; arguments in r0 and r1, the rest in API_ARGS ($6f00) - pointers and 16-bit
; numbers little-endian, addresses most significant byte first. On return r0
; is 0 or an error, NET_E_* above (also left in API_ERR, $6f20), and r1 is a
; result where the entry says so. Every entry returns NET_E_NOCARD (1)
; without a Wi-Fi card and NET_E_POWER (2) on a USB source under 3 A.
; Sockets are the card's, 0-3 (doc/hardware/wifi-card.md). The asynchronous
; ones (join, connect, connect_host, listen's clients) finish with an event-
; drain them with api_net_events (the card holds IRQ_n while any wait, so a
; program can WAI for them).

; the common start- keeps r0, r1 in net_a0, net_a1. When the card cannot be
; used it returns the error to the entry's caller (not to the entry)
api_net_pre:
	st [net_a0], r0
	st [net_a1], r1
	push pch
	push pcl
	b net_ready
	eq r0, #0
	bzf .ready
	pop r1				; the entry's return address, dropped
	pop r1
	b api_net_out
.ready:
	pop pcl
	pop pch

; the common end- r0 into API_ERR, then back to the API's caller
api_net_out:
	st API_ERR, r0
	pop pcl
	pop pch

; status- NET_STATUS into API_ARGS- state (0 idle, 1 joining, 2 up, 3 failed),
; rssi, ip[4], gw[4], dns[4] (the lease). r1 = state
api_net_status:
	push pch
	push pcl
	b api_net_pre
	push pch
	push pcl
	b net_status
	xor r1, r1
.copy:
	ld r0, [net_buf]+r1
	st API_ARGS+r1, r0
	add r1, #1
	eq r1, #14
	bzf .done
	b .copy
.done:
	ld r1, [net_buf]
	xor r0, r0
	b api_net_out

; join- JOIN the network. API_ARGS+0 pointer to the SSID, +2 pointer to the
; password (NUL-terminated, up to 32 and 63 characters); r0 = 1 keeps them on
; the card (it joins them at power-up). Asynchronous- JOINED or JOIN_FAILED
api_net_join:
	push pch
	push pcl
	b api_net_pre
	mov r0, #4
	push pch
	push pcl
	b net_begin
	ld r0, $6f00
	st [net_ptr], r0
	ld r0, $6f01
	st [net_ptr+1], r0
	push pch
	push pcl
	b net_send_pstr
	ld r0, $6f02
	st [net_ptr], r0
	ld r0, $6f03
	st [net_ptr+1], r0
	push pch
	push pcl
	b net_send_pstr
	ld r0, [net_a0]
	push pch
	push pcl
	b net_send
	push pch
	push pcl
	b net_cs_off
	xor r0, r0
	b api_net_out

; open- OPEN a socket of type r0 (0 TCP, 1 UDP, 2 TLS, 3 ICMP). r1 = the
; socket; NET_E_NOSOCK when none is free
api_net_open:
	push pch
	push pcl
	b api_net_pre
	ld r0, [net_a0]
	push pch
	push pcl
	b net_open
	ld r1, [net_sock]
	b api_net_out

; connect- CONNECT socket r0 to API_ARGS+0 ip[4], +4 port16. Asynchronous-
; CONNECTED or CONN_FAILED
api_net_connect:
	push pch
	push pcl
	b api_net_pre
	mov r0, #0x11
	push pch
	push pcl
	b net_begin
	ld r0, [net_a0]
	push pch
	push pcl
	b net_send
	mov r0, #6
	b api_net_args_end

; send r0 bytes from API_ARGS, close the frame, return 0
api_net_args_end:
	st [net_count], r0
	mov r0, #0x00
	st [net_ptr], r0
	mov r0, #0x6f
	st [net_ptr+1], r0
	push pch
	push pcl
	b net_sendp
	push pch
	push pcl
	b net_cs_off
	xor r0, r0
	b api_net_out

; connect_host- CONNECT_HOST socket r0 to API_ARGS+0 port16, +2 pointer to the
; host name (NUL-terminated, up to 63). The card resolves it (and TLS checks
; the certificate against it). Asynchronous- CONNECTED or CONN_FAILED
api_net_connect_host:
	push pch
	push pcl
	b api_net_pre
	mov r0, #0x12
	push pch
	push pcl
	b net_begin
	ld r0, [net_a0]
	push pch
	push pcl
	b net_send
	ld r0, $6f00
	push pch
	push pcl
	b net_send
	ld r0, $6f01
	push pch
	push pcl
	b net_send
	ld r0, $6f02
	st [net_ptr], r0
	ld r0, $6f03
	st [net_ptr+1], r0
	push pch
	push pcl
	b net_send_pstr
	push pch
	push pcl
	b net_cs_off
	xor r0, r0
	b api_net_out

; listen- LISTEN on socket r0 (TCP), API_ARGS+0 port16. A client raises
; ACCEPTED and takes over the socket
api_net_listen:
	push pch
	push pcl
	b api_net_pre
	mov r0, #0x13
	b api_net_sock_port

; the frame opcode r0, socket net_a0, port API_ARGS+0; return 0
api_net_sock_port:
	push pch
	push pcl
	b net_begin
	ld r0, [net_a0]
	push pch
	push pcl
	b net_send
	mov r0, #2
	b api_net_args_end

; send- SEND r1 bytes (up to 255) on socket r0 from the pointer at API_ARGS+0.
; Check tx_free (sock_status) first- the card drops what does not fit
api_net_send:
	push pch
	push pcl
	b api_net_pre
	mov r0, #0x14
	push pch
	push pcl
	b net_begin
	ld r0, [net_a0]
	push pch
	push pcl
	b net_send
	ld r0, [net_a1]
	push pch
	push pcl
	b net_send
	ld r0, $6f00
	st [net_ptr], r0
	ld r0, $6f01
	st [net_ptr+1], r0
	ld r0, [net_a1]
	st [net_count], r0
	push pch
	push pcl
	b net_sendp
	push pch
	push pcl
	b net_cs_off
	xor r0, r0
	b api_net_out

; recv- RECV up to r1 bytes (1-250) from socket r0 into the buffer at
; API_ARGS+0. r1 = how many (0, nothing waiting)
api_net_recv:
	push pch
	push pcl
	b api_net_pre
	mov r0, #0x15
	push pch
	push pcl
	b net_begin
	ld r0, [net_a0]
	push pch
	push pcl
	b net_send
	ld r0, [net_a1]
	push pch
	push pcl
	b net_send
	push pch
	push pcl
	b net_cs_off
	mov r0, #1
	st [net_hn], r0
	ld r0, $6f00
	st [net_dst], r0
	ld r0, $6f01
	st [net_dst+1], r0
	b api_net_read_data

; READ the answer (net_hn header bytes to net_buf, then up to net_a1 bytes to
; net_dst); r1 = the data bytes kept, return 0
api_net_read_data:
	ld r0, [net_a1]
	st [net_cap], r0
	push pch
	push pcl
	b net_readp
	b api_net_count

; r1 = the data bytes of the answer net_readp read (RESP_LEN - net_hn, at most
; net_a1), return 0
api_net_count:
	ld r0, [net_rlen]
	ld r1, [net_hn]
	lt r0, r1
	bzf .none
	sub r0, r1
	ld r1, [net_a1]
	gt r0, r1
	bzf .capped
	mov r1, r0
	b .done
.none:
	xor r1, r1
	b .done
.capped:
	ld r1, [net_a1]
.done:
	xor r0, r0
	b api_net_out

; sock_status- SOCK_STATUS of socket r0 into API_ARGS- state (0 closed,
; 1 connecting, 2 open, 3 listening, 4 peer closed), rx_avail16, tx_free16.
; r1 = state
api_net_sock_status:
	push pch
	push pcl
	b api_net_pre
	mov r0, #0x16
	ld r1, [net_a0]
	push pch
	push pcl
	b net_op2
	mov r0, #5
	st [net_count], r0
	push pch
	push pcl
	b net_read
	xor r1, r1
.copy:
	ld r0, [net_buf]+r1
	st API_ARGS+r1, r0
	add r1, #1
	eq r1, #5
	bzf .done
	b .copy
.done:
	ld r1, [net_buf]
	xor r0, r0
	b api_net_out

; close- CLOSE socket r0
api_net_close:
	push pch
	push pcl
	b api_net_pre
	mov r0, #0x17
	ld r1, [net_a0]
	push pch
	push pcl
	b net_op2
	xor r0, r0
	b api_net_out

; udp_bind- UDP_BIND socket r0 (UDP) to the local port API_ARGS+0 port16
api_net_udp_bind:
	push pch
	push pcl
	b api_net_pre
	mov r0, #0x19
	b api_net_sock_port

; sendto- UDP_SENDTO r1 bytes (up to 255) on socket r0 (UDP or ICMP) to
; API_ARGS+0 ip[4], +4 port16 (ICMP- ignored), from the pointer at API_ARGS+6.
; On an ICMP socket the bytes are the whole ICMP message, checksum included
api_net_sendto:
	push pch
	push pcl
	b api_net_pre
	mov r0, #0x18
	push pch
	push pcl
	b net_begin
	ld r0, [net_a0]
	push pch
	push pcl
	b net_send
	mov r0, #0x00
	st [net_ptr], r0
	mov r0, #0x6f
	st [net_ptr+1], r0
	mov r0, #6
	st [net_count], r0
	push pch
	push pcl
	b net_sendp
	ld r0, [net_a1]
	push pch
	push pcl
	b net_send
	ld r0, $6f06
	st [net_ptr], r0
	ld r0, $6f07
	st [net_ptr+1], r0
	ld r0, [net_a1]
	st [net_count], r0
	push pch
	push pcl
	b net_sendp
	push pch
	push pcl
	b net_cs_off
	xor r0, r0
	b api_net_out

; recvfrom- RECVFROM one datagram (UDP; ICMP- one ICMP message) on socket r0,
; up to r1 bytes (1-248) into the buffer at API_ARGS+6. The sender goes to
; API_ARGS+0 ip[4], +4 port16. r1 = how many (0, nothing waiting); the rest
; of a longer datagram is lost
api_net_recvfrom:
	push pch
	push pcl
	b api_net_pre
	mov r0, #0x1a
	push pch
	push pcl
	b net_begin
	ld r0, [net_a0]
	push pch
	push pcl
	b net_send
	ld r0, [net_a1]
	push pch
	push pcl
	b net_send
	push pch
	push pcl
	b net_cs_off
	mov r0, #7
	st [net_hn], r0
	xor r0, r0			; nothing from nobody, unless the card says
	st [net_buf], r0
	st [net_buf+1], r0
	st [net_buf+2], r0
	st [net_buf+3], r0
	st [net_buf+4], r0
	st [net_buf+5], r0
	ld r0, $6f06
	st [net_dst], r0
	ld r0, $6f07
	st [net_dst+1], r0
	ld r0, [net_a1]
	st [net_cap], r0
	push pch
	push pcl
	b net_readp
	xor r1, r1
.copy:
	ld r0, [net_buf]+r1
	st API_ARGS+r1, r0
	add r1, #1
	eq r1, #6
	bzf .copied
	b .copy
.copied:
	b api_net_count

; events- EVENTS into the buffer at API_ARGS+0 (33 bytes)- count, then
; (code, socket) × count. r1 = count. Codes- wifi-card.md ($10 CONNECTED,
; $11 CONN_FAILED, $12 ACCEPTED, $13 PEER_CLOSED, $14 ERROR, ...)
api_net_events:
	push pch
	push pcl
	b api_net_pre
	push pch
	push pcl
	b net_events
	ld r0, $6f00
	st [net_dst], r0
	ld r0, $6f01
	st [net_dst+1], r0
	xor r1, r1
.copy:
	ld r0, [net_buf]+r1
	std [net_dst]+r1, r0
	add r1, #1
	eq r1, #33
	bzf .done
	b .copy
.done:
	ld r1, [net_buf]
	xor r0, r0
	b api_net_out

; resolve- the kernel's DNS client (resolv.s)- the name at the pointer in
; API_ARGS+0 (NUL-terminated, up to 63; a dotted quad is used as it is) to
; its address, API_ARGS+0 ip[4]. Errors- NET_E_NXDOMAIN, NET_E_NOANSWER (no A
; record), NET_E_DNSTIME (no answer, after one retry), NET_E_MALFORMED,
; NET_E_DNSERR (another RCODE), NET_E_NODNS (no server), NET_E_BADARG (not a
; name), NET_E_NOSOCK. Waits up to ~2 s
api_net_resolve:
	push pch
	push pcl
	b api_net_pre
	ld r0, $6f00
	st [net_ptr], r0
	ld r0, $6f01
	st [net_ptr+1], r0
	xor r1, r1
.copy:
	ldd r0, [net_ptr]+r1
	st [net_host]+r1, r0
	eq r0, #0
	bzf .copied
	add r1, #1
	eq r1, #64
	bzf .toolong
	b .copy
.toolong:
	mov r0, #NET_E_BADARG
	b api_net_out
.copied:
	st [net_hlen], r1
	push pch
	push pcl
	b net_resolve
	eq r0, #0
	bzf .found
	b api_net_out
.found:
	ld r0, [net_ip]
	st $6f00, r0
	ld r0, [net_ip+1]
	st $6f01, r0
	ld r0, [net_ip+2]
	st $6f02, r0
	ld r0, [net_ip+3]
	st $6f03, r0
	xor r0, r0
	b api_net_out

; config- r0 = 0 gets the card's settings (NET_CONFIG_GET) into API_ARGS,
; r0 = 1 sets them (NET_CONFIG) from API_ARGS- mode (0 DHCP, 1 static),
; ip[4], mask[4], gw[4], dns[4] (0.0.0.0 = DHCP's), dns_port16, and saved
; (get) or save (set- 1 keeps them on the card, applied at power-up)
api_net_config:
	push pch
	push pcl
	b api_net_pre
	ld r0, [net_a0]
	eq r0, #0
	bzf .get
	eq r0, #1
	bzf .set
	mov r0, #NET_E_BADARG
	b api_net_out
.set:
	xor r1, r1
.set_copy:
	ld r0, API_ARGS+r1
	st [net_cfg]+r1, r0
	add r1, #1
	eq r1, #20
	bzf .set_done
	b .set_copy
.set_done:
	push pch
	push pcl
	b net_cfg_set
	xor r0, r0
	b api_net_out
.get:
	push pch
	push pcl
	b net_cfg_get
	eq r0, #0
	bzf .got
	b api_net_out
.got:
	xor r1, r1
.get_copy:
	ld r0, [net_cfg]+r1
	st API_ARGS+r1, r0
	add r1, #1
	eq r1, #20
	bzf .get_done
	b .get_copy
.get_done:
	xor r0, r0
	b api_net_out
