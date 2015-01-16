; routines for printing text

; global variables
posx: resb 1
posy: resb 1
charset: resb 208  ; temporary until .data assembler implementation

; character set
;charset db 0, 0, 0, 0, 0, 0, 0, 0,  ; A

i0: resb 1
j0: resb 1
char0: resb 1
offset0: resb 1

tmp_fill_charset:
    mov r0, #0
    st [charset], r0
    mov r0, #0
    st [charset+1], r0
    mov r0, #60
    st [charset+2], r0
    mov r0, #6
    st [charset+3], r0
    mov r0, #62
    st [charset+4], r0
    mov r0, #102
    st [charset+5], r0
    mov r0, #62
    st [charset+6], r0
    mov r0, #0
    st [charset+7], r0

print_char:
    ; arg
    ; - ascii value in r0

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
    ld r1, [offset0]+r1
    and r0, r1
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
    eq r0, #0 : ? posx == 0
    bzf .print_char_inc_posy
    b .print_char_done
print_char_inc_posy:
    ld r0, [posy]
    add r0, #8
    st [posy], r0
print_char_done:
    pop pcl
    pop pch
