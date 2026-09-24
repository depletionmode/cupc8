/*
 * CUPC/8 Wi-Fi card core (doc/hardware/wifi-card.md).
 *
 * The whole network stack lives on the card; the CPU sees four sockets. The
 * core is hardware- and stack-independent: it talks to a backend (BSD sockets
 * on the host and in the simulator, lwIP on the ESP32-C3).
 */
#ifndef WIFI_H
#define WIFI_H

#include <stdbool.h>
#include <stdint.h>

#include "cardproto.h"

#define WIFI_SOCKETS   4
#define WIFI_EVENTS    16
#define WIFI_SCAN_MAX  16

/* socket types */
enum { WIFI_TCP = 0, WIFI_UDP = 1, WIFI_TLS = 2 };

/* socket states, as reported by SOCK_STATUS */
enum { WIFI_CLOSED = 0, WIFI_CONNECTING, WIFI_OPEN, WIFI_LISTENING, WIFI_PEER_CLOSED };

/* link states, as reported by NET_STATUS */
enum { WIFI_LINK_IDLE = 0, WIFI_LINK_JOINING, WIFI_LINK_UP, WIFI_LINK_FAILED };

/* events */
enum {
	WIFI_EV_SCAN_DONE = 0x01, WIFI_EV_JOINED = 0x02, WIFI_EV_JOIN_FAILED = 0x03,
	WIFI_EV_LINK_LOST = 0x04, WIFI_EV_RESOLVED = 0x05,
	WIFI_EV_CONNECTED = 0x10, WIFI_EV_CONN_FAILED = 0x11, WIFI_EV_ACCEPTED = 0x12,
	WIFI_EV_PEER_CLOSED = 0x13, WIFI_EV_ERROR = 0x14,
};

typedef struct wifi wifi_t;

typedef struct {
	/* link */
	/* save: keep the credentials (NVS) and join them again at power-up */
	int (*join)(void *ctx, const char *ssid, const char *psk, bool save);
	int (*link_state)(void *ctx, uint8_t *rssi, uint8_t ip[4], uint8_t gw[4], uint8_t dns[4]);
	void (*leave)(void *ctx, bool forget);
	int (*scan_start)(void *ctx);
	/* -1 past the end */
	int (*scan_result)(void *ctx, int idx, uint8_t *rssi, uint8_t *auth, char *ssid, int cap);
	/* 1 done, 0 pending, -1 failed */
	int (*resolve)(void *ctx, const char *host, uint8_t ip[4]);

	/* sockets: handle >= 0, or -1 */
	int (*open)(void *ctx, int type);
	int (*connect)(void *ctx, int h, const uint8_t ip[4], uint16_t port, const char *sni);
	int (*listen)(void *ctx, int h, uint16_t port);
	int (*send)(void *ctx, int h, const uint8_t *data, int len);
	int (*recv)(void *ctx, int h, uint8_t *data, int len);
	/* state, plus how much is buffered each way */
	int (*status)(void *ctx, int h, int *rx_avail, int *tx_free);
	void (*close)(void *ctx, int h);
	void (*poll)(void *ctx);
} wifi_net_ops;

typedef struct {
	int handle;
	uint8_t state;
	bool used;
} wifi_socket_t;

struct wifi {
	card_t card;
	const wifi_net_ops *net;
	void *ctx;

	wifi_socket_t sock[WIFI_SOCKETS];
	uint8_t events[WIFI_EVENTS][2];
	int nevents;
	bool busy;                        /* an asynchronous operation is running */
	char pending_host[64];            /* resolve in progress */
	int pending_sock;                 /* socket waiting for that resolve */
	uint16_t pending_port;
	bool resolve_ok;
	uint8_t resolve_ip[4];
	uint8_t link;                     /* last link state seen */
	uint32_t tx_bytes, rx_bytes;      /* socket data sent and received: the TX/RX LEDs */
};

void wifi_init(wifi_t *w, const wifi_net_ops *net, void *ctx);
void wifi_reset(wifi_t *w);
void wifi_poll(wifi_t *w);            /* run the backend and raise events */

#endif
