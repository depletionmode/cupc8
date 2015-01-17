func1:
    nop

func2:
    call .func1

main:
    call .func2
