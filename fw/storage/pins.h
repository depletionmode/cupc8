/* Generated from hw/pins.yaml by hw/tools/genpins.py. Do not edit. */
#ifndef STORAGE_PINS_H
#define STORAGE_PINS_H

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
/* debug: medium activity, lit ~30 ms after each access */
#define PIN_LED_ACT            24
/* debug: a card is inserted and mounted */
#define PIN_LED_CARD           25
#define PIN_UART_TX            16

#endif
