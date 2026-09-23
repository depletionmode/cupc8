/* TinyUSB for the system card: a USB CDC device, the sysctl protocol
 * (doc/hardware/sysctl.md). */
#ifndef TUSB_CONFIG_H
#define TUSB_CONFIG_H

#define CFG_TUSB_MCU              OPT_MCU_RP2040
#define CFG_TUSB_OS               OPT_OS_PICO
#define CFG_TUSB_RHPORT0_MODE     OPT_MODE_DEVICE
#define CFG_TUD_ENABLED           1
#define CFG_TUD_ENDPOINT0_SIZE    64
#define CFG_TUD_CDC               1
#define CFG_TUD_CDC_RX_BUFSIZE    4096
#define CFG_TUD_CDC_TX_BUFSIZE    4096

#endif
