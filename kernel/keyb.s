; simple keyboard driver
; ps/2->spi taken care of by SoC

%define		SD_SPI_DEVICE		#2

keyb_read_char:
	; SoC returns 0xff if no new char in buffer
	; this call blocks until valid char returned
	push r1

	mov r1, SD_SPI_DEVICE
	mov r0, #255

.loop:
	push pch
	push pcl
	b spi_write
	push pch
	push pcl
	b spi_read
	eq r0, #255
	bzf .loop
	
.done:
	pop r1
	pop pcl
	pop pch
