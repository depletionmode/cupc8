
%define GPO $f000

mul_n: resb 1
mul_v: resb 1
mul:
    ; r0 = r0 * r1
    st [mul_v], r0
    st [mul_n], r1
    mov r1, #1  ; i=1
.mul_loop:
    push r0
    ld r0, [mul_n]
    eq r0, r1
    pop r0
    bzf .mul_done  ; i==mul_n ? mul_done
    push r1
    ld r1, [mul_v]
    add r0, r1
    pop r1
    add r1, #1  ; i++
    b .mul_loop
.mul_done:
    pop pcl
    pop pch 

main:
    ; 3 * 2
    mov r0, #3
    mov r1, #3
    push pch
    push pcl
    b mul
    st GPO, r0
