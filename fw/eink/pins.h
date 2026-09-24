/* Generated from hw/pins.yaml by hw/tools/genpins.py. Do not edit. */
#ifndef EINK_PINS_H
#define EINK_PINS_H

#define PIN_SLOT_SCK           2
#define PIN_SLOT_MOSI          3
#define PIN_SLOT_MISO          4
#define PIN_SLOT_NCS           5
/* slot: open drain */
#define PIN_SLOT_NIRQ          6
/* panel: SPI1 SCK */
#define PIN_EPD_CLK            10
/* panel: SPI1 TX */
#define PIN_EPD_DIN            11
/* panel: SPI1 CSn */
#define PIN_EPD_NCS            9
/* panel: data (1) or command (0) */
#define PIN_EPD_DC             12
#define PIN_EPD_NRST           13
/* panel: UC8179: low while busy */
#define PIN_EPD_BUSY           14
/* panel: the module's power switch (Waveshare HAT V2 PWR pin): high = on */
#define PIN_EPD_PWR            15
/* debug: lit while the panel refreshes */
#define PIN_LED_REFRESH        24
#define PIN_UART_TX            16

#endif
