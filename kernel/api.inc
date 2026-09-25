; CUPC/8 kernel API, for programs (doc/proposals/kernel-api.md).
;
; tools/mkprg.py puts this file in front of a program's source. Call an
; entry as any routine - push pch / push pcl / b API_PUTC - and it returns
; with pop pcl / pop pch. Small arguments in r0/r1, the rest and pointers
; (low byte first) in API_ARGS; r0 = 0 ok or an error code (also in
; API_ERR). Every call may change r0, r1 and API_ARGS. The contracts are
; in kernel/sys.s. An entry that does nothing yet returns r0 = $ff.
;
; Entries are only ever added: an address here never changes. ($10DB is in
; upper case because as.py takes any line with a lower-case "db" for data.)

; the API block ($6f00-$6fff): API_ARGS is 32 bytes, $6f00-$6f1f
%define API_ARGS $6f00
%define API_ERR $6f20
%define API_RUN $6f21

; group 0: system
%define API_VERSION $1003
%define API_EXIT $1006
%define API_BLOCK $1009
%define API_SLOTS $100c
%define API_BANK_SET $100f
%define API_BANK_GET $1012
%define API_BANK_COUNT $1015
%define API_BANK_FAR_COPY $1018

; group 1: console
%define API_PUTC $1033
%define API_PUTS $1036
%define API_GETKEY $1039
%define API_POLLKEY $103c
%define API_CLS $103f
%define API_GOTOXY $1042
%define API_GETXY $1045
%define API_ATTR $1048
%define API_CURSOR $104b
%define API_SCROLL $104e
%define API_CLEOL $1051
%define API_POKE $1054

; group 2: graphics
%define API_GFX_MODE $1063
%define API_GFX_PIXEL $1066
%define API_GFX_FILL_RECT $1069
%define API_GFX_RECT $106c
%define API_GFX_LINE $106f
%define API_GFX_PALETTE $1072
%define API_GFX_PALETTE_RESET $1075
%define API_GFX_TEXT8 $1078
%define API_GFX_VSCROLL $107b
%define API_GFX_GETPIXEL $107e
%define API_GFX_VSYNC $1081

; group 3: e-ink
%define API_EINK_AUTO $1093
%define API_EINK_GET $1096
%define API_EINK_STATUS $1099
%define API_EINK_REFRESH $109c

; group 4: storage
%define API_ST_INFO $10c3
%define API_ST_OPEN $10c6
%define API_ST_READ $10c9
%define API_ST_WRITE $10cc
%define API_ST_CLOSE $10cf
%define API_ST_SEEK $10d2
%define API_ST_DIR_FIRST $10d5
%define API_ST_DIR_NEXT $10d8
%define API_ST_DELETE $10DB
%define API_ST_RENAME $10de

; group 5: net ($10f3)

; group 6: timers
%define API_TICKS $1123
%define API_WAIT_MS $1126

; group 7: reserved ($1153)
