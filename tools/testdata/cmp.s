; Compare + BZF. $2000 = 0xaa on success, 0xee on first failure.
main:
	mov r0, #5
	eq r0, #5
	bzf .eq_imm_ok
	b fail
.eq_imm_ok:
	eq r0, #6
	bzf fail

	gt r0, #4
	bzf .gt_ok
	b fail
.gt_ok:
	gt r0, #5
	bzf fail
	gt r0, #6
	bzf fail

	lt r0, #6
	bzf .lt_ok
	b fail
.lt_ok:
	lt r0, #5
	bzf fail
	lt r0, #4
	bzf fail

	mov r1, #5
	eq r0, r1
	bzf .eq_reg_ok
	b fail
.eq_reg_ok:
	mov r1, #4
	gt r0, r1
	bzf .gt_reg_ok
	b fail
.gt_reg_ok:
	mov r1, #9
	lt r0, r1
	bzf .lt_reg_ok
	b fail
.lt_reg_ok:
	; compares must not clobber registers
	eq r0, r0
	gt r0, r1
	lt r0, r1
	eq r0, #99
	mov r1, #5
	eq r0, r1
	bzf .regs_ok
	b fail
.regs_ok:
	; r0 still 5
	eq r0, #5
	bzf pass
	b fail

pass:
	mov r0, #0xaa
	st $2000, r0
	halt

fail:
	mov r0, #0xee
	st $2000, r0
	halt
