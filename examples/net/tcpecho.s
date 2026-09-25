; TCP echo server- a user program for the kernel API (doc/proposals/kernel-api.md).
;
; Listens on TCP port 7007; every byte a client sends comes back. When the
; client closes, the next one is taken. Runs until reset (or until the card
; refuses a socket, when it returns to the terminal).
;
; Build- the API's names (kernel/api.inc) first, then this, for $7000:
;   python3 tools/mkprg.py examples/net/tcpecho.s -o build/tcpecho.prg
; Run- cupc8.py run build/tcpecho.prg (the system card), exec from the SD card,
; or tools/sim --cards:hdmi,io,wifi --run:build/tcpecho.prg. On the emulator,
; forward a host port to it (forward- tcp:PORT:7007).

%define ECHO_PORT_LO 95
%define ECHO_PORT_HI 27

sock: resb 1
count: resb 1
buf: resb 250

main:
	; a TCP socket, listening
	xor r0, r0
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
	b API_NET_LISTEN

.poll:
	; state, then how much is waiting (API_ARGS+0, +1, +2)
	ld r0, [sock]
	push pch
	push pcl
	b API_NET_SOCK_STATUS
	ld r0, $6f01
	ld r1, $6f02
	or r0, r1
	eq r0, #0
	bzf .idle

	; RECV what is there (up to 250), SEND it back
	mov r0, #<[buf]
	st $6f00, r0
	mov r0, #>[buf]
	st $6f01, r0
	ld r0, [sock]
	mov r1, #250
	push pch
	push pcl
	b API_NET_RECV
	eq r1, #0
	bzf .poll
	st [count], r1
	mov r0, #<[buf]
	st $6f00, r0
	mov r0, #>[buf]
	st $6f01, r0
	ld r0, [sock]
	ld r1, [count]
	push pch
	push pcl
	b API_NET_SEND
	b .poll

.idle:
	; the client gone (peer closed, or closed)- the next one
	ld r0, $6f00
	eq r0, #4
	bzf .next
	eq r0, #0
	bzf .next
	b .poll
.next:
	ld r0, [sock]
	push pch
	push pcl
	b API_NET_CLOSE
	b main
