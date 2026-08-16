; Display SPI status register reads as ready (1). Keyboard has no key (0).
main:
	ld r0, $f103
	st $2000, r0
	ld r1, $f123
	st $2001, r1
	halt
