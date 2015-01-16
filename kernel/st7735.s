; st7735 display driver

%define _DEV_ 0     ; spi device

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

    mov r1, #0  ; ctr
saw_loop:
    pop r0
    push pch
    push pcl
    b .spi_write_DEV_
    add r1, #1  ; ctr++
    eq r1, #4
    bzf .saw_done
    b .saw_loop
saw_done:
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
    push pch
    push pcl
    b .spi_write_DEV_

    ; write low byte
    push pch
    push pcl
    b .spi_write_DEV_

    ; restore return pc
    ld r0, [st7735_pc_2+1]
    push r0
    ld r0, [st7735_pc_2]
    push r0

    pop pcl
    pop pch

st7735_pc_1: resb 2
st7735_x1: resb 1
st7735_x2: resb 1
st7735_y1: resb 1
st7735_y2: resb 1

st7735_draw_pixel:
    ; args on stack:
    ; - x
    ; - y
    ; - color

    ; save return pc
    pop r0
    st [st7735_pc_1], r0
    pop r0
    st [st7735_pc_1+1], r0

    ; x coord
    pop r0
    mov r1, r0
    add r1, #1
    st [st7735_x1], r0
    st [st7735_x2], r1

    ; y coord
    pop r0
    mov r1, r0
    add r1, #1
    st [st7735_y1], r0
    st [st7735_y2], r1

    ; set window (1 px in size)
    ld r0, [st7735_y2]
    push r0
    ld r0, [st7735_y1]
    push r0
    ld r0, [st7735_x2]
    push r0
    ld r0, [st7735_x1]
    push r0
    push pch
    push pcl
    b .st7735_set_addr_window

    ; write color
    pop r0
    push pch
    push pcl
    b .st7735_set_color

    ; restore return pc
    ld r0, [st7735_pc_1+1]
    push r0
    ld r0, [st7735_pc_1]
    push r0

    pop pcl
    pop pch
