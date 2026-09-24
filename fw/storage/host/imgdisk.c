#include "imgdisk.h"

#include <fcntl.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>

#include "ff.h"

static int d_init(void *ctx)
{
	imgdisk_t *d = ctx;
	d->inits++;
	return d->fail ? -1 : 0;
}

static bool d_wp(void *ctx) { return ((imgdisk_t *)ctx)->wp; }
static uint32_t d_sectors(void *ctx) { return ((imgdisk_t *)ctx)->sectors; }

static int d_read(void *ctx, uint8_t *buf, uint32_t lba, uint32_t count)
{
	imgdisk_t *d = ctx;
	if (d->fail || lba + count > d->sectors || lba + count < lba)
		return -1;
	memcpy(buf, d->data + (size_t)lba * 512, (size_t)count * 512);
	d->reads += count;
	return 0;
}

static int d_write(void *ctx, const uint8_t *buf, uint32_t lba, uint32_t count)
{
	imgdisk_t *d = ctx;
	if (d->fail || d->wp || lba + count > d->sectors || lba + count < lba)
		return -1;
	for (uint32_t i = 0; i < count; i++) {
		if (d->before_write && !d->before_write(d, lba + i))
			return -1;
		memcpy(d->data + (size_t)(lba + i) * 512, buf + (size_t)i * 512, 512);
		if (d->fd >= 0 && pwrite(d->fd, buf + (size_t)i * 512, 512, (off_t)(lba + i) * 512) != 512)
			return -1;
		d->writes++;
	}
	return 0;
}

static int d_sync(void *ctx)
{
	return ((imgdisk_t *)ctx)->fail ? -1 : 0;
}

const st_disk_t imgdisk_ops = {
	.media = ST_MEDIA_SD,
	.init = d_init, .write_protected = d_wp, .sectors = d_sectors,
	.read = d_read, .write = d_write, .sync = d_sync,
};

imgdisk_t *imgdisk_new(uint32_t sectors)
{
	imgdisk_t *d = calloc(1, sizeof *d);
	if (!d)
		return 0;
	d->data = calloc(sectors, 512);
	if (!d->data) {
		free(d);
		return 0;
	}
	d->sectors = sectors;
	d->fd = -1;
	return d;
}

imgdisk_t *imgdisk_open(const char *path)
{
	int fd = open(path, O_RDWR);
	struct stat st;
	if (fd < 0 || fstat(fd, &st) || st.st_size < 512) {
		if (fd >= 0)
			close(fd);
		return 0;
	}
	imgdisk_t *d = imgdisk_new((uint32_t)(st.st_size / 512));
	if (!d || pread(fd, d->data, (size_t)d->sectors * 512, 0) != (ssize_t)d->sectors * 512) {
		imgdisk_free(d);
		close(fd);
		return 0;
	}
	d->fd = fd;
	return d;
}

void imgdisk_free(imgdisk_t *d)
{
	if (!d)
		return;
	if (d->fd >= 0)
		close(d->fd);
	free(d->data);
	free(d);
}

int imgdisk_format(imgdisk_t *d)
{
	static storage_t scratch;
	static BYTE work[FF_MAX_SS];
	st_init(&scratch, &imgdisk_ops, d, true);
	MKFS_PARM opt = { FM_FAT | FM_FAT32, 0, 0, 0, 0 };
	return f_mkfs("", &opt, work, sizeof work) == FR_OK ? 0 : -1;
}
