/* STO-001/002 (host part): the storage card core (doc/hardware/storage-card.md)
 * on FatFs over in-memory disk images, through the slot protocol.
 *
 *   test_storage                 the command tests
 *   test_storage PC.img          also read the files a PC wrote (tools/fatcheck.py mkimg)
 *
 * It leaves $OUT/storage_card.img and the files it should hold in
 * $OUT/storage_expect/, for tools/fatcheck.py to check with a PC's FAT reader. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/wait.h>
#include <unistd.h>

#include "check.h"
#include "imgdisk.h"
#include "storage.h"

static storage_t st;
static imgdisk_t *disk;
static uint8_t resp[256];

/* a command frame; `poll` runs the worker afterwards */
static void send(const uint8_t *f, int len, bool poll)
{
	card_frame(&st.card, f, 0, len);
	if (poll)
		st_poll(&st);
}

/* a READ frame: RESP_LEN, the response in resp */
static int read_resp(void)
{
	uint8_t mosi[257] = {CARD_OP_READ}, miso[257];
	card_frame(&st.card, mosi, miso, 257);
	memcpy(resp, miso + 2, 255);
	return miso[1];
}

/* command, worker, READ: RESP_LEN */
static int cmd(const uint8_t *f, int len)
{
	send(f, len, true);
	return read_resp();
}

/* a command answered with one error byte */
static int ecmd(const uint8_t *f, int len)
{
	int n = cmd(f, len);
	return n == 1 ? resp[0] : -1000 - n;
}

static uint8_t status(void)
{
	card_select(&st.card, true);
	uint8_t s = card_next_miso(&st.card);
	card_select(&st.card, false);
	return s;
}

/* frames with a length-prefixed name */
static int t_open(uint8_t h, uint8_t mode, const char *name)
{
	uint8_t f[64] = {ST_F_OPEN, h, mode, (uint8_t)strlen(name)};
	memcpy(f + 4, name, strlen(name));
	return ecmd(f, 4 + (int)strlen(name));
}

static int t_write(uint8_t h, const uint8_t *data, int n)
{
	uint8_t f[3 + ST_CHUNK] = {ST_F_WRITE, h, (uint8_t)n};
	memcpy(f + 3, data, (size_t)n);
	return ecmd(f, 3 + n);
}

/* F_READ: n', data in resp+1 */
static int t_read(uint8_t h, uint8_t n)
{
	uint8_t f[3] = {ST_F_READ, h, n};
	int len = cmd(f, 3);
	CHECK(len >= 1, "F_READ answered");
	if (resp[0] == ST_READ_ERR)
		CHECK_EQ(len, 2);
	else
		CHECK_EQ(len, 1 + resp[0]);
	return resp[0];
}

static int t_close(uint8_t h)
{
	uint8_t f[2] = {ST_F_CLOSE, h};
	return ecmd(f, 2);
}

static int t_seek(uint8_t h, uint32_t pos)
{
	uint8_t f[6] = {ST_F_SEEK, h, (uint8_t)pos, (uint8_t)(pos >> 8), (uint8_t)(pos >> 16), (uint8_t)(pos >> 24)};
	return ecmd(f, 6);
}

static int t_delete(const char *name)
{
	uint8_t f[64] = {ST_F_DELETE, (uint8_t)strlen(name)};
	memcpy(f + 2, name, strlen(name));
	return ecmd(f, 2 + (int)strlen(name));
}

static int t_rename(const char *from, const char *to)
{
	int a = (int)strlen(from), b = (int)strlen(to);
	uint8_t f[64] = {ST_F_RENAME, (uint8_t)a};
	memcpy(f + 2, from, (size_t)a);
	f[2 + a] = (uint8_t)b;
	memcpy(f + 3 + a, to, (size_t)b);
	return ecmd(f, 3 + a + b);
}

static int simple(uint8_t op)
{
	return ecmd(&op, 1);
}

static uint32_t le32(const uint8_t *p)
{
	return (uint32_t)p[0] | (uint32_t)p[1] << 8 | (uint32_t)p[2] << 16 | (uint32_t)p[3] << 24;
}

/* ST_INFO into resp: media, err, flags, free, total */
static void info(void)
{
	uint8_t op = ST_INFO;
	CHECK_EQ(cmd(&op, 1), 11);
}

static uint8_t pattern(uint32_t i, uint32_t seed) { return (uint8_t)(i * 7 + seed + (i >> 8)); }

/* write `size` bytes of pattern `seed` as `name`, in chunks of `chunk` */
static void write_file(const char *name, uint32_t size, uint32_t seed, int chunk)
{
	uint8_t buf[ST_CHUNK];
	CHECK_EQ(t_open(0, 1, name), ST_OK);
	for (uint32_t pos = 0; pos < size; pos += (uint32_t)chunk) {
		int n = size - pos < (uint32_t)chunk ? (int)(size - pos) : chunk;
		for (int i = 0; i < n; i++)
			buf[i] = pattern(pos + (uint32_t)i, seed);
		CHECK_EQ(t_write(0, buf, n), ST_OK);
	}
	CHECK_EQ(t_close(0), ST_OK);
}

/* read `name` back in chunks of `chunk`: its size, checking the pattern */
static uint32_t read_file(const char *name, uint32_t seed, int chunk)
{
	uint32_t pos = 0;
	int bad = 0;
	CHECK_EQ(t_open(1, 0, name), ST_OK);
	for (;;) {
		int n = t_read(1, (uint8_t)chunk);
		if (n == ST_READ_ERR)
			break;
		for (int i = 0; i < n; i++)
			bad += resp[1 + i] != pattern(pos + (uint32_t)i, seed);
		pos += (uint32_t)n;
		if (n < chunk)
			break;
	}
	CHECK(bad == 0, "%s: %d bytes differ", name, bad);
	CHECK_EQ(t_close(1), ST_OK);
	return pos;
}

/* a fresh core on a new formatted image */
static void fresh(uint32_t sectors)
{
	imgdisk_free(disk);
	disk = imgdisk_new(sectors);
	CHECK(imgdisk_format(disk) == 0, "format %u sectors", sectors);
	st_init(&st, &imgdisk_ops, disk, true);
	st_poll(&st);
}

/* the file's size as a second, independent core sees the medium now: what
 * a PC would read if the card were pulled this moment. In a child process,
 * since FatFs has one volume and ours stays mounted. */
static long size_on_medium(const char *name)
{
	int fds[2];
	long size = -1;
	if (pipe(fds))
		return -2;
	fflush(0);
	pid_t pid = fork();
	if (pid == 0) {
		static storage_t other;
		uint8_t f[20] = {ST_F_OPEN, 0, 0, (uint8_t)strlen(name)}, r[CARD_RESP_MAX];
		memcpy(f + 4, name, strlen(name));
		st_init(&other, &imgdisk_ops, disk, true);
		disk->fd = -1;                             /* never write through */
		st_service(&other);
		if (st_exec(&other, f, 4 + (int)strlen(name), r) == 1 && r[0] == ST_OK)
			size = (long)f_size(&other.fil[0]);
		if (write(fds[1], &size, sizeof size) != sizeof size)
			_exit(1);
		_exit(0);
	}
	close(fds[1]);
	if (read(fds[0], &size, sizeof size) != sizeof size)
		size = -3;
	close(fds[0]);
	waitpid(pid, 0, 0);
	return size;
}

static void protocol(void)
{
	fresh(8192);                                     /* 4 MB: FAT16 */
	uint8_t r[4];
	card_frame(&st.card, (uint8_t[]){CARD_OP_IDENT}, 0, 1);
	CHECK_EQ(read_resp(), 4);
	memcpy(r, resp, 4);
	CHECK(r[0] == CARD_TYPE_STORAGE && r[3] == CARD_IDENT_SIG, "IDENT type $04");

	CHECK_EQ(status(), ST_S_MEDIA | ST_S_MOUNTED);   /* mounted on insertion */
	info();
	CHECK_EQ(resp[0], ST_MEDIA_SD);
	CHECK_EQ(resp[1], ST_OK);
	CHECK_EQ(resp[2], ST_S_MEDIA | ST_S_MOUNTED);
	uint32_t free0 = le32(resp + 3), total = le32(resp + 7);
	CHECK(total > 3900 && total <= 4096, "total %u KB", total);
	CHECK(free0 > 3900 && free0 <= total, "free %u KB", free0);

	/* not ready (and BUSY) until the worker has run it */
	send((uint8_t[]){ST_INFO}, 1, false);
	CHECK_EQ(status() & ST_S_BUSY, ST_S_BUSY);
	CHECK_EQ(read_resp(), 0);
	st_poll(&st);
	CHECK_EQ(status() & ST_S_BUSY, 0);
	CHECK_EQ(read_resp(), 11);

	/* a new command discards the older answer, even one still running */
	t_open(0, 1, "A.TXT");
	send((uint8_t[]){ST_F_WRITE, 0, 1, 'x'}, 4, false);
	send((uint8_t[]){ST_INFO}, 1, false);
	st_poll(&st);
	CHECK_EQ(read_resp(), 11);                        /* ST_INFO's, not F_WRITE's */
	/* and an IDENT sent while one runs keeps its own answer */
	send((uint8_t[]){ST_F_CLOSE, 0}, 2, false);
	card_frame(&st.card, (uint8_t[]){CARD_OP_IDENT}, 0, 1);
	st_poll(&st);
	CHECK_EQ(read_resp(), 4);
	CHECK_EQ(resp[3], CARD_IDENT_SIG);
	CHECK_EQ(size_on_medium("A.TXT"), 1);            /* both ran */

	/* more commands than the queue holds without waiting: counted */
	uint32_t e = st.card.errors;
	for (int i = 0; i < ST_QUEUE + 1; i++)
		send((uint8_t[]){ST_INFO}, 1, false);
	CHECK_EQ(st.card.errors, e + 1);
	st_poll(&st);
	CHECK_EQ(read_resp(), 0);                         /* the dropped one was the latest */

	/* malformed frames: counted, never answered */
	const struct { uint8_t f[8]; int len; } bad[] = {
		{{ST_F_OPEN, 0, 0}, 3},                       /* no name length */
		{{ST_F_OPEN, 0, 0, 5, 'A', 'B'}, 6},          /* name shorter than its length */
		{{ST_F_OPEN, 0, 3, 1, 'A'}, 5},               /* mode 3 */
		{{ST_F_READ, 0}, 2},
		{{ST_F_READ, 0, 129}, 3},                     /* > 128 */
		{{ST_F_WRITE, 0, 2, 'a'}, 4},                 /* shorter than n */
		{{ST_F_WRITE, 0, 1, 'a', 'b'}, 5},            /* longer than n */
		{{ST_F_CLOSE}, 1},
		{{ST_F_SEEK, 0, 1, 2}, 4},
		{{ST_F_DELETE}, 1},
		{{ST_F_DELETE, 3, 'A'}, 3},
		{{ST_F_RENAME, 1, 'A'}, 3},
		{{ST_F_RENAME, 1, 'A', 2, 'B'}, 5},
		{{ST_BLK_READ, 0, 0}, 3},
		{{ST_BLK_WRITE}, 1},
		{{ST_BUF_GET, 0, 0}, 3},
		{{ST_BUF_GET, 0, 2, 1}, 4},                   /* 512 + 1 */
		{{ST_BUF_GET, 0, 0, 0}, 4},                   /* 0 bytes */
		{{ST_BUF_GET, 0, 0, 129}, 4},
		{{ST_BUF_PUT, 0, 0, 2, 1}, 5},
		{{0x30}, 1},                                  /* not a storage opcode */
		{{0x04}, 1},
	};
	for (unsigned i = 0; i < sizeof bad / sizeof bad[0]; i++) {
		e = st.card.errors;
		send(bad[i].f, bad[i].len, true);
		CHECK(st.card.errors == e + 1, "malformed frame %u counted", i);
		CHECK(read_resp() == 0, "malformed frame %u answered", i);
	}
	uint8_t big[ST_REQ_MAX + 1] = {ST_BUF_PUT};
	e = st.card.errors;
	send(big, sizeof big, true);
	CHECK_EQ(st.card.errors, e + 1);
}

static void files(void)
{
	fresh(8192);
	/* chunking: sizes around the 128-byte chunks and the 512-byte sectors,
	 * written and read in several chunk sizes */
	const uint32_t sizes[] = {0, 1, 127, 128, 129, 511, 512, 513, 2048, 2049, 5000};
	for (unsigned i = 0; i < sizeof sizes / sizeof sizes[0]; i++) {
		char name[16];
		snprintf(name, sizeof name, "F%u.DAT", i);
		write_file(name, sizes[i], i, i % 2 ? 128 : 100);
		CHECK_EQ(size_on_medium(name), sizes[i]);   /* on the medium once closed */
		CHECK_EQ(read_file(name, i, 128), sizes[i]);
		CHECK_EQ(read_file(name, i, 37), sizes[i]);
	}
	/* end of file: n' < n, then 0 */
	CHECK_EQ(t_open(2, 0, "F2.DAT"), ST_OK);         /* 127 bytes */
	CHECK_EQ(t_read(2, 128), 127);
	CHECK_EQ(t_read(2, 128), 0);
	CHECK_EQ(t_read(2, 0), 0);
	/* seek */
	CHECK_EQ(t_seek(2, 100), ST_OK);
	CHECK_EQ(t_read(2, 5), 5);
	CHECK_EQ(resp[1], pattern(100, 2));
	CHECK_EQ(t_seek(2, 1000), ST_OK);                /* past the end of a read file: at the end */
	CHECK_EQ(t_read(2, 5), 0);
	CHECK_EQ(t_close(2), ST_OK);

	/* append */
	CHECK_EQ(t_open(0, 2, "F2.DAT"), ST_OK);
	uint8_t more[3] = {pattern(127, 2), pattern(128, 2), pattern(129, 2)};
	CHECK_EQ(t_write(0, more, 3), ST_OK);
	CHECK_EQ(t_close(0), ST_OK);
	CHECK_EQ(read_file("F2.DAT", 2, 128), 130);
	/* write truncates */
	write_file("F2.DAT", 10, 9, 128);
	CHECK_EQ(read_file("F2.DAT", 9, 128), 10);
	/* append creates */
	CHECK_EQ(t_open(0, 2, "NEW.TXT"), ST_OK);
	CHECK_EQ(t_close(0), ST_OK);
	CHECK_EQ(size_on_medium("NEW.TXT"), 0);

	/* handles: four at once, independent */
	const char *names[4] = {"H0.TXT", "H1.TXT", "H2.TXT", "H3.TXT"};
	for (int h = 0; h < 4; h++)
		CHECK_EQ(t_open((uint8_t)h, 1, names[h]), ST_OK);
	for (int round = 0; round < 3; round++)
		for (int h = 0; h < 4; h++) {
			uint8_t b[50];
			for (int i = 0; i < 50; i++)
				b[i] = pattern((uint32_t)(round * 50 + i), (uint32_t)h + 20);
			CHECK_EQ(t_write((uint8_t)h, b, 50), ST_OK);
		}
	for (int h = 0; h < 4; h++)
		CHECK_EQ(t_close((uint8_t)h), ST_OK);
	for (int h = 0; h < 4; h++)
		CHECK_EQ(read_file(names[h], (uint32_t)h + 20, 128), 150);
	CHECK_EQ(t_open(4, 0, "H0.TXT"), ST_E_BAD_HANDLE);
	CHECK_EQ(t_open(255, 0, "H0.TXT"), ST_E_BAD_HANDLE);
	CHECK_EQ(t_close(0), ST_E_BAD_HANDLE);           /* not open */
	CHECK_EQ(t_close(4), ST_E_BAD_HANDLE);
	CHECK_EQ(t_seek(3, 0), ST_E_BAD_HANDLE);
	CHECK_EQ(t_read(0, 10), ST_READ_ERR);
	CHECK_EQ(resp[1], ST_E_BAD_HANDLE);
	CHECK_EQ(t_write(0, (uint8_t *)"x", 1), ST_E_BAD_HANDLE);
	/* the wrong direction */
	CHECK_EQ(t_open(0, 0, "H0.TXT"), ST_OK);
	CHECK_EQ(t_write(0, (uint8_t *)"x", 1), ST_E_BAD_HANDLE);
	CHECK_EQ(t_open(1, 1, "H1.TXT"), ST_OK);
	CHECK_EQ(t_read(1, 10), ST_READ_ERR);
	CHECK_EQ(resp[1], ST_E_BAD_HANDLE);
	/* a file open for write on one handle cannot be opened on another */
	CHECK_EQ(t_open(2, 0, "H1.TXT"), ST_E_TOO_MANY);
	CHECK_EQ(t_open(2, 1, "H1.TXT"), ST_E_TOO_MANY);
	CHECK_EQ(t_delete("H1.TXT"), ST_E_TOO_MANY);
	/* reopening an open handle closes (and flushes) what it had */
	CHECK_EQ(t_write(1, (uint8_t *)"hello", 5), ST_OK);
	CHECK_EQ(t_open(1, 0, "H2.TXT"), ST_OK);
	CHECK_EQ(size_on_medium("H1.TXT"), 5);
	CHECK_EQ(t_close(0), ST_OK);
	CHECK_EQ(t_close(1), ST_OK);
	CHECK_EQ(t_open(0, 0, "NOSUCH.TXT"), ST_E_NOT_FOUND);

	/* SOFT_RESET closes and flushes every file */
	CHECK_EQ(t_open(3, 1, "RESET.TXT"), ST_OK);
	CHECK_EQ(t_write(3, (uint8_t *)"abc", 3), ST_OK);
	card_frame(&st.card, (uint8_t[]){CARD_OP_SOFT_RESET}, 0, 1);
	st_poll(&st);
	CHECK_EQ(size_on_medium("RESET.TXT"), 3);
	CHECK_EQ(t_close(3), ST_E_BAD_HANDLE);
}

static void names(void)
{
	fresh(8192);
	const char *bad[] = {
		"TOOLONGNA.BAS",       /* 9-character base */
		"ABCDEFGHIJKLM",       /* 13 characters */
		"A.BASI",              /* 4-character extension */
		"A/B", "A\\B", "A B", "A*B", "A?B", "A:B", "A\"B", "A<B", "A|B", "A+B", "A,B", "A;B", "A=B", "A[B",
		".X", "..", ".", "A.B.C", "",
	};
	for (unsigned i = 0; i < sizeof bad / sizeof bad[0]; i++) {
		CHECK(t_open(0, 1, bad[i]) == ST_E_BAD_NAME, "name \"%s\" refused", bad[i]);
		CHECK(t_delete(bad[i]) == ST_E_BAD_NAME, "delete \"%s\" refused", bad[i]);
	}
	CHECK_EQ(t_open(0, 1, "\x01X"), ST_E_BAD_NAME);
	CHECK_EQ(t_open(0, 1, "X\x80"), ST_E_BAD_NAME);
	const char *good[] = {"A", "ABCDEFGH.BAS", "12345678.123", "X_Y-Z.$$$", "NOEXT", "A.B", "~!@#$%^&.()"};
	for (unsigned i = 0; i < sizeof good / sizeof good[0]; i++) {
		CHECK(t_open(0, 1, good[i]) == ST_OK, "name \"%s\" accepted", good[i]);
		CHECK_EQ(t_close(0), ST_OK);
	}
	/* 8.3 names are upper case: lower case finds the same file */
	write_file("hello.bas", 20, 3, 128);
	CHECK_EQ(read_file("HELLO.BAS", 3, 128), 20);
	CHECK_EQ(read_file("Hello.Bas", 3, 128), 20);

	/* the directory: every file, its size, upper-case names */
	uint8_t op = ST_DIR_FIRST;
	int count = 0, seen_hello = 0;
	for (int n = cmd(&op, 1); n > 1; n = cmd((uint8_t[]){ST_DIR_NEXT}, 1)) {
		CHECK_EQ(n, 6 + resp[5]);
		if (resp[5] == 9 && !memcmp(resp + 6, "HELLO.BAS", 9)) {
			seen_hello++;
			CHECK_EQ(le32(resp), 20);
			CHECK_EQ(resp[4] & 0x10, 0);                /* not a directory */
		}
		count++;
	}
	CHECK_EQ(resp[0], ST_DIR_END);
	CHECK_EQ(count, 8);
	CHECK_EQ(seen_hello, 1);
	CHECK_EQ(cmd((uint8_t[]){ST_DIR_NEXT}, 1), 1);    /* stays at the end */
	CHECK_EQ(resp[0], ST_DIR_END);

	/* delete and rename */
	CHECK_EQ(t_delete("HELLO.BAS"), ST_OK);
	CHECK_EQ(t_open(0, 0, "HELLO.BAS"), ST_E_NOT_FOUND);
	CHECK_EQ(t_delete("HELLO.BAS"), ST_E_NOT_FOUND);
	CHECK_EQ(t_rename("A", "B.TXT"), ST_OK);
	CHECK_EQ(t_open(0, 0, "A"), ST_E_NOT_FOUND);
	CHECK_EQ(t_open(0, 0, "B.TXT"), ST_OK);
	CHECK_EQ(t_close(0), ST_OK);
	CHECK_EQ(t_rename("B.TXT", "NOEXT"), ST_E_EXISTS);
	CHECK_EQ(t_rename("NONE", "C"), ST_E_NOT_FOUND);
	CHECK_EQ(t_rename("B.TXT", "TOOLONGNAME"), ST_E_BAD_NAME);

	/* an empty directory */
	fresh(8192);
	CHECK_EQ(cmd((uint8_t[]){ST_DIR_FIRST}, 1), 1);
	CHECK_EQ(resp[0], ST_DIR_END);
	CHECK_EQ(cmd((uint8_t[]){ST_DIR_NEXT}, 1), 1);
	CHECK_EQ(resp[0], ST_DIR_END);
}

static void full(void)
{
	/* the medium full: F_WRITE says so, and what fitted is kept */
	fresh(200);                                      /* 100 KB, FAT12 */
	info();
	uint32_t free_kb = le32(resp + 3);
	CHECK(free_kb > 50 && free_kb < 100, "free %u KB", free_kb);
	uint8_t b[ST_CHUNK];
	memset(b, 'z', sizeof b);
	CHECK_EQ(t_open(0, 1, "BIG.DAT"), ST_OK);
	uint32_t written = 0;
	int e;
	while ((e = t_write(0, b, ST_CHUNK)) == ST_OK)
		written += ST_CHUNK;
	CHECK_EQ(e, ST_E_FULL);
	CHECK(written + ST_CHUNK > free_kb * 1024 && written < (free_kb + 1) * 1024, "wrote %u of %u KB", written, free_kb);
	CHECK_EQ(t_close(0), ST_OK);
	long size = size_on_medium("BIG.DAT");
	CHECK(size >= (long)written && size < (long)written + ST_CHUNK, "size %ld", size);
	info();
	CHECK_EQ(le32(resp + 3), 0);
	CHECK_EQ(resp[1], ST_OK);                         /* ST_INFO's err: the last command's, F_CLOSE */
	/* an empty file still fits (a directory entry, no cluster)... */
	CHECK_EQ(t_open(0, 1, "EMPTY"), ST_OK);
	CHECK_EQ(t_write(0, b, 1), ST_E_FULL);
	CHECK_EQ(t_close(0), ST_OK);
	info();
	CHECK_EQ(resp[1], ST_OK);
	/* ...and ST_INFO reports the last error */
	CHECK_EQ(t_open(0, 2, "BIG.DAT"), ST_OK);
	CHECK_EQ(t_write(0, b, 1), ST_E_FULL);
	info();
	CHECK_EQ(resp[1], ST_E_FULL);
	CHECK_EQ(t_close(0), ST_OK);

	/* the root directory full (FAT12/16 have a fixed one) */
	fresh(200);
	int made = 0;
	char name[16];
	for (;;) {
		snprintf(name, sizeof name, "E%d", made);
		e = t_open(0, 1, name);
		if (e != ST_OK)
			break;
		CHECK_EQ(t_close(0), ST_OK);
		made++;
		if (made > 2000)
			break;
	}
	CHECK_EQ(e, ST_E_FULL);
	CHECK(made >= 16 && made <= 512, "%d files in the root", made);
}

static void protect(void)
{
	fresh(8192);
	write_file("KEEP.TXT", 300, 5, 128);
	/* a write-protected medium goes in */
	st_detect(&st, false);
	disk->wp = true;
	st_detect(&st, true);
	st_poll(&st);
	CHECK_EQ(status(), ST_S_MEDIA | ST_S_MOUNTED | ST_S_WP);
	info();
	CHECK_EQ(resp[2], ST_S_MEDIA | ST_S_MOUNTED | ST_S_WP);
	CHECK_EQ(t_open(0, 1, "NEW.TXT"), ST_E_WP);
	CHECK_EQ(t_open(0, 2, "KEEP.TXT"), ST_E_WP);
	CHECK_EQ(t_delete("KEEP.TXT"), ST_E_WP);
	CHECK_EQ(t_rename("KEEP.TXT", "K"), ST_E_WP);
	CHECK_EQ(read_file("KEEP.TXT", 5, 128), 300);    /* reading is fine */
	CHECK_EQ(ecmd((uint8_t[]){ST_BLK_WRITE, 1, 0, 0, 0}, 5), ST_E_WP);
	CHECK_EQ(ecmd((uint8_t[]){ST_BLK_READ, 1, 0, 0, 0}, 5), ST_OK);
	uint32_t w = disk->writes;
	CHECK_EQ(w, disk->writes);
	st_detect(&st, false);
	disk->wp = false;
	st_detect(&st, true);
	st_poll(&st);
	CHECK_EQ(status(), ST_S_MEDIA | ST_S_MOUNTED);
	CHECK_EQ(t_open(0, 1, "NEW.TXT"), ST_OK);
	CHECK_EQ(t_close(0), ST_OK);
}

/* the card is pulled during F_WRITE's second sector */
static int pull_after;
static bool pull_hook(imgdisk_t *d, uint32_t lba)
{
	(void)lba;
	if (pull_after-- == 0) {
		st_detect(&st, false);
		d->before_write = 0;
		return false;
	}
	return true;
}

static void removal(void)
{
	fresh(8192);
	write_file("SAFE.TXT", 1000, 7, 128);
	CHECK_EQ(t_open(0, 1, "OPEN.TXT"), ST_OK);
	uint8_t b[ST_CHUNK];
	memset(b, 'q', sizeof b);
	CHECK_EQ(t_write(0, b, ST_CHUNK), ST_OK);
	CHECK_EQ(t_open(1, 0, "SAFE.TXT"), ST_OK);

	/* pulled: unmounted at once, before the worker runs */
	st_detect(&st, false);
	CHECK_EQ(status(), 0);
	send((uint8_t[]){ST_INFO}, 1, false);
	CHECK_EQ(status(), ST_S_BUSY);
	st_poll(&st);
	CHECK_EQ(read_resp(), 11);
	CHECK_EQ(resp[0], ST_MEDIA_NONE);
	CHECK_EQ(resp[2], 0);
	CHECK_EQ(le32(resp + 7), 0);
	/* open handles fail with "no medium" */
	CHECK_EQ(t_write(0, b, 1), ST_E_NO_MEDIUM);
	CHECK_EQ(t_read(1, 10), ST_READ_ERR);
	CHECK_EQ(resp[1], ST_E_NO_MEDIUM);
	CHECK_EQ(t_seek(1, 0), ST_E_NO_MEDIUM);
	CHECK_EQ(t_open(2, 0, "SAFE.TXT"), ST_E_NO_MEDIUM);
	CHECK_EQ(t_delete("SAFE.TXT"), ST_E_NO_MEDIUM);
	CHECK_EQ(cmd((uint8_t[]){ST_DIR_FIRST}, 1), 1);
	CHECK_EQ(resp[0], ST_E_NO_MEDIUM);
	CHECK_EQ(simple(ST_MOUNT), ST_E_NO_MEDIUM);
	CHECK_EQ(ecmd((uint8_t[]){ST_BLK_READ, 0, 0, 0, 0}, 5), ST_E_NO_MEDIUM);
	CHECK_EQ(t_close(0), ST_E_NO_MEDIUM);            /* and closing forgets them */
	CHECK_EQ(t_close(0), ST_E_BAD_HANDLE);

	/* back in: mounted again; handle 1 still refers to the old medium */
	st_detect(&st, true);
	CHECK_EQ(status(), ST_S_MEDIA);
	st_poll(&st);
	CHECK_EQ(status(), ST_S_MEDIA | ST_S_MOUNTED);
	CHECK_EQ(t_read(1, 10), ST_READ_ERR);
	CHECK_EQ(resp[1], ST_E_NO_MEDIUM);
	CHECK_EQ(t_close(1), ST_E_NO_MEDIUM);
	/* lost at most the file being written */
	CHECK_EQ(read_file("SAFE.TXT", 7, 128), 1000);
	CHECK(size_on_medium("OPEN.TXT") >= 0, "the open file's entry");

	/* pulled in the middle of a write */
	CHECK_EQ(t_open(0, 1, "MID.TXT"), ST_OK);
	for (int i = 0; i < 3; i++)
		CHECK_EQ(t_write(0, b, ST_CHUNK), ST_OK);
	pull_after = 1;
	disk->before_write = pull_hook;
	uint8_t big[ST_CHUNK];
	memset(big, 'r', sizeof big);
	int e = ST_OK;
	for (int i = 0; i < 20 && e == ST_OK; i++)
		e = t_write(0, big, ST_CHUNK);
	CHECK_EQ(e, ST_E_NO_MEDIUM);
	CHECK_EQ(status(), 0);
	st_detect(&st, true);
	st_poll(&st);
	CHECK_EQ(read_file("SAFE.TXT", 7, 128), 1000);

	/* ST_EJECT: flush and unmount before the card is pulled */
	CHECK_EQ(t_open(0, 1, "EJECT.TXT"), ST_OK);
	for (int i = 0; i < 100; i++)
		b[i] = pattern((uint32_t)i, 0);
	CHECK_EQ(t_write(0, b, 100), ST_OK);
	CHECK_EQ(simple(ST_EJECT), ST_OK);
	CHECK_EQ(status(), ST_S_MEDIA);
	CHECK_EQ(size_on_medium("EJECT.TXT"), 100);
	CHECK_EQ(t_open(0, 0, "EJECT.TXT"), ST_E_NOT_MOUNTED);
	CHECK_EQ(cmd((uint8_t[]){ST_DIR_FIRST}, 1), 1);
	CHECK_EQ(resp[0], ST_E_NOT_MOUNTED);
	CHECK_EQ(simple(ST_MOUNT), ST_OK);
	CHECK_EQ(status(), ST_S_MEDIA | ST_S_MOUNTED);
	CHECK_EQ(simple(ST_MOUNT), ST_OK);               /* already mounted */
	CHECK_EQ(read_file("EJECT.TXT", 0, 128), 100);

	/* a blank medium: present, not mounted */
	imgdisk_free(disk);
	disk = imgdisk_new(2048);
	st_init(&st, &imgdisk_ops, disk, true);
	st_poll(&st);
	CHECK_EQ(status(), ST_S_MEDIA);
	info();
	CHECK_EQ(resp[0], ST_MEDIA_SD);
	CHECK_EQ(resp[1], ST_E_NOT_MOUNTED);
	CHECK_EQ(le32(resp + 7), 1024);                   /* the medium's size */
	CHECK_EQ(t_open(0, 1, "X"), ST_E_NOT_MOUNTED);
	CHECK_EQ(simple(ST_MOUNT), ST_E_NOT_MOUNTED);
	/* a medium that does not answer */
	disk->fail = true;
	st_detect(&st, false);
	st_detect(&st, true);
	st_poll(&st);
	CHECK_EQ(status(), ST_S_MEDIA);
	CHECK_EQ(simple(ST_MOUNT), ST_E_IO);
	CHECK_EQ(ecmd((uint8_t[]){ST_BLK_READ, 0, 0, 0, 0}, 5), ST_E_IO);
	/* no medium at all */
	st_init(&st, &imgdisk_ops, disk, false);
	st_poll(&st);
	CHECK_EQ(status(), 0);
	CHECK_EQ(simple(ST_MOUNT), ST_E_NO_MEDIUM);
	CHECK_EQ(simple(ST_EJECT), ST_OK);
}

static void blocks(void)
{
	fresh(8192);
	/* the MBR FatFs wrote */
	CHECK_EQ(ecmd((uint8_t[]){ST_BLK_READ, 0, 0, 0, 0}, 5), ST_OK);
	CHECK_EQ(cmd((uint8_t[]){ST_BUF_GET, 0xFE, 0x01, 2}, 4), 2);
	CHECK(resp[0] == 0x55 && resp[1] == 0xAA, "boot signature");
	/* a whole sector through the buffer, 128 bytes at a time */
	for (int part = 0; part < 4; part++) {
		uint8_t f[4 + 128] = {ST_BUF_PUT, (uint8_t)(part * 128), (uint8_t)(part * 128 >> 8), 128};
		for (int i = 0; i < 128; i++)
			f[4 + i] = pattern((uint32_t)(part * 128 + i), 42);
		CHECK_EQ(cmd(f, sizeof f), 0);             /* no answer */
	}
	uint32_t last = disk->sectors - 1;
	uint8_t lba[4] = {(uint8_t)last, (uint8_t)(last >> 8), (uint8_t)(last >> 16), (uint8_t)(last >> 24)};
	CHECK_EQ(ecmd((uint8_t[]){ST_BLK_WRITE, lba[0], lba[1], lba[2], lba[3]}, 5), ST_OK);
	int bad = 0;
	for (int i = 0; i < 512; i++)
		bad += disk->data[(size_t)last * 512 + (size_t)i] != pattern((uint32_t)i, 42);
	CHECK(bad == 0, "sector written: %d bytes differ", bad);
	CHECK_EQ(ecmd((uint8_t[]){ST_BLK_READ, 0, 0, 0, 0}, 5), ST_OK);
	CHECK_EQ(ecmd((uint8_t[]){ST_BLK_READ, lba[0], lba[1], lba[2], lba[3]}, 5), ST_OK);
	CHECK_EQ(cmd((uint8_t[]){ST_BUF_GET, 0x80, 0x01, 128}, 4), 128);
	for (int i = 0; i < 128; i++)
		bad += resp[i] != pattern((uint32_t)(384 + i), 42);
	CHECK(bad == 0, "sector read back: %d bytes differ", bad);
	/* past the end */
	uint32_t end = disk->sectors;
	CHECK_EQ(ecmd((uint8_t[]){ST_BLK_READ, (uint8_t)end, (uint8_t)(end >> 8), 0, 0}, 5), ST_E_IO);
	CHECK_EQ(ecmd((uint8_t[]){ST_BLK_WRITE, 0xFF, 0xFF, 0xFF, 0xFF}, 5), ST_E_IO);
	/* a raw write the file system sees: rename a file in the directory sector */
	write_file("RAW.TXT", 10, 1, 128);
	/* the file system still works after raw access */
	CHECK_EQ(read_file("RAW.TXT", 1, 128), 10);
	/* a raw write, then ST_EJECT: EJECT syncs the medium (an SD card
	 * finishes programming the block) before it answers */
	CHECK_EQ(ecmd((uint8_t[]){ST_BLK_WRITE, lba[0], lba[1], lba[2], lba[3]}, 5), ST_OK);
	CHECK(disk->unsynced, "a raw BLK_WRITE is not synced by itself");
	CHECK_EQ(simple(ST_EJECT), ST_OK);
	CHECK(!disk->unsynced, "ST_EJECT synced the medium after a raw BLK_WRITE");
}

/* files a PC wrote (tools/fatcheck.py mkimg) */
static void from_pc(const char *path)
{
	imgdisk_free(disk);
	disk = imgdisk_open(path);
	CHECK(disk != 0, "open %s", path);
	if (!disk)
		return;
	st_init(&st, &imgdisk_ops, disk, true);
	st_poll(&st);
	CHECK_EQ(status(), ST_S_MEDIA | ST_S_MOUNTED);
	CHECK_EQ(t_open(0, 0, "PC.TXT"), ST_OK);
	char text[4096];
	int len = 0, n;
	while ((n = t_read(0, 128)) > 0 && n != ST_READ_ERR && len + n < (int)sizeof text) {
		memcpy(text + len, resp + 1, (size_t)n);
		len += n;
	}
	text[len] = 0;
	CHECK_EQ(t_close(0), ST_OK);
	int lines = 0;
	for (char *p = text; (p = strstr(p, "10 PRINT \"WRITTEN ON A PC\"\r\n")); p++)
		lines++;
	CHECK_EQ(lines, 40);
	CHECK_EQ(len, 40 * 28);
	CHECK_EQ(t_open(0, 0, "EMPTY.TXT"), ST_OK);
	CHECK_EQ(t_read(0, 128), 0);
	CHECK_EQ(t_close(0), ST_OK);
	/* and the card writes to the PC's volume (fatcheck.py checks it after) */
	write_file("CARD.DAT", 3000, 11, 128);
	CHECK_EQ(t_delete("DELME.TXT"), ST_OK);
}

/* the image and the files it should hold, for tools/fatcheck.py check */
static void for_pc(const char *out)
{
	char path[512];
	fresh(16384);                                    /* 8 MB */
	write_file("PROG.BAS", 700, 1, 128);
	write_file("DATA.BIN", 70000, 2, 128);
	write_file("EMPTY.TXT", 0, 0, 128);
	write_file("GONE.TXT", 100, 3, 128);
	CHECK_EQ(t_delete("GONE.TXT"), ST_OK);
	write_file("OLD.TXT", 50, 4, 128);
	CHECK_EQ(t_rename("OLD.TXT", "NEW.TXT"), ST_OK);
	/* appended in two sessions, the second across a remount */
	CHECK_EQ(t_open(0, 1, "LOG.TXT"), ST_OK);
	CHECK_EQ(t_write(0, (const uint8_t *)"first\r\n", 7), ST_OK);
	CHECK_EQ(t_close(0), ST_OK);
	CHECK_EQ(simple(ST_EJECT), ST_OK);
	CHECK_EQ(simple(ST_MOUNT), ST_OK);
	CHECK_EQ(t_open(0, 2, "LOG.TXT"), ST_OK);
	CHECK_EQ(t_write(0, (const uint8_t *)"second\r\n", 8), ST_OK);
	CHECK_EQ(t_close(0), ST_OK);

	snprintf(path, sizeof path, "%s/storage_card.img", out);
	FILE *img = fopen(path, "wb");
	CHECK(img != 0, "write %s", path);
	if (img) {
		fwrite(disk->data, 512, disk->sectors, img);
		fclose(img);
	}
	snprintf(path, sizeof path, "%s/storage_expect", out);
	mkdir(path, 0755);
	struct { const char *name; uint32_t size, seed; } want[] = {
		{"PROG.BAS", 700, 1}, {"DATA.BIN", 70000, 2}, {"EMPTY.TXT", 0, 0}, {"NEW.TXT", 50, 4},
	};
	for (unsigned i = 0; i < sizeof want / sizeof want[0]; i++) {
		snprintf(path, sizeof path, "%s/storage_expect/%s", out, want[i].name);
		FILE *f = fopen(path, "wb");
		for (uint32_t j = 0; f && j < want[i].size; j++)
			fputc(pattern(j, want[i].seed), f);
		if (f)
			fclose(f);
	}
	snprintf(path, sizeof path, "%s/storage_expect/LOG.TXT", out);
	FILE *f = fopen(path, "wb");
	if (f) {
		fputs("first\r\nsecond\r\n", f);
		fclose(f);
	}
}

int main(int argc, char **argv)
{
	const char *out = getenv("OUT") ? getenv("OUT") : ".";
	protocol();
	files();
	names();
	full();
	protect();
	removal();
	blocks();
	for_pc(out);
	if (argc > 1)
		from_pc(argv[1]);
	imgdisk_free(disk);
	return check_report("STO-001/002 storage card core");
}
