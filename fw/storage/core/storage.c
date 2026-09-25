#include "storage.h"

#include <string.h>

#include "diskio.h"
#include "stdiskio.h"

#define ST_FW_MAJOR 1
#define ST_FW_MINOR 0

enum { H_CLOSED, H_READ, H_WRITE, H_LOST };

static uint32_t le32(const uint8_t *p)
{
	return (uint32_t)p[0] | (uint32_t)p[1] << 8 | (uint32_t)p[2] << 16 | (uint32_t)p[3] << 24;
}

static void put32(uint8_t *p, uint32_t v)
{
	p[0] = (uint8_t)v;
	p[1] = (uint8_t)(v >> 8);
	p[2] = (uint8_t)(v >> 16);
	p[3] = (uint8_t)(v >> 24);
}

/* ------------------------------------------------------------ card engine side */

uint8_t st_status(const storage_t *s)
{
	return (uint8_t)((s->present ? ST_S_MEDIA : 0) | (s->present && s->mounted ? ST_S_MOUNTED : 0) |
	                 (st_busy(s) ? ST_S_BUSY : 0) | (s->present && s->wp ? ST_S_WP : 0));
}

bool st_busy(const storage_t *s)
{
	return s->q_count != 0 || s->running;
}

/* A frame the worker can run without reading past its end. Anything else is
 * malformed: counted, and never answered (as every card's commands). */
static bool well_formed(const uint8_t *f, int len)
{
	switch (f[0]) {
	case ST_INFO: case ST_MOUNT: case ST_EJECT: case ST_DIR_FIRST: case ST_DIR_NEXT:
		return true;
	case ST_F_OPEN:                                 /* h, mode, len, name */
		return len >= 4 && f[2] <= 2 && len >= 4 + f[3];
	case ST_F_READ:                                 /* h, n */
		return len >= 3 && f[2] <= ST_CHUNK;
	case ST_F_WRITE:                                /* h, n, data */
		return len >= 3 && f[2] <= ST_CHUNK && len == 3 + f[2];
	case ST_F_CLOSE:
		return len >= 2;
	case ST_F_SEEK:                                 /* h, pos32 */
		return len >= 6;
	case ST_F_DELETE:                               /* len, name */
		return len >= 2 && len >= 2 + f[1];
	case ST_F_RENAME:                               /* len, old, len, new */
		return len >= 3 && len >= 3 + f[1] && len >= 3 + f[1] + f[2 + f[1]];
	case ST_BLK_READ: case ST_BLK_WRITE:            /* lba32 */
		return len >= 5;
	case ST_BUF_GET:                                /* off16, n */
		return len >= 4 && f[3] >= 1 && f[3] <= ST_CHUNK && (f[1] | f[2] << 8) + f[3] <= 512;
	case ST_BUF_PUT:                                /* off16, n, data */
		return len >= 4 && f[3] <= ST_CHUNK && (f[1] | f[2] << 8) + f[3] <= 512 && len == 4 + f[3];
	default:
		return false;
	}
}

static void enqueue(storage_t *s, const uint8_t *f, int len)
{
	if (s->q_count == ST_QUEUE) {
		s->card.errors++;              /* the host did not wait for its answers */
		s->seq++;
		return;
	}
	st_req_t *r = &s->queue[(s->q_head + s->q_count) % ST_QUEUE];
	memcpy(r->data, f, (size_t)len);
	r->len = len;
	r->seq = ++s->seq;                 /* the latest command: older answers are dropped */
	s->q_count++;
}

static void command(card_t *c, const uint8_t *f, int len)
{
	storage_t *s = c->priv;
	if (len > ST_REQ_MAX || !well_formed(f, len)) {
		s->seq++;                      /* still a new command: an older answer is not delivered */
		c->errors++;
		return;
	}
	enqueue(s, f, len);
}

static void soft_reset(card_t *c)
{
	storage_t *s = c->priv;
	s->q_count = 0;
	uint8_t r = ST_INTERNAL_RESET;     /* the worker closes (and flushes) every file */
	enqueue(s, &r, 1);
}

static uint8_t status(card_t *c) { return st_status(c->priv); }

static const card_ops_t st_ops = {
	.type = CARD_TYPE_STORAGE, .fw_major = ST_FW_MAJOR, .fw_minor = ST_FW_MINOR,
	.status = status, .command = command, .soft_reset = soft_reset,
};

bool st_take(storage_t *s, st_req_t *req)
{
	if (s->running || !s->q_count)
		return false;
	*req = s->queue[s->q_head];
	s->q_head = (s->q_head + 1) % ST_QUEUE;
	s->q_count--;
	s->running = true;
	return true;
}

void st_done(storage_t *s, uint32_t seq, const uint8_t *resp, int len)
{
	s->running = false;
	/* only the latest command's answer, and never over another command's
	 * (an IDENT sent meanwhile has its own) */
	if (len > 0 && seq == s->seq && !s->card.resp_ready)
		card_respond(&s->card, resp, len);
}

void st_detect(storage_t *s, bool present)
{
	if (present == s->present)
		return;
	s->present = present;
	if (!present)
		s->mounted = false;            /* at once; the worker drops the volume next */
	s->detect_gen++;
}

void st_init(storage_t *s, const st_disk_t *disk, void *ctx, bool present)
{
	memset(s, 0, sizeof *s);
	card_init(&s->card, &st_ops, s);
	s->disk = disk;
	s->ctx = ctx;
	s->present = present;
	s->detect_gen = 1;                 /* the worker's first st_service mounts */
	st_diskio_bind(s);
}

/* ------------------------------------------------------------ worker side */

static uint8_t fr_err(const storage_t *s, FRESULT fr)
{
	if (fr != FR_OK && !s->present)
		return ST_E_NO_MEDIUM;         /* pulled during the operation */
	switch (fr) {
	case FR_OK: return ST_OK;
	case FR_NO_FILE: case FR_NO_PATH: return ST_E_NOT_FOUND;
	case FR_INVALID_NAME: return ST_E_BAD_NAME;
	case FR_DENIED: return ST_E_FULL;              /* directory full (read-only files: see fr_denied) */
	case FR_EXIST: return ST_E_EXISTS;
	case FR_INVALID_OBJECT: return ST_E_BAD_HANDLE;
	case FR_WRITE_PROTECTED: return ST_E_WP;
	case FR_INVALID_DRIVE: case FR_NOT_ENABLED: case FR_NO_FILESYSTEM: return ST_E_NOT_MOUNTED;
	case FR_LOCKED: case FR_TOO_MANY_OPEN_FILES: return ST_E_TOO_MANY;
	default: return ST_E_IO;
	}
}

/* FR_DENIED on a name: a read-only file or a directory, else the directory is full */
static uint8_t fr_denied(const char *name)
{
	FILINFO fi;
	if (f_stat(name, &fi) == FR_OK) {
		if (fi.fattrib & AM_DIR)
			return ST_E_BAD_NAME;
		if (fi.fattrib & AM_RDO)
			return ST_E_WP;
	}
	return ST_E_FULL;
}

/* A length-prefixed 8.3 name into out (NUL-terminated): printable ASCII, no
 * paths; FatFs checks the rest of the 8.3 rules. */
static bool get_name(const uint8_t *p, char out[ST_NAME_MAX + 1])
{
	int n = p[0];
	if (n < 1 || n > ST_NAME_MAX || p[1] == '.')
		return false;
	for (int i = 0; i < n; i++) {
		uint8_t ch = p[1 + i];
		if (ch <= ' ' || ch >= 0x7F || ch == '/' || ch == '\\' || ch == ':')
			return false;
		out[i] = (char)ch;
	}
	out[n] = 0;
	return true;
}

static uint8_t need_mounted(const storage_t *s)
{
	if (!s->present)
		return ST_E_NO_MEDIUM;
	return s->mounted ? ST_OK : ST_E_NOT_MOUNTED;
}

static uint8_t do_mount(storage_t *s)
{
	if (!s->present)
		return ST_E_NO_MEDIUM;
	if (s->mounted)
		return ST_OK;
	FRESULT fr = f_mount(&s->fs, "", 1);
	s->wp = s->disk->write_protected(s->ctx);
	s->mounted = fr == FR_OK && s->present;
	return fr_err(s, fr);
}

static void drop_files(storage_t *s, uint8_t to)
{
	for (int h = 0; h < ST_HANDLES; h++)
		if (s->hmode[h] == H_READ || s->hmode[h] == H_WRITE)
			s->hmode[h] = to;
	s->dir_open = false;
}

/* close every file, flushing; the first error */
static uint8_t close_all(storage_t *s)
{
	uint8_t e = ST_OK;
	for (int h = 0; h < ST_HANDLES; h++) {
		if (s->hmode[h] == H_READ || s->hmode[h] == H_WRITE) {
			uint8_t r = fr_err(s, f_close(&s->fil[h]));
			if (!e)
				e = r;
		}
		s->hmode[h] = H_CLOSED;
	}
	if (s->dir_open)
		f_closedir(&s->dir);
	s->dir_open = false;
	return e;
}

void st_service(storage_t *s)
{
	uint32_t gen = s->detect_gen;
	if (gen == s->seen_gen)
		return;
	s->seen_gen = gen;
	/* the medium changed: whatever was open was on the old one */
	drop_files(s, H_LOST);
	f_mount(0, "", 0);
	s->mounted = false;
	s->wp = false;
	st_diskio_reset();
	if (s->present)
		s->err = do_mount(s);          /* mount on insertion */
}

/* the handle for a file operation, or an error */
static uint8_t handle(const storage_t *s, uint8_t h, int want)
{
	if (h >= ST_HANDLES || s->hmode[h] == H_CLOSED)
		return ST_E_BAD_HANDLE;
	if (s->hmode[h] == H_LOST || !s->present)
		return ST_E_NO_MEDIUM;
	if (want && s->hmode[h] != want)
		return ST_E_BAD_HANDLE;
	return ST_OK;
}

static int f_open_cmd(storage_t *s, const uint8_t *f)
{
	uint8_t h = f[1], mode = f[2];
	char name[ST_NAME_MAX + 1];
	if (h >= ST_HANDLES)
		return ST_E_BAD_HANDLE;
	/* reusing an open handle closes it first (a program that stopped
	 * half-way must not lock its handle until the next reset) */
	if (s->hmode[h] == H_READ || s->hmode[h] == H_WRITE)
		f_close(&s->fil[h]);
	s->hmode[h] = H_CLOSED;
	uint8_t e = need_mounted(s);
	if (e)
		return e;
	if (!get_name(f + 3, name))
		return ST_E_BAD_NAME;
	static const BYTE modes[3] = { FA_READ, FA_WRITE | FA_CREATE_ALWAYS, FA_WRITE | FA_OPEN_APPEND };
	FRESULT fr = f_open(&s->fil[h], name, modes[mode]);
	if (fr == FR_OK)
		s->hmode[h] = mode ? H_WRITE : H_READ;
	return fr == FR_DENIED ? fr_denied(name) : fr_err(s, fr);
}

static int f_read_cmd(storage_t *s, const uint8_t *f, uint8_t *resp)
{
	uint8_t h = f[1], n = f[2];
	uint8_t e = handle(s, h, H_READ);
	UINT got = 0;
	if (!e)
		e = fr_err(s, f_read(&s->fil[h], resp + 1, n, &got));
	s->err = e;
	if (e) {
		resp[0] = ST_READ_ERR;
		resp[1] = e;
		return 2;
	}
	resp[0] = (uint8_t)got;
	return 1 + (int)got;
}

static int f_write_cmd(storage_t *s, const uint8_t *f)
{
	uint8_t h = f[1], n = f[2];
	uint8_t e = handle(s, h, H_WRITE);
	if (e)
		return e;
	UINT put = 0;
	e = fr_err(s, f_write(&s->fil[h], f + 3, n, &put));
	if (!e && put < n)
		e = ST_E_FULL;
	return e;
}

static int f_close_cmd(storage_t *s, uint8_t h)
{
	uint8_t e = handle(s, h, 0);
	if (h < ST_HANDLES && s->hmode[h] == H_LOST)
		s->hmode[h] = H_CLOSED;        /* forgotten; the data went with the medium */
	if (e)
		return e;
	s->hmode[h] = H_CLOSED;
	return fr_err(s, f_close(&s->fil[h]));
}

/* the next directory entry: size32, attr, len, name; or $FF at the end */
static int dir_entry(storage_t *s, uint8_t *resp)
{
	FILINFO fi;
	FRESULT fr = f_readdir(&s->dir, &fi);
	if (fr != FR_OK || !fi.fname[0]) {
		f_closedir(&s->dir);
		s->dir_open = false;
		s->err = fr_err(s, fr);
		resp[0] = fr == FR_OK ? ST_DIR_END : s->err;
		return 1;
	}
	s->err = ST_OK;
	int n = (int)strlen(fi.fname);
	put32(resp, (uint32_t)fi.fsize);
	resp[4] = fi.fattrib;
	resp[5] = (uint8_t)n;
	memcpy(resp + 6, fi.fname, (size_t)n);
	return 6 + n;
}

static int dir_cmd(storage_t *s, bool first, uint8_t *resp)
{
	uint8_t e = need_mounted(s);
	if (!e && first) {
		if (s->dir_open)
			f_closedir(&s->dir);
		s->dir_open = false;
		e = fr_err(s, f_opendir(&s->dir, ""));
		s->dir_open = e == ST_OK;
	}
	if (e) {
		s->err = e;
		resp[0] = e;
		return 1;
	}
	if (!s->dir_open) {
		s->err = ST_OK;
		resp[0] = ST_DIR_END;          /* DIR_NEXT after the end, or without DIR_FIRST */
		return 1;
	}
	return dir_entry(s, resp);
}

static int f_delete_cmd(storage_t *s, const uint8_t *f)
{
	char name[ST_NAME_MAX + 1];
	uint8_t e = need_mounted(s);
	if (e)
		return e;
	if (!get_name(f + 1, name))
		return ST_E_BAD_NAME;
	FILINFO fi;
	FRESULT fr = f_stat(name, &fi);
	if (fr == FR_OK && (fi.fattrib & AM_DIR))
		return ST_E_BAD_NAME;          /* files only */
	if (fr == FR_OK)
		fr = f_unlink(name);
	return fr == FR_DENIED ? fr_denied(name) : fr_err(s, fr);
}

static int f_rename_cmd(storage_t *s, const uint8_t *f)
{
	char from[ST_NAME_MAX + 1], to[ST_NAME_MAX + 1];
	uint8_t e = need_mounted(s);
	if (e)
		return e;
	if (!get_name(f + 1, from) || !get_name(f + 2 + f[1], to))
		return ST_E_BAD_NAME;
	FRESULT fr = f_rename(from, to);
	return fr == FR_DENIED ? fr_denied(from) : fr_err(s, fr);
}

/* raw sectors bypass the file system: flush it first, and make it read
 * again whatever a raw write may have changed */
static int blk_cmd(storage_t *s, bool write, uint32_t lba)
{
	if (!s->present)
		return ST_E_NO_MEDIUM;
	if (disk_initialize(0) & STA_NOINIT)
		return ST_E_IO;
	if (lba >= s->disk->sectors(s->ctx))
		return ST_E_IO;
	if (!write)
		return disk_read(0, s->buf, lba, 1) == RES_OK ? ST_OK : ST_E_IO;
	if (s->disk->write_protected(s->ctx))
		return ST_E_WP;
	for (int h = 0; h < ST_HANDLES; h++)
		if (s->hmode[h] == H_WRITE)
			f_sync(&s->fil[h]);
	DRESULT r = disk_write(0, s->buf, lba, 1);
	if (s->mounted)
		s->fs.winsect = (LBA_t)0 - 1;  /* FatFs's sector window: read it again */
	return r == RES_OK ? ST_OK : ST_E_IO;
}

static int info_cmd(storage_t *s, uint8_t *resp)
{
	uint32_t free_kb = 0, total_kb = 0;
	if (s->present && s->mounted) {
		DWORD clusters;
		FATFS *fs;
		if (f_getfree("", &clusters, &fs) == FR_OK) {
			free_kb = clusters * fs->csize / 2;
			total_kb = (fs->n_fatent - 2) * fs->csize / 2;
		}
	} else if (s->present && !(disk_initialize(0) & STA_NOINIT)) {
		total_kb = s->disk->sectors(s->ctx) / 2;
	}
	resp[0] = s->present ? s->disk->media : ST_MEDIA_NONE;
	resp[1] = s->err;
	resp[2] = (uint8_t)(st_status(s) & ~ST_S_BUSY);
	put32(resp + 3, free_kb);
	put32(resp + 7, total_kb);
	return 11;
}

int st_exec(storage_t *s, const uint8_t *f, int len, uint8_t resp[CARD_RESP_MAX])
{
	(void)len;                         /* checked by well_formed() when it was queued */
	st_service(s);
	int e;
	switch (f[0]) {
	case ST_INFO:
		return info_cmd(s, resp);
	case ST_F_READ:
		return f_read_cmd(s, f, resp);
	case ST_DIR_FIRST: case ST_DIR_NEXT:
		return dir_cmd(s, f[0] == ST_DIR_FIRST, resp);
	case ST_BUF_GET:
		memcpy(resp, s->buf + (f[1] | f[2] << 8), f[3]);
		return f[3];
	case ST_BUF_PUT:
		memcpy(s->buf + (f[1] | f[2] << 8), f + 4, f[3]);
		return -1;
	case ST_INTERNAL_RESET:
		close_all(s);
		return -1;
	case ST_MOUNT: e = do_mount(s); break;
	case ST_EJECT:
		e = close_all(s);
		/* a raw BLK_WRITE has no sync after it: wait until the medium has
		 * programmed it (an SD card: busy until DO goes high), since the
		 * card may be pulled as soon as EJECT answers */
		if (disk_ioctl(0, CTRL_SYNC, 0) == RES_ERROR && !e)
			e = ST_E_IO;
		f_mount(0, "", 0);
		s->mounted = false;
		break;
	case ST_F_OPEN: e = f_open_cmd(s, f); break;
	case ST_F_WRITE: e = f_write_cmd(s, f); break;
	case ST_F_CLOSE: e = f_close_cmd(s, f[1]); break;
	case ST_F_SEEK:
		e = handle(s, f[1], 0);
		if (!e)
			e = fr_err(s, f_lseek(&s->fil[f[1]], le32(f + 2)));
		break;
	case ST_F_DELETE: e = f_delete_cmd(s, f); break;
	case ST_F_RENAME: e = f_rename_cmd(s, f); break;
	case ST_BLK_READ: e = blk_cmd(s, false, le32(f + 1)); break;
	case ST_BLK_WRITE: e = blk_cmd(s, true, le32(f + 1)); break;
	default:
		return -1;
	}
	s->err = (uint8_t)e;
	resp[0] = (uint8_t)e;
	return 1;
}

void st_poll(storage_t *s)
{
	st_req_t r;
	uint8_t resp[CARD_RESP_MAX];
	st_service(s);
	while (st_take(s, &r))
		st_done(s, r.seq, resp, st_exec(s, r.data, r.len, resp));
}
