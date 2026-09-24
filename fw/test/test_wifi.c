/* WIFI-001/002 (host part): Wi-Fi card core (doc/hardware/wifi-card.md).
 * WIFI-001 drives the protocol against the host socket backend; WIFI-002
 * makes a real TCP connection to a listener in this process. */
#include <arpa/inet.h>
#include <netinet/in.h>
#include <string.h>
#include <sys/socket.h>
#include <unistd.h>

#include "check.h"
#include "netposix.h"
#include "wifi.h"

static wifi_t w;

/* the host backend, noting the SNI each connect is given */
static wifi_net_ops spy_ops;
static char last_sni[64];
static int last_save = -1;

static int spy_join(void *ctx, const char *ssid, const char *psk, bool save)
{
	last_save = save;
	return netposix_ops.join(ctx, ssid, psk, save);
}

static int spy_connect(void *ctx, int h, const uint8_t ip[4], uint16_t port, const char *sni)
{
	snprintf(last_sni, sizeof last_sni, "%s", sni ? sni : "(none)");
	return netposix_ops.connect(ctx, h, ip, port, sni);
}

static void send_frame(const uint8_t *f, int len)
{
	card_frame(&w.card, f, 0, len);
	wifi_poll(&w);
}
#define SEND(...) do { uint8_t b_[] = {__VA_ARGS__}; send_frame(b_, (int)sizeof b_); } while (0)

static int read_resp(uint8_t *out, int max)
{
	uint8_t mosi[2 + 64] = {CARD_OP_READ}, miso[2 + 64];
	card_frame(&w.card, mosi, miso, 2 + max);
	memcpy(out, miso + 2, (size_t)max);
	return miso[1];
}

static uint8_t status(void)
{
	uint8_t st;
	card_select(&w.card, true);
	st = card_next_miso(&w.card);
	card_select(&w.card, false);
	return st;
}

/* run the card until `code` shows up in the event queue, or give up */
static bool wait_event(uint8_t code, uint8_t *sock)
{
	uint8_t r[1 + 2 * WIFI_EVENTS];
	for (int i = 0; i < 2000; i++) {
		wifi_poll(&w);
		SEND(0x1F);                                    /* EVENTS */
		int n = read_resp(r, 1 + 2 * WIFI_EVENTS);
		if (n >= 1) {
			for (int e = 0; e < r[0]; e++)
				if (r[1 + e * 2] == code) {
					if (sock)
						*sock = r[2 + e * 2];
					return true;
				}
		}
		usleep(200);
	}
	return false;
}

static void test_link(void)
{
	uint8_t r[16];

	/* JOIN: takes a couple of polls, then the link comes up */
	uint8_t join[] = {0x04, 4, 'h', 'o', 'm', 'e', 3, 'p', 'w', 'd', 1};
	send_frame(join, sizeof join);
	CHECK(status() & 0x20, "BUSY while joining");
	CHECK(wait_event(WIFI_EV_JOINED, 0), "no JOINED event");
	/* doc: JOIN's save = 1 stores the credentials for auto-join at power-up */
	CHECK(last_save == 1, "JOIN save=1 reached the backend as %d", last_save);
	CHECK(status() & 0x40, "LINK not up after joining");

	SEND(0x01);                                        /* NET_STATUS */
	CHECK_EQ(read_resp(r, 14), 14);
	CHECK_EQ(r[0], WIFI_LINK_UP);
	CHECK(r[2] == 127 && r[5] == 1, "ip %d.%d.%d.%d", r[2], r[3], r[4], r[5]);

	/* SCAN */
	SEND(0x02);
	CHECK(wait_event(WIFI_EV_SCAN_DONE, 0), "no SCAN_DONE event");
	SEND(0x03, 0);
	int n = read_resp(r, 16);
	CHECK(n >= 3 && r[2] == 10 && memcmp(r + 3, "cupc8-test", 10) == 0, "scan result 0");
	SEND(0x03, 9);
	CHECK_EQ(read_resp(r, 4), 1);
	CHECK_EQ(r[0], 0xFF);                              /* past the end */

	/* RESOLVE */
	uint8_t res[] = {0x06, 9, 'l', 'o', 'c', 'a', 'l', 'h', 'o', 's', 't'};
	send_frame(res, sizeof res);
	CHECK(wait_event(WIFI_EV_RESOLVED, 0), "no RESOLVED event");
	SEND(0x07);
	CHECK_EQ(read_resp(r, 5), 5);
	CHECK(r[0] == 1 && r[1] == 127, "resolved %d.%d.%d.%d", r[1], r[2], r[3], r[4]);

	/* a join with no SSID fails */
	uint8_t bad[] = {0x04, 0, 0, 0};
	send_frame(bad, sizeof bad);
	CHECK(wait_event(WIFI_EV_JOIN_FAILED, 0), "no JOIN_FAILED event");
	send_frame(join, sizeof join);
	CHECK(wait_event(WIFI_EV_JOINED, 0), "rejoin failed");
}

static void test_sockets(void)
{
	uint8_t r[260], sock;

	/* a listener in this process stands in for a server */
	int srv = socket(AF_INET, SOCK_STREAM, 0);
	int one = 1;
	setsockopt(srv, SOL_SOCKET, SO_REUSEADDR, &one, sizeof one);
	struct sockaddr_in sa = {.sin_family = AF_INET, .sin_addr.s_addr = htonl(INADDR_LOOPBACK)};
	CHECK(bind(srv, (struct sockaddr *)&sa, sizeof sa) == 0, "bind");
	CHECK(listen(srv, 1) == 0, "listen");
	socklen_t sl = sizeof sa;
	getsockname(srv, (struct sockaddr *)&sa, &sl);
	uint16_t port = ntohs(sa.sin_port);

	/* OPEN + CONNECT_HOST "localhost" */
	SEND(0x10, WIFI_TCP);
	CHECK_EQ(read_resp(r, 1), 1);
	CHECK_EQ(r[0], 0);
	uint8_t conn[] = {0x12, 0, (uint8_t)port, (uint8_t)(port >> 8), 9,
	                  'l', 'o', 'c', 'a', 'l', 'h', 'o', 's', 't'};
	send_frame(conn, sizeof conn);
	int fd = -1;
	for (int i = 0; i < 2000 && fd < 0; i++) {
		wifi_poll(&w);
		fd = accept(srv, 0, 0);
		usleep(200);
	}
	CHECK(fd >= 0, "server did not see the connection");
	CHECK(wait_event(WIFI_EV_CONNECTED, &sock), "no CONNECTED event");
	CHECK_EQ(sock, 0);
	/* doc: CONNECT_HOST's host is TLS's SNI and certificate name */
	CHECK(!strcmp(last_sni, "localhost"), "CONNECT_HOST gave the backend SNI '%s', not the host name", last_sni);

	/* SEND from the card, read on the server */
	uint32_t tx0 = w.tx_bytes, rx0 = w.rx_bytes;
	uint8_t msg[] = {0x14, 0, 5, 'h', 'e', 'l', 'l', 'o'};
	send_frame(msg, sizeof msg);
	char buf[32] = {0};
	CHECK(read(fd, buf, sizeof buf) == 5 && memcmp(buf, "hello", 5) == 0, "server got '%s'", buf);
	/* the TX LED counts what went out */
	CHECK(w.tx_bytes - tx0 == 5, "tx_bytes counted %u, not 5", (unsigned)(w.tx_bytes - tx0));

	/* server replies; the card reports it and RECV returns it */
	CHECK(write(fd, "PONG", 4) == 4, "server write");
	bool ready = false;
	for (int i = 0; i < 2000 && !ready; i++) {
		wifi_poll(&w);
		ready = (status() & 0x01) != 0;
		usleep(200);
	}
	CHECK(ready, "RXREADY never set");
	SEND(0x16, 0);                                     /* SOCK_STATUS */
	CHECK_EQ(read_resp(r, 5), 5);
	CHECK(r[0] == WIFI_OPEN && r[1] == 4, "status state %d rx %d", r[0], r[1]);
	SEND(0x15, 0, 32);                                 /* RECV */
	int n = read_resp(r, 40);
	CHECK(n == 5 && r[0] == 4 && memcmp(r + 1, "PONG", 4) == 0, "recv %d bytes", n);
	CHECK(w.rx_bytes - rx0 == 4, "rx_bytes counted %u, not 4", (unsigned)(w.rx_bytes - rx0));

	/* the server closes: PEER_CLOSED */
	close(fd);
	CHECK(wait_event(WIFI_EV_PEER_CLOSED, &sock), "no PEER_CLOSED event");

	SEND(0x17, 0);                                     /* CLOSE */
	SEND(0x16, 0);
	CHECK_EQ(read_resp(r, 5), 0);                      /* a closed socket answers nothing */

	/* sockets are limited, and running out is reported */
	for (int i = 0; i < WIFI_SOCKETS; i++) {
		SEND(0x10, WIFI_TCP);
		read_resp(r, 1);
		CHECK_EQ(r[0], i);
	}
	SEND(0x10, WIFI_TCP);
	read_resp(r, 1);
	CHECK_EQ(r[0], 0xFF);
	for (int i = 0; i < WIFI_SOCKETS; i++)
		SEND(0x17, (uint8_t)i);

	/* TLS is not available on the host backend, and says so */
	SEND(0x10, WIFI_TLS);
	read_resp(r, 1);
	CHECK_EQ(r[0], 0xFF);

	close(srv);
}

static void test_errors(void)
{
	uint32_t e = w.card.errors;
	SEND(0x11, 9, 1, 2, 3, 4, 0, 0);                   /* CONNECT on a bad socket */
	SEND(0x14, 0);                                     /* SEND with no length */
	SEND(0x77);                                        /* unknown opcode */
	CHECK_EQ(w.card.errors, e + 3);

	uint8_t r[8];
	SEND(CARD_OP_IDENT);
	CHECK_EQ(read_resp(r, 4), 4);
	CHECK(r[0] == CARD_TYPE_WIFI && r[3] == CARD_IDENT_SIG, "IDENT");
}

int main(void)
{
	spy_ops = netposix_ops;
	spy_ops.connect = spy_connect;
	spy_ops.join = spy_join;
	wifi_init(&w, &spy_ops, netposix_new());
	test_link();
	test_sockets();
	test_errors();
	return check_report("WIFI-001/002 wifi core");
}
