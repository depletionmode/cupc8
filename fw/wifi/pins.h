/* Generated from hw/pins.yaml by hw/tools/genpins.py. Do not edit. */
#ifndef WIFI_PINS_H
#define WIFI_PINS_H

#define PIN_SLOT_SCK           6
#define PIN_SLOT_MOSI          7
/* slot: not GPIO2: that is a strapping pin, and the shared MISO line can be low while this card resets */
#define PIN_SLOT_MISO          5
#define PIN_SLOT_NCS           10
/* slot: open drain */
#define PIN_SLOT_NIRQ          3
#define PIN_U0RXD              20
#define PIN_U0TXD              21
#define PIN_BOOT_STRAP         9
#define PIN_LED_LINK           4
/* debug: socket data sent (milestone-1.md, Indicator LEDs) */
#define PIN_LED_TX             0
/* debug: socket data received */
#define PIN_LED_RX             1

#endif
