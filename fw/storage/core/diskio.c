/* FatFs's disk I/O layer (fw/third_party/fatfs/diskio.h) over the storage
 * card's medium (st_disk_t). One volume: the storage core bound last. */
#include "storage.h"                   /* ff.h first: diskio.h uses its types */

#include "diskio.h"
#include "stdiskio.h"

static storage_t *bound;
static bool ready;                     /* the medium answered init since it was inserted */

void st_diskio_bind(storage_t *s)
{
	bound = s;
	ready = false;
}

void st_diskio_reset(void) { ready = false; }

DSTATUS disk_status(BYTE pdrv)
{
	if (pdrv || !bound || !bound->present)
		return STA_NOINIT | STA_NODISK;
	DSTATUS st = ready ? 0 : STA_NOINIT;
	if (bound->disk->write_protected(bound->ctx))
		st |= STA_PROTECT;
	return st;
}

DSTATUS disk_initialize(BYTE pdrv)
{
	if (pdrv || !bound || !bound->present)
		return STA_NOINIT | STA_NODISK;
	if (!ready)
		ready = bound->disk->init(bound->ctx) == 0;
	return disk_status(pdrv);
}

static DRESULT check(BYTE pdrv)
{
	if (pdrv || !bound)
		return RES_PARERR;
	if (!bound->present || !ready)
		return RES_NOTRDY;             /* pulled mid-operation: FR_NOT_READY */
	return RES_OK;
}

DRESULT disk_read(BYTE pdrv, BYTE *buff, LBA_t sector, UINT count)
{
	DRESULT r = check(pdrv);
	if (r != RES_OK)
		return r;
	return bound->disk->read(bound->ctx, buff, sector, count) ? RES_ERROR : RES_OK;
}

DRESULT disk_write(BYTE pdrv, const BYTE *buff, LBA_t sector, UINT count)
{
	DRESULT r = check(pdrv);
	if (r != RES_OK)
		return r;
	if (bound->disk->write_protected(bound->ctx))
		return RES_WRPRT;
	return bound->disk->write(bound->ctx, buff, sector, count) ? RES_ERROR : RES_OK;
}

DRESULT disk_ioctl(BYTE pdrv, BYTE cmd, void *buff)
{
	DRESULT r = check(pdrv);
	if (r != RES_OK)
		return r;
	switch (cmd) {
	case CTRL_SYNC:
		return bound->disk->sync(bound->ctx) ? RES_ERROR : RES_OK;
	case GET_SECTOR_COUNT:
		*(LBA_t *)buff = bound->disk->sectors(bound->ctx);
		return RES_OK;
	case GET_SECTOR_SIZE:
		*(WORD *)buff = 512;
		return RES_OK;
	case GET_BLOCK_SIZE:
		*(DWORD *)buff = 1;            /* erase block unknown */
		return RES_OK;
	default:
		return RES_PARERR;
	}
}
