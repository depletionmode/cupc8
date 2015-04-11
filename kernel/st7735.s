; st7735 display driver

; ported from adafruit library
%define ST7735_NOP     #0
%define ST7735_SWRESET #1
%define ST7735_RDDID   #4
%define ST7735_RDDST   #6

%define ST7735_SLPIN   #16
%define ST7735_SLPOUT  #17
%define ST7735_PTLON   #18
%define ST7735_NORON   #19

%define ST7735_INVOFF  #32
%define ST7735_INVON   #33
%define ST7735_DISPOFF #40
%define ST7735_DISPON  #41
%define ST7735_CASET   #42
%define ST7735_RASET   #43
%define ST7735_RAMWR   #44
%define ST7735_RAMRD   #46

%define ST7735_PTLAR   #48
%define ST7735_COLMOD  #58
%define ST7735_MADCTL  #54

%define ST7735_FRMCTR1 #177
%define ST7735_FRMCTR2 #178
%define ST7735_FRMCTR3 #179
%define ST7735_INVCTR  #180
%define ST7735_DISSET5 #182

%define ST7735_PWCTR1  #192
%define ST7735_PWCTR2  #193
%define ST7735_PWCTR3  #194
%define ST7735_PWCTR4  #195
%define ST7735_PWCTR5  #196
%define ST7735_VMCTR1  #197

%define ST7735_RDID1   #218
%define ST7735_RDID2   #219
%define ST7735_RDID3   #220
%define ST7735_RDID4   #221

%define ST7735_PWCTR6  #252

%define ST7735_GMCTRP1 #224
%define ST7735_GMCTRN1 #225

st7735_init:
    nop
    pop pcl
    pop pch

st7735_pc_0: resb 2

saw_i0: resb 1
st7735_set_addr_window:
    ; args on stack:
    ; - col start
    ; - col end
    ; - row start
    ; - row end

    ; save return pc
    pop r0
    st [st7735_pc_0], r0
    pop r0
    st [st7735_pc_0+1], r0

    mov r0, ST7735_CASET
	xor r1, r1
    push pch
    push pcl
    b spi_write

    mov r1, #0  ; ctr
.loop_col:
    st [saw_i0], r1
    pop r0
	xor r1, r1
    push pch
    push pcl
    b spi_write
    ld r1, [saw_i0]
    add r1, #1  ; ctr++
    eq r1, #2
    bzf .col_done
    b .loop_col
.col_done:
    mov r0, ST7735_RASET
	xor r1, r1
    push pch
    push pcl
    b spi_write

    mov r1, #0  ; ctr
.loop_row:
    st [saw_i0], r1
    pop r0
	xor r1, r1
    push pch
    push pcl
    b spi_write
    ld r1, [saw_i0]

    add r1, #1  ; ctr++
    eq r1, #2
    bzf .row_done
    b .loop_row
.row_done:
    mov r0, ST7735_RAMWR
	xor r1, r1
    push pch
    push pcl
    b spi_write

    ; restore return pc
    ld r0, [st7735_pc_0+1]
    push r0
    ld r0, [st7735_pc_0]
    push r0

    pop pcl
    pop pch

st7735_pc_2: resb 2

st7735_set_color:
    ; arg in r0:
    ; - color idx

    ; save return pc
    pop r0
    st [st7735_pc_2], r0
    pop r0
    st [st7735_pc_2+1], r0

    ; todo write actual color
    ; temporarily set colour to white
    mov r0, #255

    ; write high byte
	xor r1, r1
    push pch
    push pcl
    b spi_write

    ; write low byte
	xor r1, r1
    push pch
    push pcl
    b spi_write
    ; restore return pc
    ld r0, [st7735_pc_2+1]
    push r0
    ld r0, [st7735_pc_2]
    push r0

    pop pcl
    pop pch


st7735_x1: resb 1
st7735_y1: resb 1
st7735_pc_3: resb 2

st7735_draw_pixel:
    ; args on stack:
    ; - x
    ; - y
    ; - color

    ; save return pc
    pop r0
    st [st7735_pc_3], r0
    pop r0
    st [st7735_pc_3+1], r0

    pop r0  ; x
    pop r1  ; y

    push #1
    push #1

    push r1
    push r0

    push pch
    push pcl
    b st7735_fill_rect

    ; restore return pc
    ld r0, [st7735_pc_3+1]
    push r0
    ld r0, [st7735_pc_3]
    push r0

    pop pcl
    pop pch

st7735_pc_4: resb 2
st7735_w: resb 1
st7735_h: resb 1
st7735_fill_rect:
    ; args on stack:
    ; - x
    ; - y
    ; - width
    ; - height
    ; - color

    ; save return pc
    pop r0
    st [st7735_pc_4], r0
    pop r0
    st [st7735_pc_4+1], r0

    pop r0
    st [st7735_x1], r0

    pop r0
    st [st7735_y1], r0

    pop r0
    st [st7735_w], r0

    pop r0
    st [st7735_h], r0

    ld r0, [st7735_y1]
    ld r1, [st7735_h]
    add r1, r0
    push r1
    push r0

    ld r0, [st7735_x1]
    ld r1, [st7735_w]
    add r1, r0
    push r1
    push r0

    push pch
    push pcl
    b st7735_set_addr_window

    ; write color
    pop r0
    push pch
    push pcl
    b st7735_set_color

    ; restore return pc
    ld r0, [st7735_pc_4+1]
    push r0
    ld r0, [st7735_pc_4]
    push r0

    pop pcl
    pop pch

