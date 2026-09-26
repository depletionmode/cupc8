; graphics primitives provided by kernel

%define gfx_fillrect gpu_fill_rect

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
