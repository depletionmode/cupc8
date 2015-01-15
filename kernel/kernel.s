; kernel entry point
main:
    nop
    push #10
    push #10
    push #0
    push pch
    push pcl
    b .st7735_draw_pixel

hang:
    nop
    b .hang
