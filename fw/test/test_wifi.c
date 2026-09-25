/* WIFI-001/002/005 (host part): Wi-Fi card core (doc/hardware/wifi-card.md).
 * WIFI-001 drives the protocol against the host socket backend; WIFI-002
 * makes a real TCP connection to a listener in this process; WIFI-005:
 * NET_CONFIG, UDP_BIND/RECVFROM/SENDTO with host peers, ICMP echo through
 * Linux's unprivileged ping socket. */
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
	uint8_t mosi[2 + CARD_RESP_MAX] = {CARD_OP_READ}, miso[2 + CARD_RESP_MAX];
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

/* the card loses power and comes back: only NVS survives. Rejoins. */
static void power_cycle(void)
{
	wifi_reset(&w);                                    /* closes the backend's sockets */
	wifi_init(&w, &spy_ops, netposix_new());
	uint8_t join[] = {0x04, 4, 'h', 'o', 'm', 'e', 0, 0};
	send_frame(join, sizeof join);
	CHECK(wait_event(WIFI_EV_JOINED, 0), "no JOINED after the power cycle");
}

static void net_config(uint8_t mode, const uint8_t ip[4], const uint8_t mask[4], const uint8_t gw[4],
                       const uint8_t dns[4], uint16_t port, uint8_t save)
{
	uint8_t f[21] = {0x08, mode};
	memcpy(f + 2, ip, 4);
	memcpy(f + 6, mask, 4);
	memcpy(f + 10, gw, 4);
	memcpy(f + 14, dns, 4);
	f[18] = (uint8_t)port;
	f[19] = (uint8_t)(port >> 8);
	f[20] = save;
	send_frame(f, sizeof f);
}

/* NET_CONFIG_GET matches these settings, and says whether they are saved */
static void expect_config(uint8_t mode, const uint8_t ip[4], const uint8_t mask[4], const uint8_t gw[4],
                          const uint8_t dns[4], uint16_t port, uint8_t saved, const char *what)
{
	uint8_t r[24];
	SEND(0x09);
	int n = read_resp(r, 24);
	CHECK(n == 20, "%s: NET_CONFIG_GET answered %d bytes, not 20", what, n);
	CHECK(r[0] == mode && !memcmp(r + 1, ip, 4) && !memcmp(r + 5, mask, 4) && !memcmp(r + 9, gw, 4) &&
	      !memcmp(r + 13, dns, 4) && (r[17] | r[18] << 8) == port && r[19] == saved,
	      "%s: mode %d ip %d.%d.%d.%d mask %d.%d.%d.%d gw %d.%d.%d.%d dns %d.%d.%d.%d:%d saved %d", what,
	      r[0], r[1], r[2], r[3], r[4], r[5], r[6], r[7], r[8], r[9], r[10], r[11], r[12],
	      r[13], r[14], r[15], r[16], r[17] | r[18] << 8, r[19]);
}

static void test_net_config(void)
{
	static const uint8_t zero[4] = {0}, ip[4] = {192, 168, 7, 50}, mask[4] = {255, 255, 255, 0},
	                     gw[4] = {192, 168, 7, 1}, dns[4] = {9, 9, 9, 9}, dns2[4] = {10, 0, 2, 2};
	uint8_t r[16];

	expect_config(0, zero, zero, zero, zero, 53, 0, "power-up default: DHCP, DNS from DHCP on port 53");

	/* static, not saved: in use now (NET_STATUS), gone after a power cycle */
	net_config(1, ip, mask, gw, dns, 5353, 0);
	expect_config(1, ip, mask, gw, dns, 5353, 0, "static, not saved");
	SEND(0x01);
	CHECK_EQ(read_resp(r, 14), 14);
	CHECK(!memcmp(r + 2, ip, 4) && !memcmp(r + 6, gw, 4) && !memcmp(r + 10, dns, 4),
	      "NET_STATUS with the static settings: ip %d.%d.%d.%d gw %d.%d.%d.%d dns %d.%d.%d.%d",
	      r[2], r[3], r[4], r[5], r[6], r[7], r[8], r[9], r[10], r[11], r[12], r[13]);
	power_cycle();
	expect_config(0, zero, zero, zero, zero, 53, 0, "unsaved settings are gone after a power cycle");

	/* saved: kept by a soft reset and by a power cycle, and applied then */
	net_config(1, ip, mask, gw, dns, 5353, 1);
	expect_config(1, ip, mask, gw, dns, 5353, 1, "static, saved");
	SEND(CARD_OP_SOFT_RESET);
	expect_config(1, ip, mask, gw, dns, 5353, 1, "a soft reset keeps the settings");
	power_cycle();
	expect_config(1, ip, mask, gw, dns, 5353, 1, "saved settings come back at power-up");
	SEND(0x01);
	CHECK_EQ(read_resp(r, 14), 14);
	CHECK(!memcmp(r + 2, ip, 4), "the saved static address is in use after power-up: %d.%d.%d.%d",
	      r[2], r[3], r[4], r[5]);

	/* changed without saving: saved 0 now; the saved ones come back */
	net_config(0, zero, zero, zero, dns2, 53, 0);
	expect_config(0, zero, zero, zero, dns2, 53, 0, "DHCP with a DNS server, not saved");
	SEND(0x01);
	CHECK_EQ(read_resp(r, 14), 14);
	CHECK(r[2] == 127 && !memcmp(r + 10, dns2, 4), "DHCP's address with the configured DNS");
	power_cycle();
	expect_config(1, ip, mask, gw, dns, 5353, 1, "power-up brings back what was saved, not the last settings");

	/* malformed: counted, not answered, settings unchanged */
	uint32_t e = w.card.errors;
	uint8_t shortf[20] = {0x08, 0};
	send_frame(shortf, sizeof shortf);                 /* no save byte */
	CHECK_EQ(read_resp(r, 4), 0);
	net_config(2, ip, mask, gw, dns, 53, 0);           /* mode 2 */
	CHECK_EQ(read_resp(r, 4), 0);
	net_config(1, zero, mask, gw, dns, 53, 0);         /* static with no address */
	CHECK_EQ(read_resp(r, 4), 0);
	CHECK_EQ(w.card.errors, e + 3);
	expect_config(1, ip, mask, gw, dns, 5353, 1, "malformed NET_CONFIG changed nothing");

	/* back to the defaults, saved, for the tests after this */
	net_config(0, zero, zero, zero, zero, 53, 1);
	expect_config(0, zero, zero, zero, zero, 53, 1, "DHCP saved");
}

static int udp_socket(uint16_t *port)
{
	int fd = socket(AF_INET, SOCK_DGRAM, 0);
	struct sockaddr_in sa = {.sin_family = AF_INET, .sin_addr.s_addr = htonl(INADDR_LOOPBACK)};
	bind(fd, (struct sockaddr *)&sa, sizeof sa);
	socklen_t sl = sizeof sa;
	getsockname(fd, (struct sockaddr *)&sa, &sl);
	*port = ntohs(sa.sin_port);
	struct timeval tv = {.tv_sec = 5};
	setsockopt(fd, SOL_SOCKET, SO_RCVTIMEO, &tv, sizeof tv);
	return fd;
}

static void to_card(int fd, uint16_t port, const void *data, size_t len)
{
	struct sockaddr_in sa = {.sin_family = AF_INET, .sin_port = htons(port),
	                         .sin_addr.s_addr = htonl(INADDR_LOOPBACK)};
	CHECK(sendto(fd, data, len, 0, (struct sockaddr *)&sa, sizeof sa) == (ssize_t)len, "host sendto");
}

/* poll the card until socket `sock`'s RXREADY bit is set */
static bool rx_ready(uint8_t sock)
{
	for (int i = 0; i < 2000; i++) {
		wifi_poll(&w);
		if (status() & (1 << sock))
			return true;
		usleep(200);
	}
	return false;
}

/* RECVFROM: n, with the sender in ip/port and the data in data */
static int recvfrom_card(uint8_t sock, uint8_t max, uint8_t ip[4], uint16_t *port, uint8_t *data)
{
	uint8_t r[CARD_RESP_MAX];
	SEND(0x1A, sock, max);
	int len = read_resp(r, CARD_RESP_MAX);
	CHECK(len >= 7 && len == 7 + r[6], "RECVFROM's RESP_LEN %d is not 7 + n (%d)", len, len >= 7 ? r[6] : -1);
	if (len < 7)
		return -1;
	memcpy(ip, r, 4);
	*port = (uint16_t)(r[4] | r[5] << 8);
	memcpy(data, r + 7, r[6]);
	return r[6];
}

static void udp_sendto(uint8_t sock, uint16_t port, const char *text)
{
	uint8_t f[64] = {0x18, sock, 127, 0, 0, 1, (uint8_t)port, (uint8_t)(port >> 8), (uint8_t)strlen(text)};
	memcpy(f + 9, text, strlen(text));
	send_frame(f, 9 + (int)strlen(text));
}

static void test_udp(void)
{
	uint8_t r[CARD_RESP_MAX], ip[4], sock, evsock;
	uint16_t from, pa, pb, card_port;
	char buf[300];

	/* a free port for the card's server */
	close(udp_socket(&card_port));
	SEND(0x10, WIFI_UDP);
	CHECK_EQ(read_resp(r, 1), 1);
	sock = r[0];
	CHECK(sock < WIFI_SOCKETS, "OPEN UDP gave %d", sock);
	SEND(0x19, sock, (uint8_t)card_port, (uint8_t)(card_port >> 8));   /* UDP_BIND */
	CHECK(!wait_event(WIFI_EV_ERROR, 0), "UDP_BIND to a free port raised ERROR");

	CHECK_EQ(recvfrom_card(sock, 64, ip, &from, r), 0);     /* nothing waiting yet */

	/* a client sends; RXREADY; RECVFROM gives the datagram and who sent it */
	int a = udp_socket(&pa), b = udp_socket(&pb);
	to_card(a, card_port, "ping-a", 6);
	CHECK(rx_ready(sock), "RXREADY for a datagram on the bound socket");
	uint32_t rx0 = w.rx_bytes;
	int n = recvfrom_card(sock, 64, ip, &from, r);
	CHECK(n == 6 && !memcmp(r, "ping-a", 6), "RECVFROM got %d bytes", n);
	CHECK(ip[0] == 127 && ip[3] == 1 && from == pa, "sender %d.%d.%d.%d:%d, not 127.0.0.1:%d",
	      ip[0], ip[1], ip[2], ip[3], from, pa);
	CHECK(w.rx_bytes - rx0 == 6, "rx_bytes counted %u, not 6", (unsigned)(w.rx_bytes - rx0));

	/* the reply goes back to the sender, from the bound port */
	udp_sendto(sock, pa, "pong-a");
	struct sockaddr_in src;
	socklen_t sl = sizeof src;
	memset(buf, 0, sizeof buf);
	ssize_t got = recvfrom(a, buf, sizeof buf, 0, (struct sockaddr *)&src, &sl);
	CHECK(got == 6 && !memcmp(buf, "pong-a", 6), "client A got '%s'", buf);
	CHECK(got > 0 && ntohs(src.sin_port) == card_port, "the reply came from port %d, not the bound %d",
	      ntohs(src.sin_port), card_port);

	/* a second client is still heard after that reply (a server answers everyone) */
	to_card(b, card_port, "ping-b", 6);
	CHECK(rx_ready(sock), "RXREADY for a second client after replying to the first");
	n = recvfrom_card(sock, 64, ip, &from, r);
	CHECK(n == 6 && !memcmp(r, "ping-b", 6) && from == pb,
	      "a bound socket that replied to A heard B: %d bytes from %d", n, from);
	udp_sendto(sock, pb, "pong-b");
	memset(buf, 0, sizeof buf);
	got = recv(b, buf, sizeof buf, 0);
	CHECK(got == 6 && !memcmp(buf, "pong-b", 6), "client B got '%s'", buf);

	/* longer than max: cut short, the rest dropped */
	to_card(a, card_port, "0123456789", 10);
	CHECK(rx_ready(sock), "RXREADY for the long datagram");
	n = recvfrom_card(sock, 4, ip, &from, r);
	CHECK(n == 4 && !memcmp(r, "0123", 4), "max 4: %d bytes", n);
	CHECK_EQ(recvfrom_card(sock, 64, ip, &from, r), 0);

	/* max is capped so RESP_LEN fits: 7 + 248 = 255 */
	memset(buf, 'x', 250);
	to_card(a, card_port, buf, 250);
	CHECK(rx_ready(sock), "RXREADY for the 250-byte datagram");
	n = recvfrom_card(sock, 255, ip, &from, r);
	CHECK_EQ(n, CARD_RESP_MAX - 7);

	/* UDP_BIND to a port already taken, or on a TCP socket: ERROR(sock) */
	SEND(0x10, WIFI_UDP);
	read_resp(r, 1);
	uint8_t s2 = r[0];
	SEND(0x19, s2, (uint8_t)pa, (uint8_t)(pa >> 8));
	CHECK(wait_event(WIFI_EV_ERROR, &evsock) && evsock == s2, "UDP_BIND to a taken port: ERROR");
	SEND(0x10, WIFI_TCP);
	read_resp(r, 1);
	uint8_t t = r[0];
	SEND(0x19, t, 0x34, 0x12);
	CHECK(wait_event(WIFI_EV_ERROR, &evsock) && evsock == t, "UDP_BIND on a TCP socket: ERROR");
	CHECK_EQ(recvfrom_card(t, 64, ip, &from, r), 0);         /* RECVFROM on TCP: nothing */

	SEND(0x17, sock);
	SEND(0x17, s2);
	SEND(0x17, t);
	close(a);
	close(b);
}

static uint16_t inet_checksum(const uint8_t *p, int len)
{
	uint32_t sum = 0;
	for (int i = 0; i + 1 < len; i += 2)
		sum += (uint32_t)(p[i] << 8 | p[i + 1]);
	if (len & 1)
		sum += (uint32_t)(p[len - 1] << 8);
	while (sum >> 16)
		sum = (sum & 0xFFFF) + (sum >> 16);
	return (uint16_t)~sum;
}

static void test_icmp(void)
{
	uint8_t r[CARD_RESP_MAX], ip[4], evsock;
	uint16_t from;

	SEND(0x10, WIFI_ICMP);
	CHECK_EQ(read_resp(r, 1), 1);
	uint8_t sock = r[0];
	/* the host backend uses a ping socket: needs this user's group in
	 * net.ipv4.ping_group_range (most distributions allow every group) */
	CHECK(sock < WIFI_SOCKETS, "OPEN ICMP gave $%02X: is ping_group_range set?", sock);
	if (sock >= WIFI_SOCKETS)
		return;

	/* an echo request the host built, checksum and all, to 127.0.0.1 */
	uint8_t f[9 + 13] = {0x18, sock, 127, 0, 0, 1, 0xAA, 0xBB, 13,
	                     8, 0, 0, 0, 0x43, 0x21, 0x00, 0x01, 'c', 'u', 'p', 'c', '8'};
	uint16_t ck = inet_checksum(f + 9, 13);
	f[11] = (uint8_t)(ck >> 8);
	f[12] = (uint8_t)ck;
	send_frame(f, sizeof f);
	CHECK(rx_ready(sock), "RXREADY for the echo reply");
	int n = recvfrom_card(sock, 64, ip, &from, r);
	CHECK(n == 13, "RECVFROM on ICMP: %d bytes, not 13", n);
	CHECK(ip[0] == 127 && ip[3] == 1 && from == 0, "from %d.%d.%d.%d port %d", ip[0], ip[1], ip[2], ip[3], from);
	CHECK(n == 13 && r[0] == 0 && r[1] == 0, "an echo reply: type %d code %d", r[0], r[1]);
	CHECK(n == 13 && r[4] == 0x43 && r[5] == 0x21 && r[6] == 0 && r[7] == 1, "id and sequence kept");
	CHECK(n == 13 && !memcmp(r + 8, "cupc8", 5), "payload echoed");
	CHECK(n == 13 && inet_checksum(r, 13) == 0, "the reply's checksum holds");

	/* too short to be an ICMP message: ERROR(sock) */
	SEND(0x18, sock, 127, 0, 0, 1, 0, 0, 4, 8, 0, 0, 0);
	CHECK(wait_event(WIFI_EV_ERROR, &evsock) && evsock == sock, "a 4-byte ICMP message: ERROR");
	SEND(0x17, sock);
}

static void test_errors(void)
{
	uint32_t e = w.card.errors;
	SEND(0x11, 9, 1, 2, 3, 4, 0, 0);                   /* CONNECT on a bad socket */
	SEND(0x14, 0);                                     /* SEND with no length */
	SEND(0x77);                                        /* unknown opcode */
	CHECK_EQ(w.card.errors, e + 3);

	/* the new commands: short frames and bad sockets are counted, not answered */
	uint8_t r[8];
	e = w.card.errors;
	SEND(0x19, 0, 0x35);                               /* UDP_BIND with half a port */
	CHECK_EQ(read_resp(r, 8), 0);
	SEND(0x19, 3, 0x35, 0);                            /* UDP_BIND on a socket not open */
	CHECK_EQ(read_resp(r, 8), 0);
	SEND(0x1A, 0);                                     /* RECVFROM with no max */
	CHECK_EQ(read_resp(r, 8), 0);
	SEND(0x1A, 7, 64);                                 /* RECVFROM on socket 7 */
	CHECK_EQ(read_resp(r, 8), 0);
	SEND(0x18, 0, 127, 0, 0, 1, 0, 0);                 /* UDP_SENDTO with no length */
	CHECK_EQ(read_resp(r, 8), 0);
	CHECK_EQ(w.card.errors, e + 5);

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
	test_net_config();
	test_udp();
	test_icmp();
	test_errors();
	return check_report("WIFI-001/002/005 wifi core");
}
