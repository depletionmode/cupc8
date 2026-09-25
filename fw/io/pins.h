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
/* debug: keyboard connected */
#define PIN_LED_KBD            25
/* debug: keyboard activity: lit ~30 ms after each HID report */
#define PIN_LED_KEY            24
#define PIN_UART_TX            16

#endif
