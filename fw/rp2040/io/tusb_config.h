/* TinyUSB for the IO card: host mode on the native port, HID keyboards
 * (doc/hardware/io-card.md). */
#ifndef TUSB_CONFIG_H
#define TUSB_CONFIG_H

#define CFG_TUSB_MCU              OPT_MCU_RP2040
#define CFG_TUSB_OS               OPT_OS_PICO
#define CFG_TUSB_RHPORT0_MODE     OPT_MODE_HOST
#define CFG_TUH_ENABLED           1
#define CFG_TUH_RPI_PIO_USB       0

#define CFG_TUH_ENUMERATION_BUFSIZE 256
#define CFG_TUH_HUB               1       /* hubs are best-effort in M1 */
#define CFG_TUH_DEVICE_MAX        4
#define CFG_TUH_HID               4
#define CFG_TUH_HID_EPIN_BUFSIZE  64
#define CFG_TUH_HID_EPOUT_BUFSIZE 64

#endif
