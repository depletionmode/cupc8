; cards mode: print through the graphics card, then read a key from the IO card
; slot 1 is SPI device 0 (graphics), slot 2 is SPI device 1 (IO)

main:
	; graphics card: SCK divider 2, mode 0
	mov r0, #16
	st $f10f, r0

	; frame: PUTC 'H', PUTC 'i'
	mov r0, #1
	st $f104, r0		; SPI_CS hold dev 0
	mov r1, #1
	mov r0, #16			; PUTC opcode
	st $f100, r0
	st $f102, r1
	mov r0, #72			; 'H'
	st $f100, r0
	st $f102, r1
	mov r0, #0
	st $f104, r0		; release

	mov r0, #1
	st $f104, r0
	mov r0, #16
	st $f100, r0
	st $f102, r1
	mov r0, #105		; 'i'
	st $f100, r0
	st $f102, r1
	mov r0, #0
	st $f104, r0

	; IO card: GETKEY, then a READ frame for the response
	mov r0, #16
	st $f11f, r0
	mov r0, #1
	st $f114, r0
	mov r0, #0			; GETKEY opcode
	st $f110, r0
	st $f112, r1
	mov r0, #0
	st $f114, r0

	mov r0, #1
	st $f114, r0
	mov r0, #254		; READ opcode
	st $f110, r0
	st $f112, r1
	mov r0, #0
	st $f110, r0
	st $f112, r1
	ld r0, $f111		; RESP_LEN
	st $2000, r0
	mov r0, #0
	st $f110, r0
	st $f112, r1
	ld r0, $f111		; the key
	st $2001, r0
	mov r0, #0
	st $f114, r0

	halt
