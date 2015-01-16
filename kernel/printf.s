; routines for printing text

; global variables
posx: resb 1
posy: resb 1

; character set
charset db 24, 60, 102, 126, 102, 102, 102, 0, 124, 102, 102, 124, 102, 102, 124, 0, 60, 102, 96, 96, 96, 102, 60, 0, 120, 108, 102, 102, 102, 108, 120, 0, 126, 96, 96, 120, 96, 96, 126, 0, 126, 96, 96, 120, 96, 96, 96, 0, 60, 102, 96, 110, 102, 102, 60, 0, 102, 102, 102, 126, 102, 102, 102, 0, 60, 24, 24, 24, 24, 24, 60, 0, 30, 12, 12, 12, 12, 108, 56, 0, 102, 108, 120, 112, 120, 108, 102, 0, 96, 96, 96, 96, 96, 96, 126, 0, 99, 119, 127, 107, 99, 99, 99, 0, 102, 118, 126, 126, 110, 102, 102, 0, 60, 102, 102, 102, 102, 102, 60, 0, 124, 102, 102, 124, 96, 96, 96, 0, 60, 102, 102, 102, 102, 60, 14, 0, 124, 102, 102, 124, 120, 108, 102, 0, 60, 102, 96, 60, 6, 102, 60, 0, 126, 24, 24, 24, 24, 24, 24, 0, 102, 102, 102, 102, 102, 102, 60, 0, 102, 102, 102, 102, 102, 60, 24, 0, 99, 99, 99, 107, 127, 119, 99, 0, 102, 102, 60, 24, 60, 102, 102, 0, 102, 102, 102, 60, 24, 24, 24, 0, 126, 6, 12, 24, 48, 96, 126, 0

i0: resb 1
j0: resb 1
char0: resb 1
offset0: resb 1

temp_msg db "\nCUPCAKE KERNEL TEST\n\nABC"

pm_i: resb 1
print_msg:
    xor r1, r1
    st [posx], r1
    st [posy], r1
    st [pm_i], r1
pm_loop:
    ld r0, [temp_msg]+r1
    eq r0, #0
    bzf .pm_done
    push pch
    push pcl
    b .print_char
    ld r1, [pm_i]
    add r1, #1
    st [pm_i], r1
    b .pm_loop
pm_done:
    pop pcl
    pop pch
    

print_char:
    ; arg
    ; - ascii value in r0

    ; newline
    eq r0, #10
    bzf .pc_newline
    b .pc_cont
pc_newline:
    ld r0, [posy]
    add r0, #8
    st [posy], r0
    xor r0, r0
    st [posx], r0
    b .print_char_done 
pc_cont:
    ; normalize ascii
    sub r0, #65
    st [char0], r0

    mov r1, #8
    push pch
    push pcl
    b .mul
    st [offset0], r0

    xor r0, r0
    st [i0], r0 ; i=0
    st [j0], r0 ; j=0
print_char_loop:
    ld r1, [i0]
    mov r0, #128
    shr r0, r1
    ;st $f000, r0

    ld r1, [j0]
    push r0
    ld r0, [offset0]
    add r1, r0
    ld r1, [charset]+r1
    ;st $f000, r1
    pop r0
    and r0, r1
    ;st $f000, r0
    eq r0, #0
    bzf .print_char_draw_done
print_char_draw:
    push #255   ; colour

    nop
    ld r0, [j0]
    ld r1, [posy]
    add r1, r0
    push r1     ; y

    ld r0, [i0]
    ld r1, [posx]
    add r1, r0
    push r1     ; x

    push pch
    push pcl
    b .st7735_draw_pixel
print_char_draw_done:
    ld r0, [i0]
    add r0, #1  ; i++
    st [i0], r0

    lt r0, #8   ; ? i < 8
    bzf .print_char_loop

    xor r0, r0  ; reset i
    st [i0], r0

    ld r1, [j0]
    add r1, #1  ; j++
    st [j0], r1

    lt r1, #8   ; ? j < 8
    bzf .print_char_loop
    
    ld r0, [posx]
    add r0, #8
    eq r0, #0
    bzf .print_char_inc_posy
    st [posx], r0
    b .print_char_done
print_char_inc_posy:
    ld r0, [posy]
    add r0, #8
    st [posy], r0
    xor r0, r0
    st [posx], r0
print_char_done:
    pop pcl
    pop pch
