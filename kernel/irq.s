; interrupt setup and default handlers
; vectors: $0010 keyb, $0012 tmr0, $0014 tmr1, $0016 spi
;
; Timer 0 is the kernel's clock. It counts instructions, and while the CPU
; is parked in WAI one every 3 clocks, so it runs at no fixed rate. Each
; expiry (every TICK_COUNT counts) adds 1/16 ms while the kernel waits in
; WAI (tick_idle set: 250 x 3 clocks at 12 MHz is 62.5 us) and TICK_BUSY/16
; ms while it runs (250 instructions, about 14 clocks each). tick_ms, the ms
; since boot, is therefore about right (+-25%), not exact. The handler also
; counts tick_wait down once a ms (API_WAIT_MS), and wakes the WAI of the
; terminal's key wait, which looks at API_RUN (sys.s) each time.

%define TICK_COUNT 250
%define TICK_UNITS 16
%define TICK_BUSY 4

tick_idle: resb 1
tick_sub: resb 1
tick_ms: resb 4
tick_wait: resb 2

irq_init:
	xor r0, r0
	st [tick_idle], r0
	st [tick_sub], r0
	st [tick_ms], r0
	st [tick_ms+1], r0
	st [tick_ms+2], r0
	st [tick_ms+3], r0
	st [tick_wait], r0
	st [tick_wait+1], r0
; the vectors, the mask and the clock (again after a program: sys_restart)
irq_setup:
	mov r0, #<irq_keyb
	st $0010, r0
	mov r0, #>irq_keyb
	st $0011, r0
	mov r0, #<irq_tmr0
	st $0012, r0
	mov r0, #>irq_tmr0
	st $0013, r0
	mov r0, #<irq_tmr1
	st $0014, r0
	mov r0, #>irq_tmr1
	st $0015, r0
	mov r0, #<irq_spi
	st $0016, r0
	mov r0, #>irq_spi
	st $0017, r0
	mov r0, #11				; slot IRQ, timer 0, SPI
	st $f201, r0
	tmr0 #TICK_COUNT
	sti
	pop pcl
	pop pch

irq_keyb:
	push r0
	mov r0, #1
	st $f200, r0
	pop r0
	pop f
	pop pcl
	pop pch

irq_tmr0:
	push r0
	tmr0 #TICK_COUNT
	mov r0, #2
	st $f200, r0
	ld r0, [tick_idle]
	eq r0, #0
	bzf .busy
	ld r0, [tick_sub]
	add r0, #1
	b .add
.busy:
	ld r0, [tick_sub]
	add r0, #TICK_BUSY
.add:
	lt r0, #TICK_UNITS
	bzf .keep
	sub r0, #TICK_UNITS
	st [tick_sub], r0
	ld r0, [tick_ms]		; a ms more
	add r0, #1
	st [tick_ms], r0
	eq r0, #0
	bzf .c1
	b .wait
.c1:
	ld r0, [tick_ms+1]
	add r0, #1
	st [tick_ms+1], r0
	eq r0, #0
	bzf .c2
	b .wait
.c2:
	ld r0, [tick_ms+2]
	add r0, #1
	st [tick_ms+2], r0
	eq r0, #0
	bzf .c3
	b .wait
.c3:
	ld r0, [tick_ms+3]
	add r0, #1
	st [tick_ms+3], r0
.wait:
	ld r0, [tick_wait]		; tick_wait - 1, down to 0
	eq r0, #0
	bzf .lo0
	sub r0, #1
	st [tick_wait], r0
	b .out
.lo0:
	ld r0, [tick_wait+1]
	eq r0, #0
	bzf .out
	sub r0, #1
	st [tick_wait+1], r0
	mov r0, #0xff
	st [tick_wait], r0
	b .out
.keep:
	st [tick_sub], r0
.out:
	pop r0
	pop f
	pop pcl
	pop pch

irq_tmr1:
	push r0
	mov r0, #4
	st $f200, r0
	pop r0
	pop f
	pop pcl
	pop pch

irq_spi:
	push r0
	mov r0, #8
	st $f200, r0
	pop r0
	pop f
	pop pcl
	pop pch
