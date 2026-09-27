; httpd- a small web server, a user program for the kernel API
; (doc/proposals/kernel-api.md).
;
; Listens on TCP port 8080 and answers every request with INDEX.HTM from the
; SD card, read afresh each time (so an edited file shows on the next load);
; a 404 if it is not there. One client at a time- it reads the request
; through its blank line, logs the request line on the console, answers
; (HTTP/1.0, the connection closed after), then listens again. A client that
; sends nothing for 2 s is dropped. A key press ends it.
;
; The headers are kept with \n line ends (the assembler has no \r in
; strings); send_text makes each one CR LF as it goes out. The file's bytes
; go out as they are.
;
; Build- the API's names (kernel/api.inc) first, then this, for $7000:
;   python3 tools/mkprg.py examples/httpd/httpd.s -o build/HTTPD.PRG
; Run- exec "HTTPD.PRG" from the SD card (INDEX.HTM next to it), e.g.
; tools/sim --slots hdmi,io,wifi,storage --sd card.img; then browse to
; http://localhost:8080/ (the simulator's Wi-Fi card uses the host's sockets).

%define HTTP_PORT_LO 144
%define HTTP_PORT_HI 31
%define FILE_H 1

msg_hi db "\nhttpd: serving INDEX.HTM on port 8080. Press a key to stop.\n"
msg_nocard db "httpd: no Wi-Fi card (or no socket free)\n"
msg_busy db "httpd: cannot listen on port 8080\n"
msg_bye db "httpd: stopped\n"

file_name db "INDEX.HTM"

; each text is strings back to back, ended by an empty one
st_200 db "HTTP/1.0 200 OK\nContent-Type: text/html\nConnection: close\n\n"
st_200_end db ""
st_404 db "HTTP/1.0 404 Not Found\nContent-Type: text/html\nConnection: close\n\n<h1>404</h1><p>No INDEX.HTM on the SD card.</p>\n"
st_404_end db ""

sock: resb 1
waits: resb 1			; 10 ms steps with no request bytes
nl: resb 1			; line ends in a row: 2 is the end of the headers
logged: resb 1			; 1 once the request line is on the console
rxn: resb 1
rxi: resb 1
li: resb 1			; log_line's index
txn: resb 1
src: resb 2			; send_text's string
rxbuf: resb 251
txbuf: resb 250

main:
	mov r0, #<[msg_hi]
	mov r1, #>[msg_hi]
	push pch
	push pcl
	b puts

.listen:
	; a TCP socket, listening
	xor r0, r0
	push pch
	push pcl
	b API_NET_OPEN
	eq r0, #0
	bzf .opened
	mov r0, #<[msg_nocard]
	mov r1, #>[msg_nocard]
	push pch
	push pcl
	b puts
	pop pcl
	pop pch
.opened:
	st [sock], r1
	mov r0, #HTTP_PORT_LO
	st $6f00, r0
	mov r0, #HTTP_PORT_HI
	st $6f01, r0
	ld r0, [sock]
	push pch
	push pcl
	b API_NET_LISTEN
	eq r0, #0
	bzf .accept
	mov r0, #<[msg_busy]
	mov r1, #>[msg_busy]
	push pch
	push pcl
	b puts
	b .close_out

.accept:
	; a key ends it; else wait for a client (the socket goes open)
	push pch
	push pcl
	b API_POLLKEY
	eq r0, #0xff
	bzf .no_key
	mov r0, #<[msg_bye]
	mov r1, #>[msg_bye]
	push pch
	push pcl
	b puts
	b .close_out
.no_key:
	ld r0, [sock]
	push pch
	push pcl
	b API_NET_SOCK_STATUS
	eq r0, #0
	bzf .status_ok
	b .next
.status_ok:
	eq r1, #2
	bzf .client
	eq r1, #3
	bzf .still
	b .next
.still:
	mov r0, #10
	xor r1, r1
	push pch
	push pcl
	b API_WAIT_MS
	b .accept

.client:
	xor r0, r0
	st [waits], r0
	st [nl], r0
	st [logged], r0

.rx:
	ld r0, [sock]
	push pch
	push pcl
	b API_NET_SOCK_STATUS
	eq r0, #0
	bzf .rx_status
	b .next
.rx_status:
	; open (or peer closed with bytes still waiting: the card says open)
	eq r1, #2
	bzf .rx_open
	b .next
.rx_open:
	ld r0, $6f01
	ld r1, $6f02
	or r0, r1
	eq r0, #0
	bzf .rx_none

	mov r0, #<[rxbuf]
	st $6f00, r0
	mov r0, #>[rxbuf]
	st $6f01, r0
	ld r0, [sock]
	mov r1, #250
	push pch
	push pcl
	b API_NET_RECV
	st [rxn], r1
	xor r0, r0
	st [rxbuf]+r1, r0		; a NUL after the bytes, for log_line
	st [waits], r0

	ld r0, [logged]
	eq r0, #0
	bzf .log
	b .scan_from_0
.log:
	mov r0, #1
	st [logged], r0
	push pch
	push pcl
	b log_line

.scan_from_0:
	xor r0, r0
	st [rxi], r0
.scan:
	; the headers end at an empty line (CR LF CR LF, or LF LF)
	ld r1, [rxi]
	ld r0, [rxn]
	eq r0, r1
	bzf .rx
	ld r0, [rxbuf]+r1
	add r1, #1
	st [rxi], r1
	eq r0, #13
	bzf .scan
	eq r0, #10
	bzf .lf
	xor r0, r0
	st [nl], r0
	b .scan
.lf:
	ld r0, [nl]
	add r0, #1
	st [nl], r0
	eq r0, #2
	bzf .answer
	b .scan

.rx_none:
	; nothing yet- wait 10 ms, up to 200 times
	ld r0, [waits]
	add r0, #1
	st [waits], r0
	eq r0, #200
	bzf .next
	mov r0, #10
	xor r1, r1
	push pch
	push pcl
	b API_WAIT_MS
	b .rx

.answer:
	; INDEX.HTM, read afresh; a 404 without it
	mov r0, #<[file_name]
	st $6f00, r0
	mov r0, #>[file_name]
	st $6f01, r0
	mov r0, #FILE_H
	xor r1, r1
	push pch
	push pcl
	b API_ST_OPEN
	eq r0, #0
	bzf .found
	mov r0, #<[st_404]
	mov r1, #>[st_404]
	push pch
	push pcl
	b send_text
	b .next
.found:
	mov r0, #<[st_200]
	mov r1, #>[st_200]
	push pch
	push pcl
	b send_text
.file:
	; the file 128 bytes at a time, straight into txbuf and out
	mov r0, #<[txbuf]
	st $6f00, r0
	mov r0, #>[txbuf]
	st $6f01, r0
	mov r0, #FILE_H
	mov r1, #128
	push pch
	push pcl
	b API_ST_READ
	eq r0, #0
	bzf .read_ok
	b .file_end
.read_ok:
	eq r1, #0
	bzf .file_end
	st [txn], r1
	push pch
	push pcl
	b tx_flush
	b .file
.file_end:
	mov r0, #FILE_H
	push pch
	push pcl
	b API_ST_CLOSE

.next:
	; done with this client (or it went away)- listen again
	ld r0, [sock]
	push pch
	push pcl
	b API_NET_CLOSE
	b .listen

.close_out:
	ld r0, [sock]
	push pch
	push pcl
	b API_NET_CLOSE
	pop pcl
	pop pch

; the request line (rxbuf up to its line end) on the console
log_line:
	xor r1, r1
	st [li], r1
.loop:
	ld r1, [li]
	ld r0, [rxbuf]+r1
	eq r0, #13
	bzf .end
	eq r0, #10
	bzf .end
	eq r0, #0
	bzf .end
	add r1, #1
	st [li], r1
	push pch
	push pcl
	b API_PUTC
	b .loop
.end:
	mov r0, #10
	push pch
	push pcl
	b API_PUTC
	pop pcl
	pop pch

; send the text at r0 (low), r1 (high)- strings back to back, ended by an
; empty one- with each \n as CR LF
send_text:
	st [src], r0
	st [src+1], r1
	xor r0, r0
	st [txn], r0
.next:
	xor r1, r1
	ldd r0, [src]+r1
	eq r0, #0
	bzf .nul
	eq r0, #10
	bzf .lf
	push pch
	push pcl
	b tx_put
	b .step
.lf:
	mov r0, #13
	push pch
	push pcl
	b tx_put
	mov r0, #10
	push pch
	push pcl
	b tx_put
	b .step
.nul:
	; a NUL right after this one (an empty string) ends the text
	mov r1, #1
	ldd r0, [src]+r1
	eq r0, #0
	bzf .end
.step:
	ld r0, [src]
	add r0, #1
	st [src], r0
	eq r0, #0
	bzf .carry
	b .next
.carry:
	ld r0, [src+1]
	add r0, #1
	st [src+1], r0
	b .next
.end:
	push pch
	push pcl
	b tx_flush
	pop pcl
	pop pch

; byte r0 into txbuf; sent when 240 are there
tx_put:
	ld r1, [txn]
	st [txbuf]+r1, r0
	add r1, #1
	st [txn], r1
	lt r1, #240
	bzf .done
	push pch
	push pcl
	b tx_flush
.done:
	pop pcl
	pop pch

; SEND txbuf's txn bytes once the card has room for them (the card drops
; what does not fit); dropped if the client has gone
tx_flush:
	ld r0, [txn]
	eq r0, #0
	bzf .done
.wait:
	ld r0, [sock]
	push pch
	push pcl
	b API_NET_SOCK_STATUS
	eq r0, #0
	bzf .status_ok
	b .drop
.status_ok:
	eq r1, #2
	bzf .room
	eq r1, #4
	bzf .room
	b .drop
.room:
	; tx_free16 at API_ARGS+3
	ld r0, $6f04
	eq r0, #0
	bzf .low
	b .send
.low:
	ld r0, $6f03
	ld r1, [txn]
	lt r0, r1
	bzf .wait
.send:
	mov r0, #<[txbuf]
	st $6f00, r0
	mov r0, #>[txbuf]
	st $6f01, r0
	ld r0, [sock]
	ld r1, [txn]
	push pch
	push pcl
	b API_NET_SEND
.drop:
	xor r0, r0
	st [txn], r0
.done:
	pop pcl
	pop pch

puts:
	st $6f00, r0			; API_ARGS
	st $6f01, r1
	push pch
	push pcl
	b API_PUTS
	pop pcl
	pop pch
