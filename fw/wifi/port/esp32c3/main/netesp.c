#include "netesp.h"

#include <errno.h>
#include <fcntl.h>
#include <string.h>

#include "esp_crt_bundle.h"
#include "esp_event.h"
#include "esp_log.h"
#include "esp_netif.h"
#include "esp_tls.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "lwip/netdb.h"
#include "lwip/sockets.h"
#include "sdkconfig.h"

#if CONFIG_CUPC8_QEMU
#include "esp_eth.h"
#else
#include "esp_wifi.h"
#endif

#define MAXS 8

static const char *TAG = "net";
#define SCAN_MAX 16

typedef struct {
	bool used;
	int type;
	int fd;                     /* TCP/UDP */
	esp_tls_t *tls;             /* TLS */
	char host[64];              /* TLS: SNI and the certificate's name */
	uint8_t ip[4];
	uint16_t port;
	bool listening, connecting, peer_closed;
} esock_t;

static struct {
	esock_t s[MAXS];
	volatile int link;
	esp_netif_t *netif;
	/* name lookups run on their own task: getaddrinfo blocks */
	char resolve_host[64];
	volatile int resolve_state;         /* 0 idle, 1 running, 2 done, 3 failed */
	uint8_t resolve_ip[4];
	TaskHandle_t resolver;
#if !CONFIG_CUPC8_QEMU
	wifi_ap_record_t scan[SCAN_MAX];
	uint16_t nscan;
#endif
} net;

/* ------------------------------------------------------------------ link */

static void on_event(void *arg, esp_event_base_t base, int32_t id, void *data)
{
	if (base == IP_EVENT && (id == IP_EVENT_STA_GOT_IP || id == IP_EVENT_ETH_GOT_IP)) {
		net.link = WIFI_LINK_UP;
#if CONFIG_CUPC8_QEMU
	} else if (base == ETH_EVENT && id == ETHERNET_EVENT_DISCONNECTED) {
		net.link = WIFI_LINK_IDLE;
#else
	} else if (base == WIFI_EVENT && id == WIFI_EVENT_STA_DISCONNECTED) {
		net.link = net.link == WIFI_LINK_JOINING ? WIFI_LINK_FAILED : WIFI_LINK_IDLE;
	} else if (base == WIFI_EVENT && id == WIFI_EVENT_SCAN_DONE) {
		net.nscan = SCAN_MAX;
		if (esp_wifi_scan_get_ap_records(&net.nscan, net.scan) != ESP_OK)
			net.nscan = 0;
#endif
	}
}

#if CONFIG_CUPC8_QEMU
static esp_eth_handle_t eth;
static bool eth_started;
#endif

static int n_join(void *ctx, const char *ssid, const char *psk, bool save)
{
	if (!ssid[0])
		return -1;
	net.link = WIFI_LINK_JOINING;
#if CONFIG_CUPC8_QEMU
	/* QEMU: every "network" is the emulated Ethernet, with DHCP */
	if (!eth_started) {
		eth_started = true;
		if (esp_eth_start(eth) != ESP_OK)
			return -1;
	} else if (esp_netif_is_netif_up(net.netif)) {
		esp_netif_ip_info_t ip;
		if (esp_netif_get_ip_info(net.netif, &ip) == ESP_OK && ip.ip.addr)
			net.link = WIFI_LINK_UP;
	}
	return 0;
#else
	wifi_config_t cfg = { 0 };
	strlcpy((char *)cfg.sta.ssid, ssid, sizeof cfg.sta.ssid);
	strlcpy((char *)cfg.sta.password, psk, sizeof cfg.sta.password);
	esp_wifi_disconnect();
	/* JOIN save=1: the driver keeps the config in NVS, and netesp_init joins it at power-up */
	esp_wifi_set_storage(save ? WIFI_STORAGE_FLASH : WIFI_STORAGE_RAM);
	if (esp_wifi_set_config(WIFI_IF_STA, &cfg) != ESP_OK || esp_wifi_connect() != ESP_OK)
		return -1;
	return 0;
#endif
}

static int n_link_state(void *ctx, uint8_t *rssi, uint8_t ip[4], uint8_t gw[4], uint8_t dns[4])
{
	memset(ip, 0, 4);
	memset(gw, 0, 4);
	memset(dns, 0, 4);
	*rssi = 0;
	if (net.link != WIFI_LINK_UP)
		return net.link;
	esp_netif_ip_info_t info;
	if (esp_netif_get_ip_info(net.netif, &info) == ESP_OK) {
		memcpy(ip, &info.ip.addr, 4);
		memcpy(gw, &info.gw.addr, 4);
	}
	esp_netif_dns_info_t d;
	if (esp_netif_get_dns_info(net.netif, ESP_NETIF_DNS_MAIN, &d) == ESP_OK)
		memcpy(dns, &d.ip.u_addr.ip4.addr, 4);
#if CONFIG_CUPC8_QEMU
	*rssi = 60;                         /* no radio: a fixed, good signal */
#else
	wifi_ap_record_t ap;
	if (esp_wifi_sta_get_ap_info(&ap) == ESP_OK)
		*rssi = (uint8_t)(ap.rssi + 100);   /* dBm -100..0 as 0..100 */
#endif
	return WIFI_LINK_UP;
}

static void n_leave(void *ctx, bool forget)
{
	net.link = WIFI_LINK_IDLE;
#if CONFIG_CUPC8_QEMU
	(void)forget;
#else
	esp_wifi_disconnect();
	if (forget) {
		wifi_config_t none = { 0 };
		esp_wifi_set_storage(WIFI_STORAGE_FLASH);
		esp_wifi_set_config(WIFI_IF_STA, &none);
	}
#endif
}

static int n_scan_start(void *ctx)
{
#if CONFIG_CUPC8_QEMU
	return 0;
#else
	net.nscan = 0;
	return esp_wifi_scan_start(NULL, false) == ESP_OK ? 0 : -1;
#endif
}

static int n_scan_result(void *ctx, int idx, uint8_t *rssi, uint8_t *auth, char *ssid, int cap)
{
#if CONFIG_CUPC8_QEMU
	if (idx != 0)
		return -1;
	*rssi = 60;
	*auth = 0;
	strlcpy(ssid, "qemu-eth", (size_t)cap);
	return 0;
#else
	if (idx < 0 || idx >= net.nscan)
		return -1;
	*rssi = (uint8_t)(net.scan[idx].rssi + 100);
	*auth = (uint8_t)net.scan[idx].authmode;
	strlcpy(ssid, (const char *)net.scan[idx].ssid, (size_t)cap);
	return 0;
#endif
}

/* ------------------------------------------------------------------ DNS */

static void resolver_task(void *arg)
{
	for (;;) {
		ulTaskNotifyTake(pdTRUE, portMAX_DELAY);
		struct addrinfo hints = { .ai_family = AF_INET, .ai_socktype = SOCK_STREAM }, *res = NULL;
		if (getaddrinfo(net.resolve_host, NULL, &hints, &res) == 0 && res) {
			memcpy(net.resolve_ip, &((struct sockaddr_in *)res->ai_addr)->sin_addr.s_addr, 4);
			freeaddrinfo(res);
			net.resolve_state = 2;
		} else {
			net.resolve_state = 3;
		}
	}
}

/* 1 done, 0 pending, -1 failed */
static int n_resolve(void *ctx, const char *host, uint8_t ip[4])
{
	if (net.resolve_state == 0 || strcmp(host, net.resolve_host)) {
		if (net.resolve_state == 1)
			return 0;                   /* another lookup is still running */
		strlcpy(net.resolve_host, host, sizeof net.resolve_host);
		net.resolve_state = 1;
		xTaskNotifyGive(net.resolver);
		return 0;
	}
	if (net.resolve_state == 1)
		return 0;
	int ok = net.resolve_state == 2;
	memcpy(ip, net.resolve_ip, 4);
	net.resolve_state = 0;
	return ok ? 1 : -1;
}

/* ------------------------------------------------------------------ sockets */

static esock_t *get(int h)
{
	return h >= 0 && h < MAXS && net.s[h].used ? &net.s[h] : NULL;
}

static int n_open(void *ctx, int type)
{
	for (int i = 0; i < MAXS; i++) {
		if (net.s[i].used)
			continue;
		esock_t *s = &net.s[i];
		memset(s, 0, sizeof *s);
		s->type = type;
		s->fd = -1;
		if (type != WIFI_TLS) {
			s->fd = socket(AF_INET, type == WIFI_UDP ? SOCK_DGRAM : SOCK_STREAM, 0);
			if (s->fd < 0)
				return -1;
			fcntl(s->fd, F_SETFL, fcntl(s->fd, F_GETFL, 0) | O_NONBLOCK);
		}
		s->used = true;
		return i;
	}
	return -1;
}

static int tls_step(esock_t *s)
{
	esp_tls_cfg_t cfg = {
		.crt_bundle_attach = esp_crt_bundle_attach,
		.non_block = true,
		.timeout_ms = 10000,
	};
	return esp_tls_conn_new_async(s->host, (int)strlen(s->host), s->port, &cfg, s->tls);
}

static int n_connect(void *ctx, int h, const uint8_t ip[4], uint16_t port, const char *sni)
{
	esock_t *s = get(h);
	if (!s)
		return -1;
	memcpy(s->ip, ip, 4);
	s->port = port;
	if (s->type == WIFI_TLS) {
		/* the certificate is checked against this name; without one (CONNECT
		 * by address) only a certificate for the address itself passes */
		if (sni)
			strlcpy(s->host, sni, sizeof s->host);
		else
			snprintf(s->host, sizeof s->host, "%u.%u.%u.%u", ip[0], ip[1], ip[2], ip[3]);
		s->tls = esp_tls_init();
		if (!s->tls || tls_step(s) < 0)
			return -1;
		s->connecting = true;
		return 0;
	}
	struct sockaddr_in sa = { .sin_family = AF_INET, .sin_port = htons(port) };
	memcpy(&sa.sin_addr.s_addr, ip, 4);
	int r = connect(s->fd, (struct sockaddr *)&sa, sizeof sa);
	if (r == 0 || errno == EINPROGRESS || s->type == WIFI_UDP) {
		s->connecting = s->type != WIFI_UDP && r != 0;
		return 0;
	}
	return -1;
}

static int n_listen(void *ctx, int h, uint16_t port)
{
	esock_t *s = get(h);
	if (!s || s->type == WIFI_TLS)
		return -1;
	int one = 1;
	setsockopt(s->fd, SOL_SOCKET, SO_REUSEADDR, &one, sizeof one);
	struct sockaddr_in sa = { .sin_family = AF_INET, .sin_port = htons(port), .sin_addr.s_addr = htonl(INADDR_ANY) };
	if (bind(s->fd, (struct sockaddr *)&sa, sizeof sa) < 0 || listen(s->fd, 1) < 0)
		return -1;
	s->listening = true;
	return 0;
}

static int n_send(void *ctx, int h, const uint8_t *data, int len)
{
	esock_t *s = get(h);
	if (!s)
		return -1;
	if (s->type == WIFI_TLS) {
		int n = (int)esp_tls_conn_write(s->tls, data, (size_t)len);
		if (n == ESP_TLS_ERR_SSL_WANT_READ || n == ESP_TLS_ERR_SSL_WANT_WRITE)
			return 0;
		if (n < 0)
			ESP_LOGW(TAG, "TLS write: -0x%x", -n);
		return n < 0 ? -1 : n;
	}
	int n = (int)send(s->fd, data, (size_t)len, 0);
	return n < 0 ? (errno == EAGAIN ? 0 : -1) : n;
}

static int n_recv(void *ctx, int h, uint8_t *data, int len)
{
	esock_t *s = get(h);
	if (!s)
		return -1;
	if (s->type == WIFI_TLS) {
		int n = (int)esp_tls_conn_read(s->tls, data, (size_t)len);
		if (n == ESP_TLS_ERR_SSL_WANT_READ || n == ESP_TLS_ERR_SSL_WANT_WRITE)
			return 0;
		if (n == 0)
			s->peer_closed = true;
		return n < 0 ? -1 : n;
	}
	int n = (int)recv(s->fd, data, (size_t)len, 0);
	if (n == 0) {
		s->peer_closed = true;
		return 0;
	}
	return n < 0 ? (errno == EAGAIN ? 0 : -1) : n;
}

static int n_status(void *ctx, int h, int *rx_avail, int *tx_free)
{
	esock_t *s = get(h);
	*rx_avail = 0;
	*tx_free = 1024;
	if (!s)
		return WIFI_CLOSED;
	if (s->type == WIFI_TLS) {
		if (!s->tls)
			return WIFI_CLOSED;         /* not connected yet (CONNECT_HOST still resolving) */
		if (s->connecting) {
			int r = tls_step(s);
			if (r < 0) {
				int code = 0, flags = 0;
				esp_tls_error_handle_t e = NULL;
				if (esp_tls_get_error_handle(s->tls, &e) == ESP_OK)
					esp_tls_get_and_clear_last_error(e, &code, &flags);
				ESP_LOGW(TAG, "TLS to %s failed: -0x%x, verify flags 0x%x", s->host, -code, flags);
				s->connecting = false;
				return WIFI_CLOSED;     /* includes a failed certificate check */
			}
			if (r == 0)
				return WIFI_CONNECTING;
			s->connecting = false;
		}
		int fd = -1, pending = 0;
		ssize_t avail = esp_tls_get_bytes_avail(s->tls);
		*rx_avail = avail > 0 ? (int)avail : 0;
		/* encrypted bytes waiting: say so, and let RECV decrypt them */
		if (!*rx_avail && esp_tls_get_conn_sockfd(s->tls, &fd) == ESP_OK &&
		    ioctl(fd, FIONREAD, &pending) == 0 && pending > 0)
			*rx_avail = 1;
		return s->peer_closed && !*rx_avail ? WIFI_PEER_CLOSED : WIFI_OPEN;
	}
	int pending = 0;
	if (ioctl(s->fd, FIONREAD, &pending) == 0)
		*rx_avail = pending;
	if (s->listening) {
		int fd = accept(s->fd, NULL, NULL);
		if (fd < 0)
			return WIFI_LISTENING;
		close(s->fd);
		fcntl(fd, F_SETFL, fcntl(fd, F_GETFL, 0) | O_NONBLOCK);
		s->fd = fd;
		s->listening = false;
		return WIFI_OPEN;
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
	if (!*rx_avail && s->type != WIFI_UDP) {
		uint8_t b;
		if (recv(s->fd, &b, 1, MSG_PEEK | MSG_DONTWAIT) == 0)
			s->peer_closed = true;
	}
	return s->peer_closed && !*rx_avail ? WIFI_PEER_CLOSED : WIFI_OPEN;
}

static void n_close(void *ctx, int h)
{
	esock_t *s = get(h);
	if (!s)
		return;
	if (s->tls)
		esp_tls_conn_destroy(s->tls);
	else if (s->fd >= 0)
		close(s->fd);
	s->used = false;
}

const wifi_net_ops netesp_ops = {
	.join = n_join, .link_state = n_link_state, .leave = n_leave,
	.scan_start = n_scan_start, .scan_result = n_scan_result, .resolve = n_resolve,
	.open = n_open, .connect = n_connect, .listen = n_listen, .send = n_send,
	.recv = n_recv, .status = n_status, .close = n_close,
};

void *netesp_init(void)
{
	ESP_ERROR_CHECK(esp_netif_init());
	ESP_ERROR_CHECK(esp_event_loop_create_default());
	ESP_ERROR_CHECK(esp_event_handler_register(IP_EVENT, ESP_EVENT_ANY_ID, on_event, NULL));
#if CONFIG_CUPC8_QEMU
	esp_netif_config_t cfg = ESP_NETIF_DEFAULT_ETH();
	net.netif = esp_netif_new(&cfg);
	eth_mac_config_t mac_cfg = ETH_MAC_DEFAULT_CONFIG();
	eth_phy_config_t phy_cfg = ETH_PHY_DEFAULT_CONFIG();
	phy_cfg.autonego_timeout_ms = 100;
	esp_eth_mac_t *mac = esp_eth_mac_new_openeth(&mac_cfg);
	esp_eth_phy_t *phy = esp_eth_phy_new_dp83848(&phy_cfg);
	esp_eth_config_t eth_cfg = ETH_DEFAULT_CONFIG(mac, phy);
	ESP_ERROR_CHECK(esp_eth_driver_install(&eth_cfg, &eth));
	ESP_ERROR_CHECK(esp_netif_attach(net.netif, esp_eth_new_netif_glue(eth)));
	ESP_ERROR_CHECK(esp_event_handler_register(ETH_EVENT, ESP_EVENT_ANY_ID, on_event, NULL));
#else
	net.netif = esp_netif_create_default_wifi_sta();
	wifi_init_config_t cfg = WIFI_INIT_CONFIG_DEFAULT();
	ESP_ERROR_CHECK(esp_wifi_init(&cfg));
	ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_STA));
	ESP_ERROR_CHECK(esp_event_handler_register(WIFI_EVENT, ESP_EVENT_ANY_ID, on_event, NULL));
	ESP_ERROR_CHECK(esp_wifi_start());
	/* credentials saved by an earlier JOIN save=1: join them now */
	wifi_config_t saved;
	if (esp_wifi_get_config(WIFI_IF_STA, &saved) == ESP_OK && saved.sta.ssid[0]) {
		net.link = WIFI_LINK_JOINING;
		esp_wifi_connect();
	}
#endif
	xTaskCreate(resolver_task, "resolve", 4096, NULL, 5, &net.resolver);
	return &net;
}
