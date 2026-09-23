#include "wifi.h"

#include <string.h>

#define WIFI_FW_MAJOR 1
#define WIFI_FW_MINOR 0

static void event(wifi_t *w, uint8_t code, uint8_t sock)
{
	if (w->nevents >= WIFI_EVENTS) {
		w->card.errors++;                 /* the host is not draining events */
		return;
	}
	w->events[w->nevents][0] = code;
	w->events[w->nevents][1] = sock;
	w->nevents++;
}

static wifi_socket_t *sock_of(wifi_t *w, uint8_t n)
{
	return n < WIFI_SOCKETS && w->sock[n].used ? &w->sock[n] : 0;
}

void wifi_poll(wifi_t *w)
{
	uint8_t rssi, ip[4], gw[4], dns[4];

	if (w->net->poll)
		w->net->poll(w->ctx);

	/* link transitions */
	int state = w->net->link_state(w->ctx, &rssi, ip, gw, dns);
	if (state != w->link) {
		if (state == WIFI_LINK_UP)
			event(w, WIFI_EV_JOINED, 0);
		else if (state == WIFI_LINK_FAILED)
			event(w, WIFI_EV_JOIN_FAILED, 0);
		else if (w->link == WIFI_LINK_UP && state == WIFI_LINK_IDLE)
			event(w, WIFI_EV_LINK_LOST, 0);
		if (state != WIFI_LINK_JOINING)
			w->busy = false;
		w->link = (uint8_t)state;
	}

	/* a name lookup in progress */
	if (w->pending_host[0]) {
		int r = w->net->resolve(w->ctx, w->pending_host, w->resolve_ip);
		if (r != 0) {
			/* the name is also TLS's SNI and certificate name (CONNECT_HOST) */
			char host[sizeof w->pending_host];
			memcpy(host, w->pending_host, sizeof host);
			w->resolve_ok = r > 0;
			w->pending_host[0] = 0;
			w->busy = false;
			if (w->pending_sock >= 0) {
				wifi_socket_t *s = sock_of(w, (uint8_t)w->pending_sock);
				if (!s || !w->resolve_ok ||
				    w->net->connect(w->ctx, s->handle, w->resolve_ip, w->pending_port, host) < 0) {
					event(w, WIFI_EV_CONN_FAILED, (uint8_t)w->pending_sock);
					if (s)
						s->state = WIFI_CLOSED;
				} else if (s) {
					s->state = WIFI_CONNECTING;
				}
				w->pending_sock = -1;
			} else {
				event(w, WIFI_EV_RESOLVED, 0);
			}
		}
	}

	/* socket state changes */
	for (int i = 0; i < WIFI_SOCKETS; i++) {
		wifi_socket_t *s = &w->sock[i];
		if (!s->used)
			continue;
		int rx = 0, tx = 0;
		int st = w->net->status(w->ctx, s->handle, &rx, &tx);
		if (st == WIFI_OPEN && s->state == WIFI_CONNECTING)
			event(w, WIFI_EV_CONNECTED, (uint8_t)i);
		else if (st == WIFI_OPEN && s->state == WIFI_LISTENING)
			event(w, WIFI_EV_ACCEPTED, (uint8_t)i);
		else if (st == WIFI_CLOSED && s->state == WIFI_CONNECTING)
			event(w, WIFI_EV_CONN_FAILED, (uint8_t)i);
		else if (st == WIFI_PEER_CLOSED && s->state == WIFI_OPEN)
			event(w, WIFI_EV_PEER_CLOSED, (uint8_t)i);
		s->state = (uint8_t)st;
	}
}

/* ------------------------------------------------------------------ commands */

static void cmd_net_status(wifi_t *w)
{
	uint8_t r[15], rssi = 0, ip[4] = {0}, gw[4] = {0}, dns[4] = {0};
	int state = w->net->link_state(w->ctx, &rssi, ip, gw, dns);
	r[0] = (uint8_t)state;
	r[1] = rssi;
	memcpy(r + 2, ip, 4);
	memcpy(r + 6, gw, 4);
	memcpy(r + 10, dns, 4);
	card_respond(&w->card, r, 14);
}

static void cmd_scan_result(wifi_t *w, uint8_t idx)
{
	uint8_t r[2 + 1 + 32], rssi = 0, auth = 0;
	char ssid[33] = {0};
	int n = w->net->scan_result(w->ctx, idx, &rssi, &auth, ssid, (int)sizeof ssid - 1);
	if (n < 0) {
		uint8_t end = 0xFF;
		card_respond(&w->card, &end, 1);
		return;
	}
	int len = (int)strlen(ssid);
	r[0] = rssi;
	r[1] = auth;
	r[2] = (uint8_t)len;
	memcpy(r + 3, ssid, (size_t)len);
	card_respond(&w->card, r, 3 + len);
}

static void command(card_t *c, const uint8_t *f, int len)
{
	wifi_t *w = c->priv;
	uint8_t r[260];
	uint8_t op = f[0];

	switch (op) {
	case 0x01:
		cmd_net_status(w);
		break;
	case 0x02:
		if (w->net->scan_start(w->ctx) == 0) {
			w->busy = true;
			event(w, WIFI_EV_SCAN_DONE, 0);    /* backends scan synchronously for now */
			w->busy = false;
		}
		break;
	case 0x03:
		if (len < 2) { c->errors++; break; }
		cmd_scan_result(w, f[1]);
		break;
	case 0x04: {                               /* JOIN ssid, psk, save */
		if (len < 3) { c->errors++; break; }
		int p = 1;
		char ssid[33] = {0}, psk[65] = {0};
		int n = f[p++];
		if (n > 32 || p + n > len) { c->errors++; break; }
		memcpy(ssid, f + p, (size_t)n); p += n;
		if (p >= len) { c->errors++; break; }
		n = f[p++];
		if (n > 64 || p + n > len) { c->errors++; break; }
		memcpy(psk, f + p, (size_t)n);
		p += n;
		bool save = p < len && f[p];
		w->busy = true;
		w->link = WIFI_LINK_JOINING;
		if (w->net->join(w->ctx, ssid, psk, save) < 0) {
			w->busy = false;
			w->link = WIFI_LINK_FAILED;
			event(w, WIFI_EV_JOIN_FAILED, 0);
		}
		break;
	}
	case 0x05:
		w->net->leave(w->ctx, len >= 2 && f[1]);
		w->link = WIFI_LINK_IDLE;
		break;
	case 0x06: {                               /* RESOLVE name */
		if (len < 2 || f[1] > 63 || 2 + f[1] > len) { c->errors++; break; }
		memcpy(w->pending_host, f + 2, f[1]);
		w->pending_host[f[1]] = 0;
		w->pending_sock = -1;
		w->busy = true;
		break;
	}
	case 0x07:
		r[0] = w->resolve_ok ? 1 : 0;
		memcpy(r + 1, w->resolve_ip, 4);
		card_respond(c, r, 5);
		break;

	case 0x10: {                               /* OPEN type */
		if (len < 2) { c->errors++; break; }
		int idx = -1;
		for (int i = 0; i < WIFI_SOCKETS; i++)
			if (!w->sock[i].used) { idx = i; break; }
		int h = idx >= 0 ? w->net->open(w->ctx, f[1]) : -1;
		if (idx < 0 || h < 0) {
			r[0] = 0xFF;
		} else {
			w->sock[idx] = (wifi_socket_t){h, WIFI_CLOSED, true};
			r[0] = (uint8_t)idx;
		}
		card_respond(c, r, 1);
		break;
	}
	case 0x11: {                               /* CONNECT sock, ip, port */
		if (len < 8) { c->errors++; break; }
		wifi_socket_t *s = sock_of(w, f[1]);
		if (!s) { c->errors++; break; }
		uint16_t port = (uint16_t)(f[6] | (f[7] << 8));
		if (w->net->connect(w->ctx, s->handle, f + 2, port, 0) < 0)
			event(w, WIFI_EV_CONN_FAILED, f[1]);
		else
			s->state = WIFI_CONNECTING;
		break;
	}
	case 0x12: {                               /* CONNECT_HOST sock, port, host */
		if (len < 5 || 5 + f[4] > len || f[4] > 63) { c->errors++; break; }
		wifi_socket_t *s = sock_of(w, f[1]);
		if (!s) { c->errors++; break; }
		memcpy(w->pending_host, f + 5, f[4]);
		w->pending_host[f[4]] = 0;
		w->pending_port = (uint16_t)(f[2] | (f[3] << 8));
		w->pending_sock = f[1];
		w->busy = true;
		s->state = WIFI_CONNECTING;
		break;
	}
	case 0x13: {                               /* LISTEN sock, port */
		if (len < 4) { c->errors++; break; }
		wifi_socket_t *s = sock_of(w, f[1]);
		if (!s) { c->errors++; break; }
		uint16_t port = (uint16_t)(f[2] | (f[3] << 8));
		if (w->net->listen(w->ctx, s->handle, port) < 0)
			event(w, WIFI_EV_ERROR, f[1]);
		else
			s->state = WIFI_LISTENING;
		break;
	}
	case 0x14: {                               /* SEND sock, len, data */
		if (len < 3) { c->errors++; break; }
		wifi_socket_t *s = sock_of(w, f[1]);
		if (!s) { c->errors++; break; }
		int n = f[2];
		if (3 + n > len) { c->errors++; break; }
		if (w->net->send(w->ctx, s->handle, f + 3, n) != n)
			event(w, WIFI_EV_ERROR, f[1]);
		break;
	}
	case 0x15: {                               /* RECV sock, max */
		if (len < 3) { c->errors++; break; }
		wifi_socket_t *s = sock_of(w, f[1]);
		if (!s) { c->errors++; break; }
		int max = f[2];
		if (max > 250)
			max = 250;
		int n = w->net->recv(w->ctx, s->handle, r + 1, max);
		if (n < 0)
			n = 0;
		r[0] = (uint8_t)n;
		card_respond(c, r, 1 + n);
		break;
	}
	case 0x16: {                               /* SOCK_STATUS sock */
		if (len < 2) { c->errors++; break; }
		wifi_socket_t *s = sock_of(w, f[1]);
		if (!s) { c->errors++; break; }
		int rx = 0, tx = 0;
		int st = w->net->status(w->ctx, s->handle, &rx, &tx);
		r[0] = (uint8_t)st;
		r[1] = (uint8_t)rx;
		r[2] = (uint8_t)(rx >> 8);
		r[3] = (uint8_t)tx;
		r[4] = (uint8_t)(tx >> 8);
		card_respond(c, r, 5);
		break;
	}
	case 0x17: {                               /* CLOSE sock */
		if (len < 2) { c->errors++; break; }
		wifi_socket_t *s = sock_of(w, f[1]);
		if (!s) { c->errors++; break; }
		w->net->close(w->ctx, s->handle);
		w->sock[f[1]].used = false;
		w->sock[f[1]].state = WIFI_CLOSED;
		break;
	}
	case 0x18: {                               /* UDP_SENDTO sock, ip, port, len, data */
		if (len < 9) { c->errors++; break; }
		wifi_socket_t *s = sock_of(w, f[1]);
		if (!s) { c->errors++; break; }
		uint16_t port = (uint16_t)(f[6] | (f[7] << 8));
		int n = f[8];
		if (9 + n > len) { c->errors++; break; }
		if (w->net->connect(w->ctx, s->handle, f + 2, port, 0) < 0 ||
		    w->net->send(w->ctx, s->handle, f + 9, n) != n)
			event(w, WIFI_EV_ERROR, f[1]);
		break;
	}

	case 0x1F: {                               /* EVENTS */
		r[0] = (uint8_t)w->nevents;
		for (int i = 0; i < w->nevents; i++) {
			r[1 + i * 2] = w->events[i][0];
			r[2 + i * 2] = w->events[i][1];
		}
		card_respond(c, r, 1 + w->nevents * 2);
		w->nevents = 0;
		break;
	}
	default:
		c->errors++;
		break;
	}
}

/* ------------------------------------------------------------------ card glue */

static uint8_t status(card_t *c)
{
	wifi_t *w = c->priv;
	uint8_t s = 0;
	if (w->link == WIFI_LINK_UP)
		s |= 0x40;
	if (w->busy)
		s |= 0x20;
	if (w->nevents)
		s |= 0x10;
	for (int i = 0; i < WIFI_SOCKETS; i++) {
		if (!w->sock[i].used)
			continue;
		int rx = 0, tx = 0;
		if (w->net->status(w->ctx, w->sock[i].handle, &rx, &tx) >= 0 && rx > 0)
			s |= (uint8_t)(1 << i);
	}
	return s;
}

static bool irq(card_t *c) { return ((wifi_t *)c->priv)->nevents != 0; }
static void soft_reset(card_t *c) { wifi_reset(c->priv); }

static const card_ops_t wifi_ops = {
	.type = CARD_TYPE_WIFI, .fw_major = WIFI_FW_MAJOR, .fw_minor = WIFI_FW_MINOR,
	.status = status, .command = command, .soft_reset = soft_reset, .irq = irq,
};

void wifi_reset(wifi_t *w)
{
	for (int i = 0; i < WIFI_SOCKETS; i++) {
		if (w->sock[i].used)
			w->net->close(w->ctx, w->sock[i].handle);
		w->sock[i] = (wifi_socket_t){0, WIFI_CLOSED, false};
	}
	w->nevents = 0;
	w->busy = false;
	w->pending_host[0] = 0;
	w->pending_sock = -1;
	w->resolve_ok = false;
}

void wifi_init(wifi_t *w, const wifi_net_ops *net, void *ctx)
{
	memset(w, 0, sizeof *w);
	card_init(&w->card, &wifi_ops, w);
	w->net = net;
	w->ctx = ctx;
	wifi_reset(w);
}
