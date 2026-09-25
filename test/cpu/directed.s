; CPU-004..007: programs for soc/tb/tb_cpu_directed.vhd. The testbench plants
; `b <entry>` at the reset vector, so each section starts at its own label.
; tools/cpudirected.py assembles this and hands the labels to the testbench.
;
; $0200 is a scratch byte, $0300 records which handler ran, $0400 is a flag
; the testbench pokes to move a program on.

main:
	halt

; ---------------------------------------------------------------- CPU-004
rst_prog:
	mov r0, #0x12
	mov r1, #0x34
	sti
	tmr0 #5
	eq r0, #0x12
rst_loop:
	ld r0, $0200
	b rst_loop
rst_idle:
	b rst_idle

; ---------------------------------------------------------------- CPU-005
irq_prog:
	mov r0, #0x0f
	st $f201, r0
irq_loop:
	ld r0, $0400
	eq r0, #1
	bzf irq_sti
	b irq_loop
irq_sti:
	sti
irq_loop2:
	add r1, #1
	ld r0, $0200
	b irq_loop2

; handlers: note which one ran, clear its pending bit, return
h0:
	mov r0, #0x10
	st $0300, r0
	mov r0, #0x01
	st $f200, r0
	pop f
	pop pcl
	pop pch
h1:
	mov r0, #0x11
	st $0300, r0
	mov r0, #0x02
	st $f200, r0
	pop f
h1_ret:
	pop pcl
	pop pch
h2:
	mov r0, #0x12
	st $0300, r0
	mov r0, #0x04
	st $f200, r0
	pop f
	pop pcl
	pop pch
h3:
	mov r0, #0x13
	st $0300, r0
	mov r0, #0x08
	st $f200, r0
	pop f
	pop pcl
	pop pch

; timer 0 falls due as POP pcl retires: the IRQ waits for the POP pch
; after it (the two are one return), so it returns to irq_ret_back
irq_ret_prog:
	mov r0, #0x02
	st $f201, r0
	sti
	tmr0 #5
	push pch
	push pcl
	b irq_ret_f
irq_ret_back:
	mov r0, #0x55
	st $0301, r0
irq_ret_done:
	b irq_ret_done
irq_ret_f:
	pop pcl
	pop pch

; ---------------------------------------------------------------- CPU-006
tmr_prog:
	tmr0 #3
	nop
tmr_fire:
	nop
	nop
	nop
tmr_self:
	tmr0 #1
	nop
	tmr1 #2
	tmr1 #0
	nop
	nop
	nop
	nop
	nop
	halt

; timers count while parked in WAI (the timer IRQ wakes it); the testbench
; pokes the count into $0200 first
tmr_wai:
	mov r0, #0x02
	st $f201, r0
	ld r1, $0200
	sti
	tmr0 r1
	wai
tmr_woke:
	halt

; ---------------------------------------------------------------- CPU-007
wai_nop:
	cli
	wai
	mov r0, #0x77
wai_nop_done:
	halt

wai_park:
	sti
	wai
wai_after:
	mov r0, #0x66
wai_park_done:
	halt

halt_prog:
	mov r0, #0x0f
	st $f201, r0
	sti
halt_here:
	halt
	mov r0, #0x99
