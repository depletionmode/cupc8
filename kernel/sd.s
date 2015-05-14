; sd card driver

%define		SD_SPI_DEVICE		#1

; commands
%define 	GO_IDLE_STATE		#0		; CMD0
%define 	SEND_OP_COND		#1		; CMD1
%define 	READ_SINGLE_BLOCK	#17		; CMD17
%define		WRITE_SINGLE_BLOCK	#24		; CMD24
%define		SET_BLOCKLEN		#16		; CMD16

; R1 response
%define		SUCCESS				#0
%define 	IDLE_STATE			#1
%define		ERASE_RESET			#2
%define 	ILLEGAL_CMD			#4
%define 	CRC_ERR				#8
%define 	ERASE_SEQ_ERR		#16
%define 	ADDRESS_ERR			#32
%define 	PARAM_ERR			#64

; 512 byte data buffer
sd_buf0 resb 256
sd_buf1 resb 256

; 4 byte cmd argument buffer
sd_cmd_buf resb 4

sd_cmd_buf_idx resb 1
sd_send_cmd:
	; write cmd
	; cmd index provided in R0
	; argument in sd_cmd_buf
	; crc is fixed
	push r1
	
	xor r1, r1
	st [sd_cmd_buf_idx], r1
	mov r1, SD_SPI_DEVICE

	; send cmd byte
	add r0, #64
	b spi_write

	; send cmd argument
.loop:
	ld r0, [sd_cmd_buf_idx]
	add r0, #1
	st [sd_cmd_buf_idx], r0
	sub r0, #1
	ld r0, [sd_cmd_buf]+r0
	b spi_write
	lt r0, #3
	bzf ,loop

	; send crc
	mov r0, #0	; todo -crc
	b spi_write
	mov r0, #0	; todo -crc
	b spi_write

	pop r1
	pop pcl
	pop pch

sd_read_R1:
	; return R1 response byte in R0
	; correct way is to send 0xff and recv until valid
	; however we'll just place an arbitraty delay for now
	push r1

	; todo: delay

	mov r1, SD_SPI_DEVICE
	b spi_read
	
	pop r1
	pop pcl
	pop pch

sd_reset:
	push r0
	push r1

	; send CMD0
	; crc must be valid
	mov r0, GO_IDLE_STATE
	b sd_send_cmd

	; read R1
	; check idle state bit is set
.loop
	b sd_read_R1
	and	r0, IDLE_STATE 
	eq r0, IDLE_STATE
	bzf .done
	b .loop

.done
	pop r1
	pop r0
    pop pcl
    pop pch

sd_init:
	push r0
	push r1

	; send CMD1
	mov r0, SEND_OP_COND
	b sd_send_cmd

	; read R1
	; check response is 0 (success)
.loop
	b sd_read_R1
	eq r0, SUCCESS
	bzf .done
	b .loop

sd_set_blocklen:
	push r0
	push r1

	; send CMD16 to set datalen to 512 bytes
	mov r0, SET_BLOCKLEN
	xor r1, r1
	st [sd_cmd_buf], r1
	st [sd_cmd_buf+1], r1
	st [sd_cmd_buf+4], r1
	add r1, #2		; set 512 bit
	st [sd_cmd_buf+3], r1
	b sd_send_cmd

	; read R1
	; check response is 0 (success)
.loop
	b sd_read_R1
	eq r0, SUCCESS
	bzf .done
	b .loop

.done
	pop r1
	pop r0
    pop pcl
    pop pch

