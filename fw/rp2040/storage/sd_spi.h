/* An SD card in SPI mode on the RP2040's SPI1 (hw/pins.yaml storage_mcu):
 * the storage core's medium (st_disk_t). Runs on core 1. */
#ifndef SD_SPI_H
#define SD_SPI_H

#include <stdint.h>

#include "storage.h"

extern const st_disk_t sd_spi_ops;

/* ms timestamp of the last card access (the ACT LED), written by core 1 */
extern volatile uint32_t sd_spi_last_access;

void sd_spi_setup(void);           /* pins and SPI1, once at boot */

#endif
