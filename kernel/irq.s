; interrupt setup and default handlers
; vectors: $0010 keyb (slot IRQ), $0012 tmr0, $0014 tmr1, $0016 spi and the
; chipset's tick
;
; The kernel's clock is the chipset's millisecond counter (MS_COUNT,
; $f206-$f209, doc/hardware/memory-map.md); the CPU's timers are left to
; programs. The chipset's tick (IRQ_PEND bit 4, every 50 ms, on the SPI
; vector) wakes the WAI of the terminal's key wait, which looks at API_RUN
; (sys.s) each time.

; the vectors and the mask (again after a program: sys_restart)
irq_init:
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
	mov r0, #0x19			; slot IRQ, SPI, the tick
	st $f201, r0
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
	mov r0, #2
	st $f200, r0
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

; SPI complete and the tick share this vector; both only wake a WAI
irq_spi:
	push r0
	mov r0, #0x18
	st $f200, r0
	pop r0
	pop f
	pop pcl
	pop pch
