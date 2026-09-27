/* Host (BSD sockets) backend for the Wi-Fi card core. */
#ifndef NETPOSIX_H
#define NETPOSIX_H

#include <stdio.h>

#include "wifi.h"

typedef struct netposix netposix_t;

extern const wifi_net_ops netposix_ops;
netposix_t *netposix_new(void);
/* close every host socket the card has (its power going off) */
void netposix_free(netposix_t *n);

#endif
