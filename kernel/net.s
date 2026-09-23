; Network driver - the Wi-Fi card (doc/hardware/wifi-card.md).
;
; The card runs the whole stack, so this is just framing- send a command
; frame, then a READ frame for the answer. The terminal's "net" command
; joins, connects to a server and prints what comes back.
;
; Frames are stored as byte blobs in .data and sent with net_frame.

%define SLOT_TABLE $0002
%define NET_CFG_DIV2 16
%define NET_TIMEOUT 64

; JOIN "cupc8" "password", save
; NET_STATUS
net_f_status db 1
; OPEN TCP
net_f_open db 16, 0
; SOCK_STATUS socket 0
net_f_sockstat db 22, 0
; RECV socket 0, 60 bytes
net_f_recv db 21, 0, 60
; CLOSE socket 0
net_f_close db 23, 0
; EVENTS
net_f_events db 31

net_s_usage db "\nnet join SSID PASSWORD | net get HOST [PORT] | net\n"
net_s_joined db "\njoined, address "
net_s_link db "\nlink "
net_s_up db "up, address "
net_s_down db "down\n"
net_s_failed db "\nconnect failed\n"
; "GET / HTTP/1.0" CR LF "Host" colon space, in numbers (the assembler has no \r)
net_s_get1 db 71, 69, 84, 32, 47, 32, 72, 84, 84, 80, 47, 49, 46, 48, 13, 10, 72, 111, 115, 116, 58, 32, 0
net_s_get2 db 13, 10, 13, 10, 0
net_s_timeout db "\nnet timeout\n"
net_s_nocard db "\nno wifi card\n"
net_s_weak db "\nUSB power under 1.5A: net off\n"

net_spi: resb 1
net_tmp: resb 1
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
net_ptmp: resb 2

net_init:
	mov r0, #0xff
	st [net_spi], r0
	xor r0, r0
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

; send the frame at net_ptr, net_count bytes
net_frame:
	push pch
	push pcl
	b net_cs_on
.loop:
	ld r0, [net_count]
	eq r0, #0
	bzf .done
	ldd r0, [net_ptr]
	push pch
	push pcl
	b net_send
	ld r0, [net_ptr]
	add r0, #1
	st [net_ptr], r0
	eq r0, #0
	bzf .carry
	b .next
.carry:
	ld r0, [net_ptr+1]
	add r0, #1
	st [net_ptr+1], r0
.next:
	ld r0, [net_count]
	sub r0, #1
	st [net_count], r0
	b .loop
.done:
	push pch
	push pcl
	b net_cs_off
	pop pcl
	pop pch

; READ frame- reads net_count response bytes into net_buf. RESP_LEN 0 means
; the answer is not ready yet (slot.md), so the READ is repeated, up to 255 times
net_read:
	xor r0, r0
	st [net_tries], r0
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
	b .ready
.not_ready:
	push pch
	push pcl
	b net_cs_off
	ld r0, [net_tries]
	add r0, #1
	st [net_tries], r0
	eq r0, #255
	bzf .ready_anyway
	b .again
.ready_anyway:
	push pch
	push pcl
	b net_cs_on
.ready:
	xor r0, r0
	st [net_tmp+1], r0
.loop:
	ld r0, [net_count]
	eq r0, #0
	bzf .done
	mov r0, #0
	push pch
	push pcl
	b net_send
	ld r1, [net_tmp+1]
	st [net_buf]+r1, r0
	add r1, #1
	st [net_tmp+1], r1
	ld r0, [net_count]
	sub r0, #1
	st [net_count], r0
	b .loop
.done:
	push pch
	push pcl
	b net_cs_off
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
	ld r0, [net_ptr]
	add r0, #1
	st [net_ptr], r0
	eq r0, #0
	bzf .carry
	b .loop
.carry:
	ld r0, [net_ptr+1]
	add r0, #1
	st [net_ptr+1], r0
	b .loop
.done:
	pop pcl
	pop pch

; print the IPv4 address at net_buf+2 (NET_STATUS's ip[4])
net_print_ip:
	xor r0, r0
	st [net_di], r0
.loop:
	ld r1, [net_di]
	ld r0, [net_buf+2]+r1
	push pch
	push pcl
	b str_printuint8
	ld r1, [net_di]
	add r1, #1
	st [net_di], r1
	eq r1, #4
	bzf .done
	mov r0, #46			; "."
	push pch
	push pcl
	b print_ascii_char
	b .loop
.done:
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

; ------------------------------------------------------------ the command

; net                     the link, up and its address, or down
; net join SSID PASSWORD  join, keep the credentials (the card joins them at power-up)
; net get HOST [PORT]     an HTTP/1.0 GET of / (port 80 unless given); prints the reply
net_cmd:
	ld r0, [net_spi]
	eq r0, #0xff
	bzf .no_card
	; the radio's bursts need a 1.5 A source (SYSCTL bit 1, doc/hardware/power.md)
	ld r0, $f203
	and r0, #2
	eq r0, #0
	bzf .weak

	mov r0, #1
	push pch
	push pcl
	b net_word
	ld r0, [net_wlen]
	eq r0, #0
	bzf .status
	ld r0, [net_wbuf]
	eq r0, #106			; "j"
	bzf .join
	eq r0, #103			; "g"
	bzf .get
	b .usage

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

	; ---------------------------------------------------- net join SSID PASSWORD
.join:
	push pch
	push pcl
	b net_cs_on
	mov r0, #4			; JOIN ssid, psk, save
	push pch
	push pcl
	b net_send
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
	b .done

	; ---------------------------------------------------- net get HOST [PORT]
.get:
	mov r0, #2
	push pch
	push pcl
	b net_word
	ld r0, [net_wlen]
	eq r0, #0
	bzf .usage
	; keep the host, net_wbuf is reused for the port
	xor r1, r1
.keep_host:
	ld r0, [net_wbuf]+r1
	st [net_host]+r1, r0
	add r1, #1
	eq r0, #0
	bzf .kept
	b .keep_host
.kept:
	ld r0, [net_wlen]
	st [net_hlen], r0

	; the port, 80, or the third word as a 16-bit decimal number
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
	xor r0, r0
	st [net_port], r0
	st [net_port+1], r0
	st [net_di], r0
.digit:
	ld r1, [net_di]
	ld r0, [net_wbuf]+r1
	lt r0, #48
	bzf .port_done
	gt r0, #57
	bzf .port_done
	sub r0, #48
	st [net_ch], r0
	; port = port * 10 + digit, port + 9 more copies of itself
	ld r0, [net_port]
	st [net_ptmp], r0
	ld r0, [net_port+1]
	st [net_ptmp+1], r0
	mov r0, #9
	st [net_wn], r0
.times10:
	ld r0, [net_port]
	ld r1, [net_ptmp]
	add r0, r1
	st [net_port], r0
	lt r0, r1
	bzf .t_carry
	b .t_high
.t_carry:
	ld r0, [net_port+1]
	add r0, #1
	st [net_port+1], r0
.t_high:
	ld r0, [net_port+1]
	ld r1, [net_ptmp+1]
	add r0, r1
	st [net_port+1], r0
	ld r0, [net_wn]
	sub r0, #1
	st [net_wn], r0
	eq r0, #0
	bzf .add_digit
	b .times10
.add_digit:
	ld r0, [net_port]
	ld r1, [net_ch]
	add r0, r1
	st [net_port], r0
	lt r0, r1
	bzf .d_carry
	b .d_next
.d_carry:
	ld r0, [net_port+1]
	add r0, #1
	st [net_port+1], r0
.d_next:
	ld r1, [net_di]
	add r1, #1
	st [net_di], r1
	b .digit
.port_done:

	; drop old events, then OPEN TCP
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
	mov r0, #<[net_f_open]
	st [net_ptr], r0
	mov r0, #>[net_f_open]
	st [net_ptr+1], r0
	mov r0, #2
	st [net_count], r0
	push pch
	push pcl
	b net_frame
	mov r0, #1
	st [net_count], r0
	push pch
	push pcl
	b net_read

	; CONNECT_HOST socket 0, port, host
	push pch
	push pcl
	b net_cs_on
	mov r0, #18
	push pch
	push pcl
	b net_send
	mov r0, #0
	push pch
	push pcl
	b net_send
	ld r0, [net_port]
	push pch
	push pcl
	b net_send
	ld r0, [net_port+1]
	push pch
	push pcl
	b net_send
	ld r0, [net_hlen]
	st [net_wlen], r0
	xor r1, r1
.host_back:
	ld r0, [net_host]+r1
	st [net_wbuf]+r1, r0
	add r1, #1
	eq r0, #0
	bzf .host_sent
	b .host_back
.host_sent:
	push pch
	push pcl
	b net_send_word
	push pch
	push pcl
	b net_cs_off

	; wait for CONNECTED ($10) or CONN_FAILED ($11)
	mov r0, #0
	st [net_retry], r0
	st [net_retry+1], r0
.conn_wait:
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
	xor r1, r1
.event:
	ld r0, [net_buf]		; count
	add r0, r0			; two bytes each
	lt r1, r0
	bzf .event_check
	b .no_event
.event_check:
	ld r0, [net_buf+1]+r1
	eq r0, #16
	bzf .connected
	eq r0, #17
	bzf .failed
	add r1, #2
	b .event
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
	push pch
	push pcl
	b net_cs_on
	mov r0, #20
	push pch
	push pcl
	b net_send
	mov r0, #0
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
	mov r0, #<[net_f_sockstat]
	st [net_ptr], r0
	mov r0, #>[net_f_sockstat]
	st [net_ptr+1], r0
	mov r0, #2
	st [net_count], r0
	push pch
	push pcl
	b net_frame
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
	mov r0, #<[net_f_recv]
	st [net_ptr], r0
	mov r0, #>[net_f_recv]
	st [net_ptr+1], r0
	mov r0, #3
	st [net_count], r0
	push pch
	push pcl
	b net_frame
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
	mov r0, #<[net_f_close]
	st [net_ptr], r0
	mov r0, #>[net_f_close]
	st [net_ptr+1], r0
	mov r0, #2
	st [net_count], r0
	push pch
	push pcl
	b net_frame
	b .done

.failed:
	mov r0, #>[net_s_failed]
	mov r1, #<[net_s_failed]
	push pch
	push pcl
	b str_printstr
	b .done
.usage:
	mov r0, #>[net_s_usage]
	mov r1, #<[net_s_usage]
	push pch
	push pcl
	b str_printstr
	b .done
.timeout:
	mov r0, #>[net_s_timeout]
	mov r1, #<[net_s_timeout]
	push pch
	push pcl
	b str_printstr
	b .done
.weak:
	mov r0, #>[net_s_weak]
	mov r1, #<[net_s_weak]
	push pch
	push pcl
	b str_printstr
	b .done
.no_card:
	mov r0, #>[net_s_nocard]
	mov r1, #<[net_s_nocard]
	push pch
	push pcl
	b str_printstr
.done:
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

