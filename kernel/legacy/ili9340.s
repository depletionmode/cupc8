; ili9340 display driver

; ported from adafruit library, original license:

;/***************************************************
;  This is an Arduino Library for the Adafruit 2.2" SPI display.
;  This library works with the Adafruit 2.2" TFT Breakout w/SD card
;  ----> http://www.adafruit.com/products/1480
; 
;  Check out the links above for our tutorials and wiring diagrams
;  These displays use SPI to communicate, 4 or 5 pins are required to
;  interface (RST is optional)
;  Adafruit invests time and resources providing this open source code,
;  please support Adafruit and open-source hardware by purchasing
;  products from Adafruit!
;  Written by Limor Fried/Ladyada for Adafruit Industries.
;  MIT license, all text above must be included in any redistribution
; ****************************************************/
;/***************************************************
;  This is an Arduino Library for the Adafruit 2.2" SPI display.
;  This library works with the Adafruit 2.2" TFT Breakout w/SD card
;  ----> http://www.adafruit.com/products/1480
; 
;  Check out the links above for our tutorials and wiring diagrams
;  These displays use SPI to communicate, 4 or 5 pins are required to
;  interface (RST is optional)
;  Adafruit invests time and resources providing this open source code,
;  please support Adafruit and open-source hardware by purchasing
;  products from Adafruit!
;  Written by Limor Fried/Ladyada for Adafruit Industries.
;  MIT license, all text above must be included in any redistribution
; ****************************************************/

; dc ('data/command') pin set to GPO0
; rst pin set to GPO1

; cupc/8 colors
%define COLOR_WHITE 0xff
%define COLOR_BLACK 0x00

%define ILI9340_TFTWIDTH  240
%define ILI9340_TFTHEIGHT 320

%define ILI9340_NOP     0x00
%define ILI9340_SWRESET 0x01
%define ILI9340_RDDID   0x04
%define ILI9340_RDDST   0x09

%define ILI9340_SLPIN   0x10
%define ILI9340_SLPOUT  0x11
%define ILI9340_PTLON   0x12
%define ILI9340_NORON   0x13

%define ILI9340_RDMODE  0x0A
%define ILI9340_RDMADCTL  0x0B
%define ILI9340_RDPIXFMT  0x0C
%define ILI9340_RDIMGFMT  0x0A
%define ILI9340_RDSELFDIAG  0x0F

%define ILI9340_INVOFF  0x20
%define ILI9340_INVON   0x21
%define ILI9340_GAMMASET 0x26
%define ILI9340_DISPOFF 0x28
%define ILI9340_DISPON  0x29

%define ILI9340_CASET   0x2A
%define ILI9340_PASET   0x2B
%define ILI9340_RAMWR   0x2C
%define ILI9340_RAMRD   0x2E

%define ILI9340_PTLAR   0x30
%define ILI9340_MADCTL  0x36


%define ILI9340_MADCTL_MY  0x80
%define ILI9340_MADCTL_MX  0x40
%define ILI9340_MADCTL_MV  0x20
%define ILI9340_MADCTL_ML  0x10
%define ILI9340_MADCTL_RGB 0x00
%define ILI9340_MADCTL_BGR 0x08
%define ILI9340_MADCTL_MH  0x04

%define ILI9340_PIXFMT  0x3A

%define ILI9340_FRMCTR1 0xB1
%define ILI9340_FRMCTR2 0xB2
%define ILI9340_FRMCTR3 0xB3
%define ILI9340_INVCTR  0xB4
%define ILI9340_DFUNCTR 0xB6

%define ILI9340_PWCTR1  0xC0
%define ILI9340_PWCTR2  0xC1
%define ILI9340_PWCTR3  0xC2
%define ILI9340_PWCTR4  0xC3
%define ILI9340_PWCTR5  0xC4
%define ILI9340_VMCTR1  0xC5
%define ILI9340_VMCTR2  0xC7

%define ILI9340_RDID1   0xDA
%define ILI9340_RDID2   0xDB
%define ILI9340_RDID3   0xDC
%define ILI9340_RDID4   0xDD

%define ILI9340_GMCTRP1 0xE0
%define ILI9340_GMCTRN1 0xE1

%define	ILI9340_BLACK   0x0000
%define	ILI9340_BLUE    0x001F
%define	ILI9340_RED     0xF800
%define	ILI9340_GREEN   0x07E0
%define ILI9340_CYAN    0x07FF
%define ILI9340_MAGENTA 0xF81F
%define ILI9340_YELLOW  0xFFE0  
%define ILI9340_WHITE   0xFFFF

ili9340_writecmd:
	; r0 = cmd
.clear_dc:
	ld r1, $f000
	and r1, #254
	st $f000, r1

.spi_write:
	xor r1, r1
    push pch
    push pcl
    b spi_write

.done:
	pop pcl
	pop pch

ili9340_writedata:
	; r0 = cmd
.set_dc:
	ld r1, $f000
	or r1, #1
	st $f000, r1

.spi_write:
	xor r1, r1
    push pch
    push pcl
    b spi_write

.done:
	pop pcl
	pop pch

ili9340_init:
.reset:
	; todo add delays
	ld r0, $f000
	or r0, #2
	st $f000, r0
	and r0, #253
	st $f000, r0
	or r0, #2
	st $f000, r0

.init_cmds:
	mov r0, #0xef
	push pch
	push pcl
	b ili9340_writecmd
	mov r0, #3
	push pch
	push pcl
	b ili9340_writedata
	mov r0, #0x80
	push pch
	push pcl
	b ili9340_writedata
	mov r0, #2
	push pch
	push pcl
	b ili9340_writedata

	mov r0, #0xcf
	push pch
	push pcl
	b ili9340_writecmd
	mov r0, #0
	push pch
	push pcl
	b ili9340_writedata
	mov r0, #0xc1
	push pch
	push pcl
	b ili9340_writedata
	mov r0, #0x30
	push pch
	push pcl
	b ili9340_writedata

	mov r0, #0xed
	push pch
	push pcl
	b ili9340_writecmd
	mov r0, #0x64
	push pch
	push pcl
	b ili9340_writedata
	mov r0, #3
	push pch
	push pcl
	b ili9340_writedata
	mov r0, #0x12
	push pch
	push pcl
	b ili9340_writedata
	mov r0, #0x81
	push pch
	push pcl
	b ili9340_writedata

	mov r0, #0xe8
	push pch
	push pcl
	b ili9340_writecmd
	mov r0, #0x85
	push pch
	push pcl
	b ili9340_writedata
	mov r0, #0
	push pch
	push pcl
	b ili9340_writedata
	mov r0, #0x78
	push pch
	push pcl
	b ili9340_writedata

	mov r0, #0xcb
	push pch
	push pcl
	b ili9340_writecmd
	mov r0, #0x39
	push pch
	push pcl
	b ili9340_writedata
	mov r0, #0x2c
	push pch
	push pcl
	b ili9340_writedata
	mov r0, #0
	push pch
	push pcl
	b ili9340_writedata
	mov r0, #0x34
	push pch
	push pcl
	b ili9340_writedata
	mov r0, #2
	push pch
	push pcl
	b ili9340_writedata

	mov r0, #0xf7
	push pch
	push pcl
	b ili9340_writecmd
	mov r0, #0x20
	push pch
	push pcl
	b ili9340_writedata

	mov r0, #0xea
	push pch
	push pcl
	b ili9340_writecmd
	mov r0, #0
	push pch
	push pcl
	b ili9340_writedata
	mov r0, #0

	mov r0, #ILI9340_PWCTR1
	push pch
	push pcl
	b ili9340_writecmd
	mov r0, #0x23
	push pch
	push pcl
	b ili9340_writedata

	mov r0, #ILI9340_PWCTR2
	push pch
	push pcl
	b ili9340_writecmd
	mov r0, #0x10
	push pch
	push pcl
	b ili9340_writedata

	mov r0, #ILI9340_VMCTR1
	push pch
	push pcl
	b ili9340_writecmd
	mov r0, #0x3e
	push pch
	push pcl
	b ili9340_writedata
	mov r0, #0x28
	push pch
	push pcl
	b ili9340_writedata

	mov r0, #ILI9340_VMCTR2
	push pch
	push pcl
	b ili9340_writecmd
	mov r0, #0x86
	push pch
	push pcl
	b ili9340_writedata

	mov r0, #ILI9340_MADCTL
	push pch
	push pcl
	b ili9340_writecmd
	mov r0, #ILI9340_MADCTL_MX
	mov r1, #ILI9340_MADCTL_BGR
	or r0, r1
	push pch
	push pcl
	b ili9340_writedata

	mov r0, #ILI9340_PIXFMT
	push pch
	push pcl
	b ili9340_writecmd
	mov r0, #0x55
	push pch
	push pcl
	b ili9340_writedata

	mov r0, #ILI9340_FRMCTR1
	push pch
	push pcl
	b ili9340_writecmd
	mov r0, #0
	push pch
	push pcl
	b ili9340_writedata
	mov r0, #0x18
	push pch
	push pcl
	b ili9340_writedata

	mov r0, #ILI9340_DFUNCTR
	push pch
	push pcl
	b ili9340_writecmd
	mov r0, #8
	push pch
	push pcl
	b ili9340_writedata
	mov r0, #0x82
	push pch
	push pcl
	b ili9340_writedata
	mov r0, #0x27
	push pch
	push pcl
	b ili9340_writedata

	mov r0, #0xf2
	push pch
	push pcl
	b ili9340_writecmd
	mov r0, #0
	push pch
	push pcl
	b ili9340_writedata

	mov r0, #ILI9340_GAMMASET
	push pch
	push pcl
	b ili9340_writecmd
	mov r0, #1
	push pch
	push pcl
	b ili9340_writedata

	mov r0, #ILI9340_GMCTRP1
	push pch
	push pcl
	b ili9340_writecmd
	mov r0, #0x0f
	push pch
	push pcl
	b ili9340_writedata
	mov r0, #0x31
	push pch
	push pcl
	b ili9340_writedata
	mov r0, #0x2b
	push pch
	push pcl
	b ili9340_writedata
	mov r0, #0x0c
	push pch
	push pcl
	b ili9340_writedata
	mov r0, #0x0e
	push pch
	push pcl
	b ili9340_writedata
	mov r0, #0x08
	push pch
	push pcl
	b ili9340_writedata
	mov r0, #0x4e
	push pch
	push pcl
	b ili9340_writedata
	mov r0, #0xf1
	push pch
	push pcl
	b ili9340_writedata
	mov r0, #0x37
	push pch
	push pcl
	b ili9340_writedata
	mov r0, #0x07
	push pch
	push pcl
	b ili9340_writedata
	mov r0, #0x10
	push pch
	push pcl
	b ili9340_writedata
	mov r0, #0x03
	push pch
	push pcl
	b ili9340_writedata
	mov r0, #0x0e
	push pch
	push pcl
	b ili9340_writedata
	mov r0, #0x09
	push pch
	push pcl
	b ili9340_writedata
	mov r0, #0
	push pch
	push pcl
	b ili9340_writedata

	mov r0, #ILI9340_GMCTRN1
	push pch
	push pcl
	b ili9340_writecmd
	mov r0, #0
	push pch
	push pcl
	b ili9340_writedata
	mov r0, #0x0e
	push pch
	push pcl
	b ili9340_writedata
	mov r0, #0x14
	push pch
	push pcl
	b ili9340_writedata
	mov r0, #0x03
	push pch
	push pcl
	b ili9340_writedata
	mov r0, #0x11
	push pch
	push pcl
	b ili9340_writedata
	mov r0, #0x07
	push pch
	push pcl
	b ili9340_writedata
	mov r0, #0x31
	push pch
	push pcl
	b ili9340_writedata
	mov r0, #0xc1
	push pch
	push pcl
	b ili9340_writedata
	mov r0, #0x48
	push pch
	push pcl
	b ili9340_writedata
	mov r0, #0x08
	push pch
	push pcl
	b ili9340_writedata
	mov r0, #0x0f
	push pch
	push pcl
	b ili9340_writedata
	mov r0, #0x0c
	push pch
	push pcl
	b ili9340_writedata
	mov r0, #0x31
	push pch
	push pcl
	b ili9340_writedata
	mov r0, #0x36
	push pch
	push pcl
	b ili9340_writedata
	mov r0, #0x0f
	push pch
	push pcl
	b ili9340_writedata

	mov r0, #ILI9340_SLPOUT
	push pch
	push pcl
	b ili9340_writecmd
	; todo delay

	mov r0, #ILI9340_DISPON
	push pch
	push pcl
	b ili9340_writecmd

.done:
	pop pcl
	pop pch

ili9340_pc0: resb 2
ili9340_set_addr_window:
    ; args on stack:
    ; - col start
    ; - col end
    ; - row start
    ; - row end

    ; save return pc
    pop r0
    st [ili9340_pc0], r0
    pop r0
    st [ili9340_pc0+1], r0

.column:
	mov r0, #ILI9340_CASET
	push pch
	push pcl
	b ili9340_writecmd
	xor r0, r0
	push pch
	push pcl
	b ili9340_writedata
	pop r0
	push pch
	push pcl
	b ili9340_writedata
	xor r0, r0
	push pch
	push pcl
	b ili9340_writedata
	pop r0
	push pch
	push pcl
	b ili9340_writedata

.row:
	mov r0, #ILI9340_PASET
	push pch
	push pcl
	b ili9340_writecmd
	xor r0, r0
	push pch
	push pcl
	b ili9340_writedata
	pop r0
	push pch
	push pcl
	b ili9340_writedata
	xor r0, r0
	push pch
	push pcl
	b ili9340_writedata
	pop r0
	push pch
	push pcl
	b ili9340_writedata

.ram_write:
	mov r0, #ILI9340_RAMWR
	push pch
	push pcl
	b ili9340_writecmd

.done:
	; restore pc
	ld r0, [ili9340_pc0+1]
	push r0
	ld r0, [ili9340_pc0]
	push r0

	pop pcl
	pop pch

ili9340_decode_color:
	; r0 - cupc/8 color code
.black:
	gt r0, #COLOR_BLACK
	bzf .white
	xor r0, r0
	xor r1, r1
	b .done

.white:		;default color
	mov r0, #0xff
	mov r1, #0xff

.done:
	pop pcl
	pop pch

ili9340_pc1: resb 2
ili9340_x: resb 1
ili9340_y: resb 1
ili9340_w: resb 1
ili9340_h: resb 1
ili9340_color: resb 2
ili9340_fill_rect:
    ; args on stack:
    ; - x
    ; - y
    ; - width
    ; - height
    ; - color

    ; save return pc
    pop r0
    st [ili9340_pc1], r0
    pop r0
    st [ili9340_pc1+1], r0

	pop r0
	st [ili9340_x], r0
	pop r0
	st [ili9340_y], r0
	pop r0
	st [ili9340_w], r0
	pop r0
	st [ili9340_h], r0

.decode_color:
	pop r0
	push pch
	push pcl
	b ili9340_decode_color
	st [ili9340_color+1], r0
	st [ili9340_color], r1

.window:
	ld r0, [ili9340_y]
	ld r1, [ili9340_h]
	add r1, r0
	push r1
	push r0
	ld r0, [ili9340_x]
	ld r1, [ili9340_w]
	add r1, r0
	push r1
	push r0
	push pch
	push pcl
	b ili9340_set_addr_window

.set_dc:
	ld r1, $f000
	or r1, #1
	st $f000, r1

	ld r0, [ili9340_h]
	push r0
.loop_w:
	ld r0, [ili9340_w]
	eq r0, #0
	bzf .done
	sub r0, #1
	st [ili9340_w], r0
	pop r0
	push r0
	st [ili9340_h], r0
.loop_h:
	ld r0, [ili9340_h]
	eq r0, #0
	bzf .loop_w
	sub r0, #1
	st [ili9340_h], r0
	; write color
	ld r0, [ili9340_color+1]
	xor r1, r1
	push pch
	push pcl
	b spi_write
	ld r0, [ili9340_color]
	xor r1, r1
	push pch
	push pcl
	b spi_write
	b .loop_h

.done:
	pop r0

	; restore pc
	ld r0, [ili9340_pc1+1]
	push r0
	ld r0, [ili9340_pc1]
	push r0

	pop pcl
	pop pch
