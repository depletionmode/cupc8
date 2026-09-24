; kernel entry point
;
; The boot ROM has copied us here and left the slot table at $0002-$0007.

main:
	; switch the ROM windows off so $e000-$efff is RAM again
	mov r0, #1
	st $f203, r0

	; card drivers
	push pch
	push pcl
	b gpu_init

	push pch
	push pcl
	b keyb_init

	push pch
	push pcl
	b net_init

	push pch
	push pcl
	b storage_init

	push pch
	push pcl
	b irq_init

	; run terminal
	push pch
	push pcl
	b term_do

kernel_loop:
    wai
    b kernel_loop
