; routines for printing text

; global variables
posx: resb 1
posy: resb 1

;%define charset charset_c64

; character set
;charset db 24, 60, 102, 126, 102, 102, 102, 0, 124, 102, 102, 124, 102, 102, 124, 0, 60, 102, 96, 96, 96, 102, 60, 0, 120, 108, 102, 102, 102, 108, 120, 0, 126, 96, 96, 120, 96, 96, 126, 0, 126, 96, 96, 120, 96, 96, 96, 0, 60, 102, 96, 110, 102, 102, 60, 0, 102, 102, 102, 126, 102, 102, 102, 0, 60, 24, 24, 24, 24, 24, 60, 0, 30, 12, 12, 12, 12, 108, 56, 0, 102, 108, 120, 112, 120, 108, 102, 0, 96, 96, 96, 96, 96, 96, 126, 0, 99, 119, 127, 107, 99, 99, 99, 0, 102, 118, 126, 126, 110, 102, 102, 0, 60, 102, 102, 102, 102, 102, 60, 0, 124, 102, 102, 124, 96, 96, 96, 0, 60, 102, 102, 102, 102, 60, 14, 0, 124, 102, 102, 124, 120, 108, 102, 0, 60, 102, 96, 60, 6, 102, 60, 0, 126, 24, 24, 24, 24, 24, 24, 0, 102, 102, 102, 102, 102, 102, 60, 0, 102, 102, 102, 102, 102, 60, 24, 0, 99, 99, 99, 107, 127, 119, 99, 0, 102, 102, 60, 24, 60, 102, 102, 0, 102, 102, 102, 60, 24, 24, 24, 0, 126, 6, 12, 24, 48, 96, 126, 0

i0: resb 1
j0: resb 1
char0: resb 1
offset0: resb 1

temp_msg db "\nCUPCAKE KERNEL TEST\n\n1234567890...\n\nChar rom dump:\n\n"

print_ascii_char:
    ; convert ascii to c64 char rom offsets

    ; 96-127: offset 7
    lt r0, #96
    bzf .pac_lt_96
    gt r0, #127
    bzf .pac_done
    sub r0, #64
    mov r1, #7
    b .pac_print_char
pac_lt_96:
    ; 64-95: offset 0
    lt r0, #64
    bzf .pac_lt_64
    gt r0, #95
    bzf .pac_done
    sub r0, #64
    xor r1, r1
    b .pac_print_char
pac_lt_64:
    ; 32-63: offset 1
    lt r0, #32
    bzf .pac_newline
    gt r0, #63
    bzf .pac_done
    sub r0, #32
    mov r1, #1
    b .pac_print_char
pac_newline:
    ; newline: #10
    mov r1, #16
    eq r0, #10
    bzf .pac_print_char
    b .pac_done
pac_print_char:
    push pch
    push pcl
    b .print_char
pac_done:
    pop pcl
    pop pch

dcr_cur: resb 1
dcr_i: resb 1
dump_char_rom:
    xor r0, r0
    st [dcr_i], r0
dcr_loop:
    ld r1, [dcr_i]
    push pch
    push pcl
    b .print_char
    ld r0, [dcr_cur]
    add r0, #1
    st [dcr_cur], r0
    lt r0, #32
    bzf .dcr_loop
    xor r0, r0
    st [dcr_cur], r0
    ld r1, [dcr_i]
    lt r1, #15
    add r1, #1
    st [dcr_i], r1
    bzf .dcr_loop
    pop pcl
    pop pch

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
;    xor r1, r1
    push pch
    push pcl
    b .print_ascii_char
;    b .print_char
    ld r1, [pm_i]
    add r1, #1
    st [pm_i], r1
    b .pm_loop
pm_done:
    pop pcl
    pop pch
    
pc_offset: resb 1
print_char:
    ; arg
    ; - ascii value in r0
    ; - charset offset r1

    st [pc_offset], r1

    ; newline
    eq r0, #10
    bzf .pc_newline
    b .pc_cont
pc_newline:
    eq r1, #16
    bzf .pc_newline2
    b .pc_cont
pc_newline2:
    ld r0, [posy]
    add r0, #8
    st [posy], r0
    xor r0, r0
    st [posx], r0
    b .print_char_done 
pc_cont:
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
    ld r0, [pc_offset]
    eq r0, #1
    bzf .pc_offset1
    eq r0, #2
    bzf .pc_offset2
    eq r0, #3
    bzf .pc_offset3
    eq r0, #4
    bzf .pc_offset4
    eq r0, #5
    bzf .pc_offset5
    eq r0, #6
    bzf .pc_offset6
    eq r0, #7
    bzf .pc_offset8
    eq r0, #9
    bzf .pc_offset9
    eq r0, #10
    bzf .pc_offset10
    eq r0, #11
    bzf .pc_offset11
    eq r0, #12
    bzf .pc_offset12
    eq r0, #13
    bzf .pc_offset13
    eq r0, #14
    bzf .pc_offset14
    eq r0, #15
    bzf .pc_offset15
pc_offset0:
    ld r1, [charset_c64]+r1
    b .pc_after_offset
pc_offset1:
    ld r1, [charset_c64+256]+r1
    b .pc_after_offset
pc_offset2:
    ld r1, [charset_c64+512]+r1
    b .pc_after_offset
pc_offset3:
    ld r1, [charset_c64+768]+r1
    b .pc_after_offset
pc_offset4:
    ld r1, [charset_c64+1024]+r1
    b .pc_after_offset
pc_offset5:
    ld r1, [charset_c64+1280]+r1
    b .pc_after_offset
pc_offset6:
    ld r1, [charset_c64+1536]+r1
    b .pc_after_offset
pc_offset7:
    ld r1, [charset_c64+1792]+r1
    b .pc_after_offset
pc_offset8:
    ld r1, [charset_c64+2048]+r1
    b .pc_after_offset
pc_offset9:
    ld r1, [charset_c64+2304]+r1
    b .pc_after_offset
pc_offset10:
    ld r1, [charset_c64+2560]+r1
    b .pc_after_offset
pc_offset11:
    ld r1, [charset_c64+2816]+r1
    b .pc_after_offset
pc_offset12:
    ld r1, [charset_c64+3072]+r1
    b .pc_after_offset
pc_offset13:
    ld r1, [charset_c64+3328]+r1
    b .pc_after_offset
pc_offset14:
    ld r1, [charset_c64+3584]+r1
    b .pc_after_offset
pc_offset15:
    ld r1, [charset_c64+3840]+r1
    b .pc_after_offset
pc_after_offset:
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
