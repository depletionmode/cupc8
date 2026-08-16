; interrupt setup and default handlers
; vectors: $0010 keyb, $0012 tmr0, $0014 tmr1, $0016 spi

irq_init:
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
	mov r0, #1
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

irq_spi:
	push r0
	mov r0, #8
	st $f200, r0
	pop r0
	pop f
	pop pcl
	pop pch
