
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
