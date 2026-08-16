%define MAGIC #0x33
%define OUT $2000
main:
	mov r0, MAGIC
	st OUT, r0
	halt
