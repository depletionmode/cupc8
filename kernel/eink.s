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
gpu_src: resb 2				; gpu_cmd_from's arguments, gpu_query_from's answer
eink_m: resb 1
eink_cfg: resb 6			; on, idle10, full_after, cap10, full_kind, sleep_s (AUTO_GET's order)
eink_st: resb 3				; busy, dirty, partials (EPD_STATUS)

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

; The refresh policy (eink-card.md, AUTO $0A, AUTO_EXT $0C, AUTO_GET $0D) and
; the panel's state (EPD_STATUS $0B). The kernel itself keeps the card's
; defaults; programs set them (API_EINK_AUTO). On HDMI these do nothing and
; r0 = $ff; eink_get and eink_status then leave $ff in eink_cfg / eink_st.

; send AUTO and AUTO_EXT from eink_cfg. r0 = 0, or $ff (not e-paper)
eink_auto:
	ld r0, [gpu_kind]
	eq r0, #EINK_KIND
	bzf .eink
	mov r0, #0xff
	b .done
.eink:
	mov r0, #<[eink_cfg]
	st [gpu_src], r0
	mov r0, #>[eink_cfg]
	st [gpu_src+1], r0
	mov r0, #0x0a			; AUTO on, idle10, full_after
	mov r1, #3
	push pch
	push pcl
	b gpu_cmd_from
	mov r0, #<[eink_cfg+3]
	st [gpu_src], r0
	mov r0, #>[eink_cfg+3]
	st [gpu_src+1], r0
	mov r0, #0x0c			; AUTO_EXT cap10, full_kind, sleep_s
	mov r1, #3
	push pch
	push pcl
	b gpu_cmd_from
	xor r0, r0
.done:
	pop pcl
	pop pch

; AUTO_GET into eink_cfg. r0 = 0, or $ff
eink_get:
	mov r0, #<[eink_cfg]
	st [gpu_src], r0
	mov r0, #>[eink_cfg]
	st [gpu_src+1], r0
	mov r1, #6
	mov r0, #0x0d
	b eink_ask

; EPD_STATUS into eink_st. r0 = 0, or $ff
eink_status:
	mov r0, #<[eink_st]
	st [gpu_src], r0
	mov r0, #>[eink_st]
	st [gpu_src+1], r0
	mov r1, #3
	mov r0, #0x0b
; command r0 (no arguments), its answer (r1 bytes) into gpu_src; $ff there
; first, and left on HDMI
eink_ask:
	st [eink_m], r0
	mov r0, #0xff
.fill:
	eq r1, #0
	bzf .filled
	sub r1, #1
	std [gpu_src]+r1, r0
	b .fill
.filled:
	ld r0, [gpu_kind]
	eq r0, #EINK_KIND
	bzf .eink
	mov r0, #0xff
	b .done
.eink:
	ld r0, [eink_m]
	push pch
	push pcl
	b gpu_query_from
.done:
	pop pcl
	pop pch
