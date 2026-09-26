; The slot SPI devices (memory-map.md, "SPI devices"): one byte each way.
; Each card driver's _send is this with its device.

spi_tmp: resb 1

; the byte r0 out to the device whose registers are at $f100 + r1 ($X0 for
; device X), the byte that came back in r0 and r1
spi_send:
	st [spi_tmp], r0
	mov r0, r1
	ld r1, [spi_tmp]
	st $f100+r0, r1
	mov r1, #1
	st $f102+r0, r1
.spi_wait:					; SPI_RX is only valid once SPI_STAT says done
	ld r1, $f103+r0
	eq r1, #0
	bzf .spi_wait
	ld r1, $f101+r0
	mov r0, r1
	pop pcl
	pop pch
