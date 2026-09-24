/* A disk image as the storage card's medium, for host tests and the
 * simulator: in memory, and written through to its file if it has one. */
#ifndef IMGDISK_H
#define IMGDISK_H

#include <stdbool.h>
#include <stdint.h>

#include "storage.h"

typedef struct imgdisk {
	uint8_t *data;
	uint32_t sectors;
	int fd;                            /* -1: memory only */
	bool wp;                           /* write-protected */
	bool fail;                         /* every access fails (a dead medium) */
	uint32_t reads, writes, inits;     /* sectors read and written, init calls */
	/* test hook: called before each sector write; false fails it */
	bool (*before_write)(struct imgdisk *d, uint32_t lba);
	void *user;
} imgdisk_t;

extern const st_disk_t imgdisk_ops;

imgdisk_t *imgdisk_new(uint32_t sectors);          /* blank (zeroed) */
imgdisk_t *imgdisk_open(const char *path);         /* 0 if it cannot be read */
void imgdisk_free(imgdisk_t *d);
/* FAT (FatFs's f_mkfs: an MBR and one partition, FAT12/16/32 by size) over
 * the whole image; 0 on success. It binds FatFs to a scratch core: st_init()
 * the real one afterwards. */
int imgdisk_format(imgdisk_t *d);

#endif
