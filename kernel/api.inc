; CUPC/8 kernel API, for programs (doc/proposals/kernel-api.md).
;
; tools/mkprg.py puts this file in front of a program's source. Call an
; entry as any routine - push pch / push pcl / b API_PUTC - and it returns
; with pop pcl / pop pch. Small arguments in r0/r1, the rest and pointers
; (low byte first) in API_ARGS; r0 = 0 ok or an error code (also in
; API_ERR). Every call may change r0, r1 and API_ARGS. The contracts are
; in kernel/sys.s, bank.s (group 0, 4-7: they leave API_ERR alone) and
; net.s (group 5). An entry that does nothing yet returns r0 = $ff.
;
; Entries are only ever added: an address here never changes. Group g,
; entry n is at $1003 + 96g + 3n (32 entries a group).

; the API block ($6f00-$6fff): API_ARGS is 32 bytes, $6f00-$6f1f
%define API_ARGS $6f00
%define API_ERR $6f20
%define API_RUN $6f21
; the USB console's flags (usb-console.md): bit 0 set while a PC has the
; system card's console port open. The console group's output goes there too.
%define CON_FLAGS $6f26

; group 0: system ($1003)
%define API_VERSION $1003
%define API_EXIT $1006
%define API_BLOCK $1009
%define API_SLOTS $100c
%define API_BANK_SET $100f
%define API_BANK_GET $1012
%define API_BANK_COUNT $1015
%define API_BANK_FAR_COPY $1018

; group 1: console ($1063)
%define API_PUTC $1063
%define API_PUTS $1066
%define API_GETKEY $1069
%define API_POLLKEY $106c
%define API_CLS $106f
%define API_GOTOXY $1072
%define API_GETXY $1075
%define API_ATTR $1078
%define API_CURSOR $107b
%define API_SCROLL $107e
%define API_CLEOL $1081
%define API_POKE $1084

; group 2: graphics ($10c3)
%define API_GFX_MODE $10c3
%define API_GFX_PIXEL $10c6
%define API_GFX_FILL_RECT $10c9
%define API_GFX_RECT $10cc
%define API_GFX_LINE $10cf
%define API_GFX_PALETTE $10d2
%define API_GFX_PALETTE_RESET $10d5
%define API_GFX_TEXT8 $10d8
%define API_GFX_VSCROLL $10db
%define API_GFX_GETPIXEL $10de
%define API_GFX_VSYNC $10e1
; the e-ink card's native mode 2 (API_GFX_MODE 2): x16, y16 coordinates
%define API_GFX2_PIXEL $10e4
%define API_GFX2_FILL_RECT $10e7
%define API_GFX2_RECT $10ea
%define API_GFX2_LINE $10ed
%define API_GFX2_BLIT1 $10f0
%define API_GFX2_BLIT2 $10f3
%define API_GFX2_TEXT16 $10f6
%define API_GFX2_TEXT8 $10f9
%define API_GFX2_VSCROLL $10fc
%define API_GFX2_GETPIXEL $10ff

; group 3: e-ink ($1123)
%define API_EINK_AUTO $1123
%define API_EINK_GET $1126
%define API_EINK_STATUS $1129
%define API_EINK_REFRESH $112c

; group 4: storage ($1183)
%define API_ST_INFO $1183
%define API_ST_OPEN $1186
%define API_ST_READ $1189
%define API_ST_WRITE $118c
%define API_ST_CLOSE $118f
%define API_ST_SEEK $1192
%define API_ST_DIR_FIRST $1195
%define API_ST_DIR_NEXT $1198
%define API_ST_DELETE $119b
%define API_ST_RENAME $119e

; group 5: net ($11e3)
%define API_NET_STATUS $11e3
%define API_NET_JOIN $11e6
%define API_NET_OPEN $11e9
%define API_NET_CONNECT $11ec
%define API_NET_CONNECT_HOST $11ef
%define API_NET_LISTEN $11f2
%define API_NET_SEND $11f5
%define API_NET_RECV $11f8
%define API_NET_SOCK_STATUS $11fb
%define API_NET_CLOSE $11fe
%define API_NET_UDP_BIND $1201
%define API_NET_SENDTO $1204
%define API_NET_RECVFROM $1207
%define API_NET_EVENTS $120a
%define API_NET_RESOLVE $120d
%define API_NET_CONFIG $1210

; group 6: timers ($1243)
%define API_TICKS $1243
%define API_WAIT_MS $1246

; group 7: reserved ($12a3)
