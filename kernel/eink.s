; E-ink console (doc/hardware/eink-card.md): what the kernel does
; differently when the console is the e-paper graphics card.
;
; Both graphics cards are card type 1 and take the same commands, so
; gpu.s drives either. gpu_init asks INFO which one it found (gpu_kind:
; 0 HDMI, 1 e-paper, $ff no answer: an HDMI card without INFO); the card
; refreshes the panel by itself, so printing needs nothing more. What is
; left is asking for a clean refresh, which clears the ghosting partial
; refreshes leave behind (the terminal's `refresh` command).

%define EINK_KIND 1
%define EINK_REFRESH_CLEAN 2

; (here, not in gpu.s: the assembler wants data defined before its use,
; and the kernel's files are merged in name order)
gpu_kind: resb 1
eink_m: resb 1

; REFRESH m (m in r0) on an e-paper console; nothing on HDMI
eink_refresh:
	st [eink_m], r0
	ld r0, [gpu_kind]
	eq r0, #EINK_KIND
	bzf .eink
	b .none
.eink:
	push pch
	push pcl
	b gpu_cs_on
	mov r0, #0x09			; REFRESH
	push pch
	push pcl
	b gpu_send
	ld r0, [eink_m]
	push pch
	push pcl
	b gpu_send
	push pch
	push pcl
	b gpu_cs_off
.none:
	pop pcl
	pop pch

; the terminal's `refresh`: a clean full refresh of the e-paper panel
eink_cmd_refresh:
	mov r0, #EINK_REFRESH_CLEAN
	push pch
	push pcl
	b eink_refresh
	pop pcl
	pop pch
