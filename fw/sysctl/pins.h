/* Generated from hw/pins.yaml by hw/tools/genpins.py. Do not edit. */
#ifndef SYSCTL_PINS_H
#define SYSCTL_PINS_H

#define PIN_BR_SCK             2
#define PIN_BR_MOSI            3
#define PIN_BR_MISO            4
#define PIN_BR_NCS             5
#define PIN_FL0_SCK            10
#define PIN_FL0_MOSI           11
#define PIN_FL0_MISO           12
#define PIN_FL0_NCS            13
/* chipset_flash: open drain */
#define PIN_CHIPSET_NCRESET    6
#define PIN_CHIPSET_CDONE      7
#define PIN_FL1_SCK            14
#define PIN_FL1_MOSI           15
#define PIN_FL1_MISO           8
#define PIN_FL1_NCS            9
/* cpucard_flash: open drain */
#define PIN_CPUCARD_NCRESET    16
#define PIN_CPUCARD_CDONE      17
#define PIN_PROG_CLK           18
#define PIN_PROG_IO            19
#define PIN_MUX_SEL0           20
#define PIN_MUX_SEL1           21
#define PIN_MUX_SEL2           22
#define PIN_I2C_SDA            24
#define PIN_I2C_SCL            25
/* misc: open drain onto the reset supervisor output */
#define PIN_SYS_NRST           23
/* misc: USB activity to the host, lit ~30 ms (milestone-1.md, Indicator LEDs); was the debug UART, which nothing used */
#define PIN_LED_USB_TX         0
/* misc: USB activity from the host */
#define PIN_LED_USB_RX         1
#define PIN_CC1_SENSE          26
#define PIN_CC2_SENSE          27
#define PIN_V1V2_SENSE         28
#define PIN_LED_STATUS         29

#endif
