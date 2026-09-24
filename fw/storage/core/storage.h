/*
 * CUPC/8 storage card core (doc/hardware/storage-card.md): files on a medium,
 * served over the common slot protocol.
 *
 * Hardware-independent. The medium is behind st_disk_t (the RP2040 build: an
 * SD card in SPI mode; host tests and the simulator: an image file), and the
 * file system is FatFs (fw/third_party/fatfs).
 *
 * Medium operations take far longer than the slot's 5 ms deadline, so the
 * card engine (core 0 on the RP2040) only queues each command frame; a worker
 * (core 1 on the RP2040, or st_poll() on a host) runs it with st_exec() and
 * hands the answer back with st_done(). Meanwhile READ returns RESP_LEN 0 and
 * the status byte's BUSY bit is set.
 *
 *   core 0 (card engine)          worker (owns FatFs and the medium)
 *   command() -> queue
 *   st_take()  ------ request --> st_exec()
 *   st_done()  <----- response --
 *
 * st_take/st_done/st_detect run where the card engine runs; st_exec and
 * st_service where the worker runs. Only the worker touches FatFs.
 */
#ifndef STORAGE_H
#define STORAGE_H

#include <stdbool.h>
#include <stdint.h>

#include "cardproto.h"
#include "ff.h"

#define ST_HANDLES   4
#define ST_CHUNK     128               /* file data per F_READ/F_WRITE */
#define ST_REQ_MAX   136               /* longest request: BUF_PUT, 4 + 128 */
#define ST_QUEUE     4                 /* requests waiting for the worker */
#define ST_NAME_MAX  12                /* 8.3 */

/* opcodes */
enum {
	ST_INFO = 0x01, ST_MOUNT = 0x02, ST_EJECT = 0x03,
	ST_F_OPEN = 0x10, ST_F_READ, ST_F_WRITE, ST_F_CLOSE, ST_F_SEEK,
	ST_DIR_FIRST, ST_DIR_NEXT, ST_F_DELETE, ST_F_RENAME,
	ST_BLK_READ = 0x20, ST_BLK_WRITE, ST_BUF_GET, ST_BUF_PUT,
	ST_INTERNAL_RESET = 0xEF,          /* SOFT_RESET's work for the worker, never from the host */
};

/* error codes */
enum {
	ST_OK = 0x00, ST_E_NO_MEDIUM, ST_E_NOT_MOUNTED, ST_E_NOT_FOUND, ST_E_EXISTS,
	ST_E_FULL, ST_E_WP, ST_E_BAD_HANDLE, ST_E_BAD_NAME, ST_E_IO, ST_E_TOO_MANY,
};

/* status byte */
#define ST_S_MEDIA   0x40
#define ST_S_MOUNTED 0x20
#define ST_S_BUSY    0x10
#define ST_S_WP      0x08

#define ST_MEDIA_NONE 0
#define ST_MEDIA_SD   1

#define ST_DIR_END 0xFF                /* DIR_FIRST/NEXT: RESP_LEN 1, $FF */
#define ST_READ_ERR 0xFF               /* F_READ: n' = $FF, then the error code */

/* The medium: 512-byte sectors. Calls return 0 on success. */
typedef struct {
	uint8_t media;                     /* ST_INFO media code */
	int (*init)(void *ctx);            /* bring a newly inserted medium up */
	bool (*write_protected)(void *ctx);
	uint32_t (*sectors)(void *ctx);
	int (*read)(void *ctx, uint8_t *buf, uint32_t lba, uint32_t count);
	int (*write)(void *ctx, const uint8_t *buf, uint32_t lba, uint32_t count);
	int (*sync)(void *ctx);
} st_disk_t;

typedef struct {
	uint8_t data[ST_REQ_MAX];
	int len;
	uint32_t seq;
} st_req_t;

typedef struct storage {
	card_t card;

	/* card engine side */
	st_req_t queue[ST_QUEUE];
	int q_head, q_count;
	uint32_t seq;                      /* of the latest queued command */
	volatile bool running;             /* a request is with the worker */

	/* shared: set by st_detect (card engine side), read by the worker */
	volatile bool present;             /* card detect */
	volatile uint32_t detect_gen;      /* counts card detect changes */

	/* shared: set by the worker, read for the status byte and ST_INFO */
	volatile bool mounted, wp;
	volatile uint8_t err;              /* the last command's error */

	/* worker side */
	const st_disk_t *disk;
	void *ctx;
	uint32_t seen_gen;                 /* detect_gen the worker has acted on */
	FATFS fs;
	FIL fil[ST_HANDLES];
	uint8_t hmode[ST_HANDLES];         /* 0 closed, 1 read, 2 write, 3 lost with the medium */
	DIR dir;
	bool dir_open;
	uint8_t buf[512];                  /* the block buffer */
} storage_t;

void st_init(storage_t *s, const st_disk_t *disk, void *ctx, bool present);

/* card engine side */
void st_detect(storage_t *s, bool present);
bool st_take(storage_t *s, st_req_t *req);
void st_done(storage_t *s, uint32_t seq, const uint8_t *resp, int len);
bool st_busy(const storage_t *s);
uint8_t st_status(const storage_t *s);

/* worker side: returns the response length, or -1 for no response */
int st_exec(storage_t *s, const uint8_t *req, int len, uint8_t resp[CARD_RESP_MAX]);
/* worker side, between requests: act on card detect (unmount at once on
 * removal, mount on insertion) */
void st_service(storage_t *s);

/* a host without a second core: run everything queued now */
void st_poll(storage_t *s);

#endif
