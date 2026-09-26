/*
 * Host network backend for the Wi-Fi card core: real BSD sockets.
 *
 * Used by the host tests and by the simulator, so CUPC/8 code talks to real
 * TCP. The ESP32-C3 build uses lwIP through the same interface. Wi-Fi itself
 * (join, scan, RSSI) is simulated here: the host is already "associated".
 */
#include "netposix.h"

#include <arpa/inet.h>
#include <errno.h>
#include <fcntl.h>
#include <netdb.h>
#include <netinet/in.h>
#include <netinet/tcp.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/socket.h>
#include <unistd.h>

#define MAXS 8

typedef struct {
	int fd;
	int type;
	bool listening;
	bool connecting;
	bool peer_closed;
	bool used;
	bool bound;                           /* ICMP: the echo id is set (see h_sendto) */
} hsock_t;

struct netposix {
	hsock_t s[MAXS];
	int link;
	int joins;
	char ssid[33];
	wifi_netcfg_t cfg;                    /* NET_CONFIG's settings */
};

static netposix_t g_net;

/* the card's NVS: outlives netposix_new(), so a test can power-cycle the card */
static struct {
	bool kept;
	wifi_netcfg_t cfg;
} g_nvs;

static void set_nonblock(int fd)
{
	fcntl(fd, F_SETFL, fcntl(fd, F_GETFL, 0) | O_NONBLOCK);
}

static int h_join(void *ctx, const char *ssid, const char *psk, bool save)
{
	netposix_t *n = ctx;
	(void)psk;
	(void)save;                           /* the host has nothing to store */
	if (!ssid[0])
		return -1;                        /* no SSID: fail, so tests can see it */
	snprintf(n->ssid, sizeof n->ssid, "%s", ssid);
	n->link = WIFI_LINK_JOINING;
	n->joins = 0;
	return 0;
}

static int h_link_state(void *ctx, uint8_t *rssi, uint8_t ip[4], uint8_t gw[4], uint8_t dns[4])
{
	netposix_t *n = ctx;
	*rssi = 60;
	const uint8_t local[4] = {127, 0, 0, 1};
	memcpy(ip, n->link == WIFI_LINK_UP ? local : (const uint8_t[4]){0, 0, 0, 0}, 4);
	memcpy(gw, ip, 4);
	memcpy(dns, ip, 4);
	/* the host's own address is what it is; a static one is only reported */
	if (n->link == WIFI_LINK_UP && n->cfg.mode == 1) {
		memcpy(ip, n->cfg.ip, 4);
		memcpy(gw, n->cfg.gw, 4);
		memset(dns, 0, 4);
	}
	if (n->link == WIFI_LINK_UP && (n->cfg.dns[0] | n->cfg.dns[1] | n->cfg.dns[2] | n->cfg.dns[3]))
		memcpy(dns, n->cfg.dns, 4);
	return n->link;
}

static void h_leave(void *ctx, bool forget)
{
	netposix_t *n = ctx;
	(void)forget;
	n->link = WIFI_LINK_IDLE;
}

static int h_scan_start(void *ctx)
{
	(void)ctx;
	return 0;
}

static int h_scan_result(void *ctx, int idx, uint8_t *rssi, uint8_t *auth, char *ssid, int cap)
{
	(void)ctx;
	static const char *fake[] = {"cupc8-test", "neighbour"};
	if (idx < 0 || idx >= (int)(sizeof fake / sizeof *fake))
		return -1;
	*rssi = (uint8_t)(70 - idx * 20);
	*auth = idx == 0 ? 3 : 0;
	snprintf(ssid, (size_t)cap, "%s", fake[idx]);
	return 0;
}

static int h_resolve(void *ctx, const char *host, uint8_t ip[4])
{
	(void)ctx;
	struct addrinfo hints = {.ai_family = AF_INET, .ai_socktype = SOCK_STREAM}, *res = 0;
	if (getaddrinfo(host, 0, &hints, &res) != 0 || !res)
		return -1;
	struct sockaddr_in *sin = (struct sockaddr_in *)res->ai_addr;
	memcpy(ip, &sin->sin_addr.s_addr, 4);
	freeaddrinfo(res);
	return 1;
}

static void h_net_config(void *ctx, const wifi_netcfg_t *cfg)
{
	((netposix_t *)ctx)->cfg = *cfg;
}

static int h_config_save(void *ctx, const wifi_netcfg_t *cfg)
{
	(void)ctx;
	g_nvs.cfg = *cfg;
	g_nvs.kept = true;
	return 0;
}

static bool h_config_load(void *ctx, wifi_netcfg_t *cfg)
{
	(void)ctx;
	if (g_nvs.kept)
		*cfg = g_nvs.cfg;
	return g_nvs.kept;
}

static int h_open(void *ctx, int type)
{
	netposix_t *n = ctx;
	if (type == WIFI_TLS || type > WIFI_ICMP)
		return -1;                        /* TLS is the ESP32's mbedTLS, not the host backend */
	for (int i = 0; i < MAXS; i++) {
		if (n->s[i].used)
			continue;
		/* ICMP: Linux's unprivileged ping socket (net.ipv4.ping_group_range),
		 * not a raw one, which needs root. It sends echo requests only. */
		int fd = type == WIFI_ICMP ? socket(AF_INET, SOCK_DGRAM, IPPROTO_ICMP)
		       : socket(AF_INET, type == WIFI_UDP ? SOCK_DGRAM : SOCK_STREAM, 0);
		if (fd < 0)
			return -1;
		set_nonblock(fd);
		n->s[i] = (hsock_t){.fd = fd, .type = type, .used = true};
		return i;
	}
	return -1;
}

static hsock_t *get(netposix_t *n, int h)
{
	return h >= 0 && h < MAXS && n->s[h].used ? &n->s[h] : 0;
}

static int h_connect(void *ctx, int h, const uint8_t ip[4], uint16_t port, const char *sni)
{
	netposix_t *n = ctx;
	hsock_t *s = get(n, h);
	(void)sni;
	if (!s)
		return -1;
	struct sockaddr_in sa = {.sin_family = AF_INET, .sin_port = htons(port)};
	memcpy(&sa.sin_addr.s_addr, ip, 4);
	int r = connect(s->fd, (struct sockaddr *)&sa, sizeof sa);
	if (r == 0 || errno == EINPROGRESS || s->type == WIFI_UDP) {
		s->connecting = s->type != WIFI_UDP && r != 0;
		return 0;
	}
	return -1;
}

static int h_listen(void *ctx, int h, uint16_t port)
{
	netposix_t *n = ctx;
	hsock_t *s = get(n, h);
	if (!s)
		return -1;
	int one = 1;
	setsockopt(s->fd, SOL_SOCKET, SO_REUSEADDR, &one, sizeof one);
	struct sockaddr_in sa = {.sin_family = AF_INET, .sin_port = htons(port),
	                         .sin_addr.s_addr = htonl(INADDR_ANY)};
	if (bind(s->fd, (struct sockaddr *)&sa, sizeof sa) < 0 || listen(s->fd, 1) < 0)
		return -1;
	s->listening = true;
	return 0;
}

static int h_send(void *ctx, int h, const uint8_t *data, int len)
{
	hsock_t *s = get(ctx, h);
	if (!s)
		return -1;
	int n = (int)send(s->fd, data, (size_t)len, MSG_NOSIGNAL);
	return n < 0 ? (errno == EAGAIN ? 0 : -1) : n;
}

static int h_recv(void *ctx, int h, uint8_t *data, int len)
{
	hsock_t *s = get(ctx, h);
	if (!s)
		return -1;
	int n = (int)recv(s->fd, data, (size_t)len, 0);
	if (n == 0) {
		s->peer_closed = true;
		return 0;
	}
	if (n < 0)
		return errno == EAGAIN ? 0 : -1;
	return n;
}

static int h_bind(void *ctx, int h, uint16_t port)
{
	hsock_t *s = get(ctx, h);
	if (!s || s->type != WIFI_UDP)
		return -1;
	struct sockaddr_in sa = {.sin_family = AF_INET, .sin_port = htons(port),
	                         .sin_addr.s_addr = htonl(INADDR_ANY)};
	return bind(s->fd, (struct sockaddr *)&sa, sizeof sa);
}

static int h_sendto(void *ctx, int h, const uint8_t ip[4], uint16_t port, const uint8_t *data, int len)
{
	hsock_t *s = get(ctx, h);
	if (!s || s->type == WIFI_TCP)
		return -1;
	struct sockaddr_in sa = {.sin_family = AF_INET, .sin_port = htons(port)};
	memcpy(&sa.sin_addr.s_addr, ip, 4);
	if (s->type == WIFI_ICMP) {
		if (len < 8)
			return -1;
		/* a ping socket puts its own port in the echo id: make that the id
		 * the host chose (the first one it sends; the socket keeps it) */
		sa.sin_port = 0;
		if (!s->bound) {
			struct sockaddr_in id = {.sin_family = AF_INET, .sin_port = htons((uint16_t)(data[4] << 8 | data[5]))};
			if (bind(s->fd, (struct sockaddr *)&id, sizeof id) < 0)
				return -1;
			s->bound = true;
		}
	}
	int n = (int)sendto(s->fd, data, (size_t)len, MSG_NOSIGNAL, (struct sockaddr *)&sa, sizeof sa);
	return n < 0 ? (errno == EAGAIN ? 0 : -1) : n;
}

static int h_recvfrom(void *ctx, int h, uint8_t *data, int len, uint8_t ip[4], uint16_t *port)
{
	hsock_t *s = get(ctx, h);
	if (!s || s->type == WIFI_TCP)
		return -1;
	struct sockaddr_in sa = {0};
	socklen_t sl = sizeof sa;
	int n = (int)recvfrom(s->fd, data, (size_t)len, 0, (struct sockaddr *)&sa, &sl);
	if (n < 0)
		return errno == EAGAIN ? 0 : -1;
	memcpy(ip, &sa.sin_addr.s_addr, 4);
	*port = s->type == WIFI_ICMP ? 0 : ntohs(sa.sin_port);
	return n;
}

static int h_status(void *ctx, int h, int *rx_avail, int *tx_free)
{
	netposix_t *n = ctx;
	hsock_t *s = get(n, h);
	*rx_avail = 0;
	*tx_free = 1024;
	if (!s)
		return WIFI_CLOSED;
	int pending = 0;
	if (ioctl(s->fd, FIONREAD, &pending) == 0)
		*rx_avail = pending;
	if (s->type == WIFI_ICMP) {
		/* a ping socket has no FIONREAD (nor MSG_TRUNC's real length): peek
		 * at the next message for its length instead */
		uint8_t msg[1500];
		int n = (int)recv(s->fd, msg, sizeof msg, MSG_PEEK | MSG_DONTWAIT);
		*rx_avail = n > 0 ? n : 0;
	}
	if (s->listening) {
		int fd = accept(s->fd, 0, 0);
		if (fd >= 0) {
			close(s->fd);
			set_nonblock(fd);
			s->fd = fd;
			s->listening = false;
			return WIFI_OPEN;
		}
		return WIFI_LISTENING;
	}
	if (s->connecting) {
		int err = 0;
		socklen_t l = sizeof err;
		getsockopt(s->fd, SOL_SOCKET, SO_ERROR, &err, &l);
		struct sockaddr_in peer;
		socklen_t pl = sizeof peer;
		if (err == 0 && getpeername(s->fd, (struct sockaddr *)&peer, &pl) == 0) {
			s->connecting = false;
			return WIFI_OPEN;
		}
		if (err != 0 && err != EINPROGRESS && err != EALREADY) {
			s->connecting = false;
			return WIFI_CLOSED;
		}
		return WIFI_CONNECTING;
	}
	if (*rx_avail == 0 && s->type == WIFI_TCP) {
		/* peek for EOF without consuming anything */
		uint8_t b;
		int n = (int)recv(s->fd, &b, 1, MSG_PEEK | MSG_DONTWAIT);
		if (n == 0)
			s->peer_closed = true;
	}
	if (s->peer_closed && *rx_avail == 0)
		return WIFI_PEER_CLOSED;
	return WIFI_OPEN;
}

static void h_close(void *ctx, int h)
{
	hsock_t *s = get(ctx, h);
	if (!s)
		return;
	close(s->fd);
	s->used = false;
}

static void h_poll(void *ctx)
{
	netposix_t *n = ctx;
	if (n->link == WIFI_LINK_JOINING && ++n->joins >= 2)
		n->link = WIFI_LINK_UP;            /* association takes a couple of polls */
}

const wifi_net_ops netposix_ops = {
	.join = h_join, .link_state = h_link_state, .leave = h_leave,
	.scan_start = h_scan_start, .scan_result = h_scan_result, .resolve = h_resolve,
	.net_config = h_net_config, .config_save = h_config_save, .config_load = h_config_load,
	.open = h_open, .connect = h_connect, .listen = h_listen, .send = h_send,
	.recv = h_recv, .bind = h_bind, .sendto = h_sendto, .recvfrom = h_recvfrom,
	.status = h_status, .close = h_close, .poll = h_poll,
};

/* the card's power going off: every host socket it had is closed, so its
 * ports are free again (for a new card, or another process) */
void netposix_free(netposix_t *n)
{
	for (int i = 0; i < MAXS; i++)
		if (n->s[i].used) {
			close(n->s[i].fd);
			n->s[i].used = false;
		}
}

netposix_t *netposix_new(void)
{
	netposix_free(&g_net);                  /* the last card's sockets, if it was not freed */
	memset(&g_net, 0, sizeof g_net);
	return &g_net;
}
