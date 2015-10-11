; graphics primitives provided by kernel

%define gfx_fillrect ili9340_fill_rect

; globals
gfx_x: resb 1
gfx_y: resb 1
gfx_w: resb 1
gfx_h: resb 1
gfx_color: resb 1

gfx_clrscreen:
    push #0
    push #255
    push #255
    push #0
    push #0
    push pch
    push pcl
    b gfx_fillrect
    pop pcl
    pop pch

gfx_emptyrect_pc: resb 2
gfx_empyrect:
    ; args on stack
    ;    x
    ;    y
    ;    w
    ;    h
    ;    color

    pop r0
    st [gfx_empyrect_pc], r0
    pop r0
    st [gfx_empyrect_pc+1], r0

    pop r0
    st [gfx_x], r0
    pop r0
    st [gfx_y], r0
    pop r0
    st [gfx_w], r0
    pop r0
    st [gfx_h], r0
    pop r0
    st [gfx_color], r0

.top:
    push r0
    push #1
    ld r0, [gfx_w]
    push r0
    ld r0, [gfx_y]
    push r0
    ld r0, [gfx_x]
    push r0
    push pch
    puch pcl
    b gfx_fillrect
.right:
    ld r0, [gfx_color]
    push r0
    ld r0, [gfx_h]
    push r0
    push #1
    ld r0, [gfx_y]
    push r0
    ld r0, [gfx_w]
    sub r0, #1
    push r0
    push pch
    puch pcl
    b gfx_fillrect
.bottom:
    ld r0, [gfx_color]
    push r0
    push #1
    ld r0, [gfx_w]
    push r0
    ld r0, [gfx_h]
    sub r0, #1
    push r0
    ld r0, [gfx_x]
    push r0
    push pch
    puch pcl
    b gfx_fillrect
.left:
    ld r0, [gfx_color]
    push r0
    ld r0, [gfx_h]
    push r0
    push #1
    ld r0, [gfx_y]
    push r0
    ld r0, [gfx_x]
    push r0
    push pch
    puch pcl
    b gfx_fillrect
.done:
    ld r0, [gfx_empyrect_pc+1]
    push r0
    ld r0, [gfx_empyrect_pc]
    push r0
    pop pcl
    pop pch
