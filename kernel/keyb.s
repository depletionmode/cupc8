; simple keyboard driver
; ps/2->spi taken care of by SoC

%define		SD_SPI_DEVICE		#2

keyb_read_char:
	; poll once; if empty, wait for IRQ0 only (not our own SPI irq)
	push r1
	mov r1, SD_SPI_DEVICE

.loop:
	push pch
	push pcl
	b spi_read
	eq r0, #255
	bzf .idle
	b .done
.idle:
	mov r0, #1
	st $f201, r0
	wai
	mov r0, #9
	st $f201, r0
	b .loop

.done:
	pop r1
	pop pcl
	pop pch
