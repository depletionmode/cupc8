/* Generated from hw/pins.yaml by hw/tools/genpins.py. Do not edit. */
#ifndef IO_PINS_H
#define IO_PINS_H

/* usb_host: native USB host port: a dedicated RP2040 pin, not a GPIO */
/* usb_host: native USB host port: a dedicated RP2040 pin, not a GPIO */
#define PIN_VBUS_EN            7
#define PIN_VBUS_NFAULT        8
#define PIN_SLOT_SCK           2
#define PIN_SLOT_MOSI          3
#define PIN_SLOT_MISO          4
#define PIN_SLOT_NCS           5
/* slot: open drain */
#define PIN_SLOT_NIRQ          6
/* sd: SPI1 SCK */
#define PIN_SD_SCK             14
/* sd: SPI1 TX, to the card's CMD */
#define PIN_SD_MOSI            15
/* sd: SPI1 RX, from the card's DAT0 */
#define PIN_SD_MISO            12
/* sd: SPI1 CSn, to the card's DAT3/CD */
#define PIN_SD_NCS             13
/* sd: socket card-detect switch, pulled up: low = card in */
#define PIN_SD_NDETECT         17
/* sd: pulled up, unused in SPI mode: routed for a later 4-bit mode on PIO */
#define PIN_SD_DAT1            18
/* sd: pulled up, unused in SPI mode: routed for a later 4-bit mode on PIO */
#define PIN_SD_DAT2            19
/* debug: keyboard connected */
#define PIN_LED_KBD            25
/* debug: keyboard activity: lit ~30 ms after each HID report */
#define PIN_LED_KEY            24
/* debug: SD activity, in the top-edge LED row */
#define PIN_LED_SD             23
#define PIN_UART_TX            16

#endif
