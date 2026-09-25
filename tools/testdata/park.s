; A program for $7000 that parks in WAI with only the slot IRQ unmasked (the
; chipset's tick masked): on a machine with no IO card nothing wakes it.
; test/sim/test_cli.py types keys at it (the sim must still end headless).
main:
	mov r0, #1
	st $f201, r0
	sti
.loop:
	wai
	b .loop
