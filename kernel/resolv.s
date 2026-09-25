; DNS client (RFC 1035) in CUPC/8 assembly- doc/proposals/kernel-api.md,
; "Networking". The card's own RESOLVE is not used.
;
; net_resolve turns the name in net_host into net_ip. A dotted quad is used
; as it is. Otherwise it asks the configured server (net config dns- the
; card's NET_CONFIG_GET), or the one DHCP gave (NET_STATUS), over a UDP socket
; of its own- one A question, RD set, a new id each time. It waits about a
; second (ping.s's net_waited, on the chipset's millisecond counter) for the answer and asks once more. A datagram from
; another address or port, with another id, or that is not a response is
; ignored. The answer's questions are skipped and its answers walked- names
; followed through compression pointers, every length checked against the
; datagram- for the first A record of class IN.
;
; r0 = 0 (net_ip is the address), or NET_E_NXDOMAIN (RCODE 3), NET_E_DNSERR
; (another RCODE), NET_E_NOANSWER (no A record), NET_E_MALFORMED,
; NET_E_DNSTIME (no answer), NET_E_NODNS, NET_E_BADARG (not a name- an empty
; label, one over 63), NET_E_NOSOCK, NET_E_FAILED (the card did not answer).

dns_srv: resb 4
dns_port: resb 2
dns_id: resb 2                  ; the last query's (RAM junk at power-up is a fine start)
dns_q: resb 96                  ; the query- 12 + up to 65 + 4
dns_qlen: resb 1
dns_try: resb 1
dns_t0: resb 2
dns_n: resb 1                   ; the answer- its length (in net_pkt)
dns_off: resb 1                 ;   where the walk is
dns_left: resb 1                ;   questions, then answers, left
dns_rd: resb 1                  ;   an answer's RDLENGTH
dns_p: resb 1                   ; dns_name
dns_end: resb 1
dns_jumps: resb 1
dns_c: resb 1
dns_i: resb 1                   ; dns_build
dns_o: resb 1
dns_l: resb 1
dns_err: resb 1

net_resolve:
	mov r0, #<[net_host]
	st [net_ptr], r0
	mov r0, #>[net_host]
	st [net_ptr+1], r0
	push pch
	push pcl
	b net_parse_ip
	eq r0, #1
	bzf .quad

	; the server- configured, or DHCP's
	push pch
	push pcl
	b net_cfg_get
	eq r0, #0
	bzf .cfg
	pop pcl
	pop pch
.cfg:
	xor r1, r1
.srv_copy:
	ld r0, [net_cfg+13]+r1
	st [dns_srv]+r1, r0
	add r1, #1
	eq r1, #4
	bzf .srv_port
	b .srv_copy
.srv_port:
	ld r0, [net_cfg+17]
	st [dns_port], r0
	ld r0, [net_cfg+18]
	st [dns_port+1], r0
	push pch
	push pcl
	b dns_srv_zero
	eq r0, #1
	bzf .dhcp
	b .port
.dhcp:
	push pch
	push pcl
	b net_status
	xor r1, r1
.dhcp_copy:
	ld r0, [net_buf+10]+r1
	st [dns_srv]+r1, r0
	add r1, #1
	eq r1, #4
	bzf .dhcp_done
	b .dhcp_copy
.dhcp_done:
	push pch
	push pcl
	b dns_srv_zero
	eq r0, #1
	bzf .nodns
.port:
	ld r0, [dns_port]
	ld r1, [dns_port+1]
	or r0, r1
	eq r0, #0
	bzf .port53
	b .build
.port53:
	mov r0, #53
	st [dns_port], r0
.build:
	push pch
	push pcl
	b dns_build
	eq r0, #0
	bzf .built
	pop pcl
	pop pch
.built:
	mov r0, #1			; UDP
	push pch
	push pcl
	b net_open
	eq r0, #0
	bzf .opened
	pop pcl
	pop pch
.opened:
	xor r0, r0
	st [dns_try], r0

.ask:
	ld r0, [dns_id]
	add r0, #1
	st [dns_id], r0
	st [dns_q+1], r0
	eq r0, #0
	bzf .id_carry
	b .id_done
.id_carry:
	ld r0, [dns_id+1]
	add r0, #1
	st [dns_id+1], r0
.id_done:
	ld r0, [dns_id+1]
	st [dns_q], r0
	push pch
	push pcl
	b dns_send
	push pch
	push pcl
	b net_now
	ld r0, [net_u16]
	st [dns_t0], r0
	ld r0, [net_u16+1]
	st [dns_t0+1], r0
.poll:
	push pch
	push pcl
	b dns_recv
	eq r0, #0
	bzf .waited
	push pch
	push pcl
	b dns_parse
	eq r0, #0xff			; not the answer- keep waiting
	bzf .waited
	b .finish
.waited:
	ld r0, [dns_t0]
	st [net_t16], r0
	ld r0, [dns_t0+1]
	st [net_t16+1], r0
	push pch
	push pcl
	b net_waited
	eq r0, #1
	bzf .again
	b .poll
.again:
	ld r0, [dns_try]
	add r0, #1
	st [dns_try], r0
	eq r0, #2
	bzf .no_answer
	b .ask
.no_answer:
	mov r0, #NET_E_DNSTIME
.finish:
	st [dns_err], r0
	push pch
	push pcl
	b net_close
	ld r0, [dns_err]
	pop pcl
	pop pch
.nodns:
	mov r0, #NET_E_NODNS
	pop pcl
	pop pch
.quad:
	xor r0, r0
	pop pcl
	pop pch

; r0 = 1 when dns_srv is 0.0.0.0
dns_srv_zero:
	ld r0, [dns_srv]
	ld r1, [dns_srv+1]
	or r0, r1
	ld r1, [dns_srv+2]
	or r0, r1
	ld r1, [dns_srv+3]
	or r0, r1
	eq r0, #0
	bzf .zero
	xor r0, r0
	pop pcl
	pop pch
.zero:
	mov r0, #1
	pop pcl
	pop pch

; the query for net_host into dns_q (all but the id), its length dns_qlen-
; r0 = 0, or NET_E_BADARG
dns_build:
	xor r0, r0
	xor r1, r1
.zero:
	st [dns_q]+r1, r0
	add r1, #1
	eq r1, #12
	bzf .header
	b .zero
.header:
	mov r0, #1
	st [dns_q+2], r0		; RD
	st [dns_q+5], r0		; QDCOUNT 1
	; the name- each label, its length then its bytes
	xor r0, r0
	st [dns_i], r0
	st [dns_l], r0
	mov r0, #12
	st [dns_o], r0
.char:
	ld r1, [dns_i]
	ld r0, [net_host]+r1
	st [dns_c], r0
	eq r0, #46			; a dot
	bzf .label_end
	eq r0, #0
	bzf .label_end
	ld r0, [dns_l]
	add r0, #1
	st [dns_l], r0
	eq r0, #64
	bzf .bad
	ld r1, [dns_o]
	add r1, r0
	ld r0, [dns_c]
	st [dns_q]+r1, r0
	b .next
.label_end:
	ld r0, [dns_l]
	eq r0, #0
	bzf .empty
	ld r1, [dns_o]
	st [dns_q]+r1, r0
	add r1, r0
	add r1, #1
	st [dns_o], r1
	xor r0, r0
	st [dns_l], r0
	ld r0, [dns_c]
	eq r0, #0
	bzf .name_end
	b .next
.empty:
	; only the end may be empty, after a name's last dot ("a.b.")
	ld r0, [dns_c]
	eq r0, #0
	bzf .end_ok
	b .bad
.end_ok:
	ld r0, [dns_o]
	eq r0, #12
	bzf .bad
	b .name_end
.next:
	ld r0, [dns_i]
	add r0, #1
	st [dns_i], r0
	b .char
.name_end:
	ld r1, [dns_o]
	xor r0, r0
	st [dns_q]+r1, r0		; the root
	add r1, #1
	st [dns_q]+r1, r0		; QTYPE 1, A
	add r1, #1
	mov r0, #1
	st [dns_q]+r1, r0
	add r1, #1
	xor r0, r0
	st [dns_q]+r1, r0		; QCLASS 1, IN
	add r1, #1
	mov r0, #1
	st [dns_q]+r1, r0
	add r1, #1
	st [dns_qlen], r1
	xor r0, r0
	pop pcl
	pop pch
.bad:
	mov r0, #NET_E_BADARG
	pop pcl
	pop pch

; UDP_SENDTO the query to the server
dns_send:
	mov r0, #0x18
	push pch
	push pcl
	b net_begin
	ld r0, [net_sock]
	push pch
	push pcl
	b net_send
	mov r0, #<[dns_srv]
	st [net_ptr], r0
	mov r0, #>[dns_srv]
	st [net_ptr+1], r0
	mov r0, #6			; the address and the port after it
	st [net_count], r0
	push pch
	push pcl
	b net_sendp
	ld r0, [dns_qlen]
	push pch
	push pcl
	b net_send
	mov r0, #<[dns_q]
	st [net_ptr], r0
	mov r0, #>[dns_q]
	st [net_ptr+1], r0
	ld r0, [dns_qlen]
	st [net_count], r0
	push pch
	push pcl
	b net_sendp
	push pch
	push pcl
	b net_cs_off
	pop pcl
	pop pch

; RECVFROM a datagram (up to 248 bytes) into net_pkt, its length dns_n-
; r0 = 1 when one came from the server's address and port, else 0
dns_recv:
	mov r0, #0x1a
	push pch
	push pcl
	b net_begin
	ld r0, [net_sock]
	push pch
	push pcl
	b net_send
	mov r0, #248
	push pch
	push pcl
	b net_send
	push pch
	push pcl
	b net_cs_off
	mov r0, #7
	st [net_hn], r0
	mov r0, #248
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
	st [dns_n], r0
	xor r1, r1
.from:
	ld r0, [net_buf]+r1		; the address and port, as dns_srv, dns_port
	st [net_rb], r0
	ld r0, [dns_srv]+r1
	push r1
	ld r1, [net_rb]
	eq r0, r1
	pop r1
	bzf .same
	b .no
.same:
	add r1, #1
	eq r1, #6
	bzf .yes
	b .from
.yes:
	mov r0, #1
	pop pcl
	pop pch
.no:
	xor r0, r0
	pop pcl
	pop pch

; the answer in net_pkt (dns_n bytes)- r0 = 0 and net_ip, an error, or $ff
; when it is not the answer to the query (another id, or not a response)
dns_parse:
	ld r0, [dns_n]
	lt r0, #12
	bzf .bad
	ld r0, [net_pkt]
	ld r1, [dns_q]
	eq r0, r1
	bzf .id_hi
	b .not_ours
.id_hi:
	ld r0, [net_pkt+1]
	ld r1, [dns_q+1]
	eq r0, r1
	bzf .id_lo
	b .not_ours
.id_lo:
	ld r0, [net_pkt+2]
	and r0, #0x80			; QR, a response
	eq r0, #0
	bzf .not_ours
	ld r0, [net_pkt+3]
	and r0, #15			; RCODE
	eq r0, #0
	bzf .rcode_ok
	eq r0, #3
	bzf .nxdomain
	mov r0, #NET_E_DNSERR
	pop pcl
	pop pch
.nxdomain:
	mov r0, #NET_E_NXDOMAIN
	pop pcl
	pop pch
.rcode_ok:
	ld r0, [net_pkt+4]		; QDCOUNT and ANCOUNT over 255 cannot fit
	eq r0, #0
	bzf .counts
	b .bad
.counts:
	ld r0, [net_pkt+6]
	eq r0, #0
	bzf .counts_ok
	b .bad
.counts_ok:
	mov r0, #12
	st [dns_off], r0
	ld r0, [net_pkt+5]
	st [dns_left], r0
.question:
	ld r0, [dns_left]
	eq r0, #0
	bzf .answers
	push pch
	push pcl
	b dns_name
	eq r0, #0
	bzf .q_name
	pop pcl
	pop pch
.q_name:
	ld r0, [dns_n]			; QTYPE and QCLASS- 4 bytes
	ld r1, [dns_off]
	sub r0, r1
	lt r0, #4
	bzf .bad
	add r1, #4
	st [dns_off], r1
	ld r0, [dns_left]
	sub r0, #1
	st [dns_left], r0
	b .question

.answers:
	ld r0, [net_pkt+7]
	st [dns_left], r0
.answer:
	ld r0, [dns_left]
	eq r0, #0
	bzf .none
	push pch
	push pcl
	b dns_name
	eq r0, #0
	bzf .a_name
	pop pcl
	pop pch
.a_name:
	ld r0, [dns_n]			; TYPE, CLASS, TTL, RDLENGTH- 10 bytes
	ld r1, [dns_off]
	sub r0, r1
	lt r0, #10
	bzf .bad
	add r1, #8
	ld r0, [net_pkt]+r1		; RDLENGTH over 255 cannot fit
	eq r0, #0
	bzf .rdlen
	b .bad
.rdlen:
	add r1, #1
	ld r0, [net_pkt]+r1
	st [dns_rd], r0
	add r1, #1
	st [dns_off], r1
	ld r0, [dns_n]			; the data must be inside
	sub r0, r1
	ld r1, [dns_rd]
	lt r0, r1
	bzf .bad
	; TYPE 1 (A), CLASS 1 (IN), 4 bytes
	ld r0, [dns_rd]
	eq r0, #4
	bzf .is_a
	b .skip
.is_a:
	ld r1, [dns_off]
	sub r1, #10
	ld r0, [net_pkt]+r1
	eq r0, #0
	bzf .type_lo
	b .skip
.type_lo:
	add r1, #1
	ld r0, [net_pkt]+r1
	eq r0, #1
	bzf .class_hi
	b .skip
.class_hi:
	add r1, #1
	ld r0, [net_pkt]+r1
	eq r0, #0
	bzf .class_lo
	b .skip
.class_lo:
	add r1, #1
	ld r0, [net_pkt]+r1
	eq r0, #1
	bzf .found
.skip:
	ld r0, [dns_off]
	ld r1, [dns_rd]
	add r0, r1
	st [dns_off], r0
	ld r0, [dns_left]
	sub r0, #1
	st [dns_left], r0
	b .answer
.found:
	ld r1, [dns_off]
	ld r0, [net_pkt]+r1
	st [net_ip], r0
	add r1, #1
	ld r0, [net_pkt]+r1
	st [net_ip+1], r0
	add r1, #1
	ld r0, [net_pkt]+r1
	st [net_ip+2], r0
	add r1, #1
	ld r0, [net_pkt]+r1
	st [net_ip+3], r0
	xor r0, r0
	pop pcl
	pop pch
.none:
	mov r0, #NET_E_NOANSWER
	pop pcl
	pop pch
.not_ours:
	mov r0, #0xff
	pop pcl
	pop pch
.bad:
	mov r0, #NET_E_MALFORMED
	pop pcl
	pop pch

; the name at dns_off in net_pkt- walked label by label, through compression
; pointers (at most 16), every label and pointer inside the dns_n bytes.
; dns_off moves past it (past its first pointer, if it has one). r0 = 0, or
; NET_E_MALFORMED
dns_name:
	xor r0, r0
	st [dns_end], r0		; 0- not yet known (a name never ends before 12)
	st [dns_jumps], r0
	ld r0, [dns_off]
	st [dns_p], r0
.label:
	ld r1, [dns_p]
	ld r0, [dns_n]
	lt r1, r0
	bzf .inside
	b .bad
.inside:
	ld r0, [net_pkt]+r1
	eq r0, #0
	bzf .root
	st [dns_c], r0
	and r0, #0xc0
	eq r0, #0xc0
	bzf .pointer
	eq r0, #0
	bzf .plain
	b .bad				; $40 and $80 are not defined
.plain:
	ld r0, [dns_n]			; the label's bytes inside- length < n - p
	sub r0, r1
	ld r1, [dns_c]
	lt r1, r0
	bzf .label_ok
	b .bad
.label_ok:
	ld r0, [dns_p]
	add r0, r1
	add r0, #1
	st [dns_p], r0
	b .label
.pointer:
	ld r0, [dns_c]			; an offset over 255 is past any answer here
	and r0, #0x3f
	eq r0, #0
	bzf .near
	b .bad
.near:
	add r1, #1			; the pointer's second byte inside
	ld r0, [dns_n]
	lt r1, r0
	bzf .target
	b .bad
.target:
	ld r0, [dns_end]
	eq r0, #0
	bzf .mark
	b .follow
.mark:
	mov r0, r1
	add r0, #1
	st [dns_end], r0
.follow:
	ld r0, [net_pkt]+r1
	st [dns_p], r0
	ld r0, [dns_jumps]
	add r0, #1
	st [dns_jumps], r0
	eq r0, #17
	bzf .bad
	b .label
.root:
	ld r0, [dns_end]
	eq r0, #0
	bzf .in_place
	b .done
.in_place:
	add r1, #1
	st [dns_end], r1
.done:
	ld r0, [dns_end]
	st [dns_off], r0
	xor r0, r0
	pop pcl
	pop pch
.bad:
	mov r0, #NET_E_MALFORMED
	pop pcl
	pop pch
