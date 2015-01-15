led:
    st $f000, r1
    pop pcl
    pop pch
     
test_gt:
    gt r0, r1
    push pch
    push pcl
    b .test
    pop pcl
    pop pch

test_lt:
    lt r0, r1
    push pch
    push pcl
    b .test
    pop pcl
    pop pch

test_eq:
    eq r0, r1
    push pch
    push pcl
    b .test
    pop pcl
    pop pch

test:
    bzf .good
bad:
    mov r1, #0
    b .nxt_0
good:
    mov r1, #1
nxt_0:
    push pch
    push pcl
    b .led
    pop pcl
    pop pch
   
main: 
    mov r0, #1
eq_tests:
    mov r1, #1
    push pch
    push pcl
    b .test_eq  ; expect 1
    mov r1, #2
    push pch
    push pcl
    b .test_eq  ; expect 0
gt_tests:
    mov r1, #0
    push pch
    push pcl
    b .test_gt  ; expect 1
    mov r1, #2
    push pch
    push pcl
    b .test_gt  ; expect 0
lt_tests:
    mov r1, #2
    push pch
    push pcl
    b .test_lt  ; expect 1
    mov r1, #0
    push pch
    push pcl
    b .test_lt  ; expect 0
