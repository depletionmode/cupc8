/* The Wi-Fi card core's network backend on the ESP32-C3: lwIP sockets,
 * esp-tls, and the radio (or QEMU's Ethernet in the emulated build). */
#ifndef NETESP_H
#define NETESP_H

#include "wifi.h"

extern const wifi_net_ops netesp_ops;
void *netesp_init(void);

#endif
