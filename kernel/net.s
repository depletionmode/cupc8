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
net_f_join db 4, 5, 99, 117, 112, 99, 56, 8, 112, 97, 115, 115, 119, 111, 114, 100, 1
; NET_STATUS
net_f_status db 1
; OPEN TCP
net_f_open db 16, 0
; CONNECT_HOST socket 0, port 8088, "localhost"
net_f_connect db 18, 0, 152, 31, 9, 108, 111, 99, 97, 108, 104, 111, 115, 116
; SEND socket 0, "GET /\r\n"
net_f_get db 20, 0, 7, 71, 69, 84, 32, 47, 13, 10
; SOCK_STATUS socket 0
net_f_sockstat db 22, 0
; RECV socket 0, 60 bytes
net_f_recv db 21, 0, 60
; CLOSE socket 0
net_f_close db 23, 0

net_s_timeout db "\nnet timeout\n"
net_s_nocard db "\nno wifi card\n"
net_s_weak db "\nUSB power under 1.5A: net off\n"

net_spi: resb 1
net_tmp: resb 1
net_ptr: resb 2
net_count: resb 1
net_buf: resb 64
net_retry: resb 2

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

; READ frame- reads net_count response bytes into net_buf
net_read:
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
	b net_send			; RESP_LEN, ignored
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

; the "net" terminal command
net_cmd:
	ld r0, [net_spi]
	eq r0, #0xff
	bzf .no_card
	; the radio's bursts need a 1.5 A source (SYSCTL bit 1, doc/hardware/power.md)
	ld r0, $f203
	and r0, #2
	eq r0, #0
	bzf .weak

	; join
	mov r0, #<[net_f_join]
	st [net_ptr], r0
	mov r0, #>[net_f_join]
	st [net_ptr+1], r0
	mov r0, #17
	st [net_count], r0
	push pch
	push pcl
	b net_frame

	; wait for the link (NET_STATUS byte 0 = 2)
	mov r0, #0
	st [net_retry], r0
	st [net_retry+1], r0
.link_wait:
	mov r0, #<[net_f_status]
	st [net_ptr], r0
	mov r0, #>[net_f_status]
	st [net_ptr+1], r0
	mov r0, #1
	st [net_count], r0
	push pch
	push pcl
	b net_frame
	mov r0, #1
	st [net_count], r0
	push pch
	push pcl
	b net_read
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

	; open a socket and connect
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

	mov r0, #<[net_f_connect]
	st [net_ptr], r0
	mov r0, #>[net_f_connect]
	st [net_ptr+1], r0
	mov r0, #14
	st [net_count], r0
	push pch
	push pcl
	b net_frame

	; wait for the socket to open (SOCK_STATUS state = 2)
	mov r0, #0
	st [net_retry], r0
	st [net_retry+1], r0
.conn_wait:
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
	ld r0, [net_buf]
	eq r0, #2
	bzf .connected
	push pch
	push pcl
	b net_backoff
	ld r0, [net_retry+1]
	eq r0, #NET_TIMEOUT
	bzf .timeout
	b .conn_wait
.connected:

	; send the request
	mov r0, #<[net_f_get]
	st [net_ptr], r0
	mov r0, #>[net_f_get]
	st [net_ptr+1], r0
	mov r0, #10
	st [net_count], r0
	push pch
	push pcl
	b net_frame

	; wait for a reply
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
	ld r0, [net_buf+1]
	eq r0, #0
	bzf .no_data
	b .have_data
.no_data:
	push pch
	push pcl
	b net_backoff
	ld r0, [net_retry+1]
	eq r0, #NET_TIMEOUT
	bzf .timeout
	b .rx_wait
.have_data:

	; read it and print it
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
	ld r0, [net_buf]			; byte 0 is the count
	lt r1, r0
	bzf .print_one
	b .print_done
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
.print_done:

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

