; routines for printing text

; global variables
posx: resb 1
posy: resb 1
charset: resb 208  ; temporary until .data assembler implementation

; character set
;charset db 0, 0, 0, 0, 0, 0, 0, 0,  ; A

mul_n: resb 1
mul:
    ; r0 = r0 * r1

    st [mul_n], r1
    
    xor r1, r1  ; i=0

mul_loop:
    add r0, r0

    push r0
    ld r0, [mul_n]

    add r1, #1
    eq r1, r0
    pop r0
    bzf .mul_done
    b .mul_loop

mul_done:
    pop pcl
    pop pch 


i0: resb 1
j0: resb 1
char0: resb 1
offset0: resb 1

print_char:
    ; arg
    ; - ascii value in r0

    ; normalize ascii
    sub r0, #65
    st [char0], r0

    ld r0, [i0]
    mov r1, #8
    push pch
    push pcl
    b .mul
    st [offset0], r0

    mov r0, r0
    st [i0], r0 ; i=0
    st [j0], r0 ; j=0
loop0:
    ld r1, [i0]
    mov r0, #128
    shr r0, r1

    ld r1, [j0]
    ld r1, [offset0]+r1
    and r0, r1
    eq r0, #0
    bzf .draw_done
draw:
    push #255   ; colour

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
draw_done:
    ld r0, [i0]
    add r0, #1  ; i++
    st [i0], r0

    lt r0, #8   ; ? i < 8
    bzf .loop0

    xor r0, r0  ; reset i
    st [i0], r0

    ld r1, [j0]
    add r1, #1  ; j++
    st [j0], r1

    lt r1, #8   ; ? j < 8
    bzf .loop0
    
    ld r0, [posx]
    add r0, #8
    eq r0, #0 : ? posx == 0
    bzf .inc_posy
    b .done0
inc_posy:
    ld r0, [posy]
    add r0, #8
    st [posy], r0
done0:
    pop pcl
    pop pch
