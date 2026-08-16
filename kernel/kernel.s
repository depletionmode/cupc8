; kernel entry point
main:
	push pch
	push pcl
	b irq_init

	; init drivers
	push pch
	push pcl
	b ili9340_init		; display driver

	; run terminal
	push pch
	push pcl
	b term_do

;    push pch
;    push pcl
;    b dump_char_rom

;	push pch
;	push pcl
;	b clr_screen

kernel_loop:
    wai
    b kernel_loop
