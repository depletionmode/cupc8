; The kernel API: the jump table programs call (doc/proposals/kernel-api.md).
;
; This file sorts first among kernel/*.s, so the table follows the
; assembler's `b main` at $1000: 8 groups of 32 entries, 3 bytes each
; (`b routine`), $1003-$1302. Group g, entry n is at $1003 + 96g + 3n.
; kernel/api.inc names every entry for programs. Entries are only ever
; added, never moved: testKernelApi checks the table against api.inc, and
; every committed api.inc against this one.
;
; Calling: push pch / push pcl / b API_X, as any kernel routine; it returns
; with pop pcl / pop pch. Small arguments go in r0/r1; the rest, and
; pointers (low byte first), in API_ARGS. Results: r0 = 0 ok or an error
; code (also left in API_ERR), data in r1, API_ARGS or the caller's buffer.
; Calls that only print or draw return nothing (r0 and r1 changed). Every
; call may change r0, r1 and API_ARGS. Each routine's comment (sys.s) is
; its contract. An entry not implemented is `b api_none`: r0 = API_ERR = $ff.
; The bank entries (group 0, 4-7) are kernel/bank.s's routines as they are:
; their contracts are there, and they leave API_ERR alone.
;
; The API block, $6f00-$6fff, is at fixed addresses shared with programs.

%define API_ARGS $6f00
%define API_ERR $6f20
%define API_RUN $6f21

; ---------------------------------------------------------------- group 0: system ($1003)
	b api_version
	b api_exit
	b api_block
	b api_slots
	b api_bank_set
	b api_bank_get
	b api_bank_count
	b api_bank_far_copy
	b api_none
	b api_none
	b api_none
	b api_none
	b api_none
	b api_none
	b api_none
	b api_none
	b api_none
	b api_none
	b api_none
	b api_none
	b api_none
	b api_none
	b api_none
	b api_none
	b api_none
	b api_none
	b api_none
	b api_none
	b api_none
	b api_none
	b api_none
	b api_none
; ---------------------------------------------------------------- group 1: console ($1063)
	b api_putc
	b api_puts
	b api_getkey
	b api_pollkey
	b api_cls
	b api_gotoxy
	b api_getxy
	b api_attr
	b api_cursor
	b api_scroll
	b api_cleol
	b api_poke
	b api_none
	b api_none
	b api_none
	b api_none
	b api_none
	b api_none
	b api_none
	b api_none
	b api_none
	b api_none
	b api_none
	b api_none
	b api_none
	b api_none
	b api_none
	b api_none
	b api_none
	b api_none
	b api_none
	b api_none
; ---------------------------------------------------------------- group 2: graphics ($10c3)
	b api_gfx_mode
	b api_gfx_pixel
	b api_gfx_fill_rect
	b api_gfx_rect
	b api_gfx_line
	b api_gfx_palette
	b api_gfx_palette_reset
	b api_gfx_text8
	b api_gfx_vscroll
	b api_gfx_getpixel
	b api_gfx_vsync
	b api_none
	b api_none
	b api_none
	b api_none
	b api_none
	b api_none
	b api_none
	b api_none
	b api_none
	b api_none
	b api_none
	b api_none
	b api_none
	b api_none
	b api_none
	b api_none
	b api_none
	b api_none
	b api_none
	b api_none
	b api_none
; ---------------------------------------------------------------- group 3: e-ink ($1123)
	b api_eink_auto
	b api_eink_get
	b api_eink_status
	b api_eink_refresh
	b api_none
	b api_none
	b api_none
	b api_none
	b api_none
	b api_none
	b api_none
	b api_none
	b api_none
	b api_none
	b api_none
	b api_none
	b api_none
	b api_none
	b api_none
	b api_none
	b api_none
	b api_none
	b api_none
	b api_none
	b api_none
	b api_none
	b api_none
	b api_none
	b api_none
	b api_none
	b api_none
	b api_none
; ---------------------------------------------------------------- group 4: storage ($1183)
	b api_st_info
	b api_st_open
	b api_st_read
	b api_st_write
	b api_st_close
	b api_st_seek
	b api_st_dir_first
	b api_st_dir_next
	b api_st_delete
	b api_st_rename
	b api_none
	b api_none
	b api_none
	b api_none
	b api_none
	b api_none
	b api_none
	b api_none
	b api_none
	b api_none
	b api_none
	b api_none
	b api_none
	b api_none
	b api_none
	b api_none
	b api_none
	b api_none
	b api_none
	b api_none
	b api_none
	b api_none
; ---------------------------------------------------------------- group 5: net ($11e3)
	b api_net_status
	b api_net_join
	b api_net_open
	b api_net_connect
	b api_net_connect_host
	b api_net_listen
	b api_net_send
	b api_net_recv
	b api_net_sock_status
	b api_net_close
	b api_net_udp_bind
	b api_net_sendto
	b api_net_recvfrom
	b api_net_events
	b api_net_resolve
	b api_net_config
	b api_none
	b api_none
	b api_none
	b api_none
	b api_none
	b api_none
	b api_none
	b api_none
	b api_none
	b api_none
	b api_none
	b api_none
	b api_none
	b api_none
	b api_none
	b api_none
; ---------------------------------------------------------------- group 6: timers ($1243)
	b api_ticks
	b api_wait_ms
	b api_none
	b api_none
	b api_none
	b api_none
	b api_none
	b api_none
	b api_none
	b api_none
	b api_none
	b api_none
	b api_none
	b api_none
	b api_none
	b api_none
	b api_none
	b api_none
	b api_none
	b api_none
	b api_none
	b api_none
	b api_none
	b api_none
	b api_none
	b api_none
	b api_none
	b api_none
	b api_none
	b api_none
	b api_none
	b api_none
; ---------------------------------------------------------------- group 7: reserved ($12a3)
	b api_none
	b api_none
	b api_none
	b api_none
	b api_none
	b api_none
	b api_none
	b api_none
	b api_none
	b api_none
	b api_none
	b api_none
	b api_none
	b api_none
	b api_none
	b api_none
	b api_none
	b api_none
	b api_none
	b api_none
	b api_none
	b api_none
	b api_none
	b api_none
	b api_none
	b api_none
	b api_none
	b api_none
	b api_none
	b api_none
	b api_none
	b api_none
; ---------------------------------------------------------------- end of the table ($1303)

; not implemented - r0 = API_ERR = $ff
api_none:
	mov r0, #0xff
; the end of a call that returns a code - r0 into API_ERR, then back
api_ret:
	st API_ERR, r0
	pop pcl
	pop pch
