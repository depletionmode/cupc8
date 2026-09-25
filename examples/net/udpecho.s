; UDP echo server- a user program for the kernel API (doc/proposals/kernel-api.md).
;
; Bound to UDP port 7007; every datagram (up to 248 bytes) goes back to
; whoever sent it. Runs until reset (or until the card refuses a socket,
; when it returns to the terminal).
;
; Build- the API's names (kernel/api.inc) first, then this, for $7000:
;   python3 tools/mkprg.py examples/net/udpecho.s -o build/udpecho.prg
; Run- cupc8.py run build/udpecho.prg (the system card), exec from the SD card,
; or tools/sim --cards:hdmi,io,wifi --run:build/udpecho.prg. On the emulator,
; forward a host port to it (forward- udp:PORT:7007).

%define ECHO_PORT_LO 95
%define ECHO_PORT_HI 27

sock: resb 1
buf: resb 248

main:
	; a UDP socket, bound to the port
	mov r0, #1
	push pch
	push pcl
	b API_NET_OPEN
	eq r0, #0
	bzf .opened
	pop pcl
	pop pch
.opened:
	st [sock], r1
	mov r0, #ECHO_PORT_LO
	st $6f00, r0
	mov r0, #ECHO_PORT_HI
	st $6f01, r0
	ld r0, [sock]
	push pch
	push pcl
	b API_NET_UDP_BIND

.poll:
	; RECVFROM- the sender into API_ARGS+0 (ip) and +4 (port), the data into buf
	mov r0, #<[buf]
	st $6f06, r0
	mov r0, #>[buf]
	st $6f07, r0
	ld r0, [sock]
	mov r1, #248
	push pch
	push pcl
	b API_NET_RECVFROM
	eq r1, #0
	bzf .poll
	; SENDTO the same address and port (still in API_ARGS), the same bytes
	ld r0, [sock]
	push pch
	push pcl
	b API_NET_SENDTO
	b .poll
