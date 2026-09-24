/* The storage core's binding to FatFs's disk I/O layer (diskio.c). */
#ifndef STDISKIO_H
#define STDISKIO_H

#include "storage.h"

/* FatFs has one volume: route it to this core's medium */
void st_diskio_bind(storage_t *s);
/* the medium went away: initialise it again before the next access */
void st_diskio_reset(void);

#endif
