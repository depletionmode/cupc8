#include "swdtarget.h"

#include <string.h>

#define DPIDR       0x0BC12477u         /* RP2040: DPv2, multi-drop */
#define TARGET_ID   0x01002927u         /* TARGETSEL for core 0 */
#define AHB_AP_IDR  0x04770031u

/* the boot ROM: magic at $10, the function table pointer at $14 */
#define ROM_FUNCS   0x0100
static const struct { char code[2]; uint16_t addr; } rom_funcs[] = {
	{{'I', 'F'}, 0x0200}, {{'E', 'X'}, 0x0210}, {{'R', 'E'}, 0x0220},
	{{'R', 'P'}, 0x0230}, {{'F', 'C'}, 0x0240}, {{'C', 'X'}, 0x0250},
};

/* the alert sequence, 128 bits sent LSB first (ADIv5.2, value
 * 0x19BC0EA2E3DDAFE986852D956209F392) */
static const uint8_t alert[16] = {
	0x92, 0xf3, 0x09, 0x62, 0x95, 0x2d, 0x85, 0x86,
	0xe9, 0xaf, 0xdd, 0xe3, 0xa2, 0x0e, 0xbc, 0x19,
};

void swdt_init(swdt_t *t)
{
	memset(t, 0, sizeof *t);
	t->dormant = true;
	t->after_alert = -1;
	t->since_reset = -1;
	memset(t->flash, 0xff, sizeof t->flash);
	t->halted = false;                /* the card runs its firmware */
}

static int parity32(uint32_t v)
{
	int p = 0;
	for (; v; v &= v - 1)
		p ^= 1;
	return p;
}

static void queue(swdt_t *t, uint32_t bits, int n)
{
	for (int i = 0; i < n; i++)
		t->outq[t->outq_n++] = (uint8_t)(bits >> i & 1);
}

/* ---------------------------------------------------------------- memory */

static uint16_t rom16(uint32_t a)
{
	if (a == 0x10) return 'M' | 'u' << 8;
	if (a == 0x12) return 0x01;
	if (a == 0x14) return ROM_FUNCS;
	if (a >= ROM_FUNCS && a < ROM_FUNCS + 4 * 7) {
		int i = (int)(a - ROM_FUNCS) / 4;
		if (i >= 6)
			return 0;
		return (a & 2) ? rom_funcs[i].addr : (uint16_t)(rom_funcs[i].code[0] | rom_funcs[i].code[1] << 8);
	}
	return 0;
}

static uint32_t mem_read(swdt_t *t, uint32_t a, bool *fault)
{
	a &= ~3u;
	if (a < 0x4000)
		return rom16(a) | (uint32_t)rom16(a + 2) << 16;
	if (a >= 0x10000000 && a < 0x10000000 + SWDT_FLASH) {
		if (!t->xip)
			return 0xffffffff;        /* XIP is off until CX: nothing useful */
		uint32_t o = a - 0x10000000, v;
		memcpy(&v, t->flash + o, 4);
		return v;
	}
	if (a >= 0x20000000 && a < 0x20000000 + SWDT_RAM) {
		uint32_t v;
		memcpy(&v, t->ram + (a - 0x20000000), 4);
		return v;
	}
	switch (a) {
	case 0xE000EDF0:                  /* DHCSR */
		return (t->halted ? 1u << 17 : 0) | 1u << 16 | (t->halted ? 2u : 0) | (t->debugen ? 1u : 0);
	case 0xE000EDF8: return t->dcrdr;
	case 0xE000EDFC: return t->demcr;
	}
	*fault = true;
	return 0;
}

static uint16_t ram16(swdt_t *t, uint32_t a)
{
	if (a < 0x20000000 || a + 2 > 0x20000000 + SWDT_RAM)
		return 0;
	return (uint16_t)(t->ram[a - 0x20000000] | t->ram[a - 0x20000000 + 1] << 8);
}

/* the core runs from PC: a boot ROM flash routine returns to LR, where the
 * host has put a BKPT; anything else and the card just runs on */
static void run(swdt_t *t)
{
	uint32_t pc = t->regs[15] & ~1u, *r = t->regs;
	int fn = -1;
	for (int i = 0; i < 6; i++)
		if (pc == rom_funcs[i].addr)
			fn = i;
	t->halted = false;
	if (fn < 0)
		return;
	t->calls++;
	bool ok = true;
	switch (fn) {
	case 0: t->connected = true; break;                                      /* IF */
	case 1: t->cmd_mode = t->connected; t->xip = false; ok = t->connected; break;   /* EX */
	case 2:                                                                  /* RE addr, count, block, cmd */
		ok = t->cmd_mode && !(r[0] & 0xfff) && !(r[1] & 0xfff) && r[0] + r[1] <= SWDT_FLASH;
		if (ok)
			memset(t->flash + r[0], 0xff, r[1]);
		break;
	case 3:                                                                  /* RP addr, data, count */
		ok = t->cmd_mode && !(r[0] & 0xff) && !(r[2] & 0xff) && r[0] + r[2] <= SWDT_FLASH &&
		     r[1] >= 0x20000000 && r[1] + r[2] <= 0x20000000 + SWDT_RAM;
		if (ok)
			for (uint32_t i = 0; i < r[2]; i++)
				t->flash[r[0] + i] &= t->ram[r[1] - 0x20000000 + i];
		break;
	case 4: break;                                                           /* FC */
	case 5: ok = t->cmd_mode; t->xip = ok; t->cmd_mode = false; break;       /* CX */
	}
	if (!ok)
		return;                       /* a real ROM would fault or hang: never halts */
	r[15] = r[14] & ~1u;
	if (ram16(t, r[15]) == 0xBE00)    /* BKPT #0 */
		t->halted = true;
}

static void mem_write(swdt_t *t, uint32_t a, uint32_t v, bool *fault)
{
	a &= ~3u;
	if (a >= 0x20000000 && a < 0x20000000 + SWDT_RAM) {
		memcpy(t->ram + (a - 0x20000000), &v, 4);
		return;
	}
	switch (a) {
	case 0xE000EDF0:                  /* DHCSR: needs the key */
		if ((v >> 16) != 0xA05F)
			return;
		t->debugen = v & 1;
		if (t->debugen && (v & 2))
			t->halted = true;
		else if (t->halted && !(v & 2))
			run(t);
		return;
	case 0xE000EDF4: {                /* DCRSR */
		int sel = (int)(v & 0x7f);
		if (sel < 20) {
			if (v & 0x10000)
				t->regs[sel] = t->dcrdr;
			else
				t->dcrdr = t->regs[sel];
		}
		return;
	}
	case 0xE000EDF8: t->dcrdr = v; return;
	case 0xE000EDFC: t->demcr = v; return;
	case 0xE000ED0C:                  /* AIRCR: SYSRESETREQ */
		if ((v >> 16) == 0x05FA && (v & 4)) {
			t->resets++;
			t->xip = true;            /* the boot path sets up XIP again */
			t->cmd_mode = t->connected = false;
			t->halted = (t->demcr & 1) && t->debugen;   /* VC_CORERESET */
		}
		return;
	}
	*fault = true;
}

/* ---------------------------------------------------------------- DP/AP */

/* the ack an AP access gets: FAULT while debug is off or an error is
 * pending, WAIT on every Nth attempt (if asked), else OK */
static int ap_ack(swdt_t *t)
{
	if (!(t->ctrl & (1u << 28)) || t->sticky) {
		t->sticky = true;
		return 4;
	}
	if (t->wait_every && ++t->wait_count % t->wait_every == 0)
		return 2;
	return 1;
}

static int ap_access(swdt_t *t, bool read, int a, uint32_t *v)
{
	int reg = (int)(t->select & 0xf0) | a;
	if ((t->select >> 24) != 0) {         /* only AP 0 exists */
		*v = 0;
		return 1;
	}
	bool fault = false;
	switch (reg) {
	case 0x00:
		if (read) *v = t->csw; else t->csw = *v;
		break;
	case 0x04:
		if (read) *v = t->tar; else t->tar = *v;
		break;
	case 0x0C:
		if ((t->csw & 7) != 2) {          /* this model does words only */
			fault = true;
			break;
		}
		if (read)
			*v = mem_read(t, t->tar, &fault);
		else
			mem_write(t, t->tar, *v, &fault);
		if ((t->csw >> 4 & 3) == 1)       /* auto-increment wraps within 1 KB */
			t->tar = (t->tar & ~0x3ffu) | ((t->tar + 4) & 0x3ffu);
		break;
	case 0xFC:
		if (read) *v = AHB_AP_IDR;
		break;
	default:
		if (read) *v = 0;
	}
	if (fault) {
		t->sticky = true;
		return 4;
	}
	return 1;
}

static void request(swdt_t *t)
{
	uint8_t r = t->req;
	bool ap = r >> 1 & 1, rd = r >> 2 & 1;
	int a = (r >> 3 & 3) * 4;
	bool valid = (r & 1) && !(r >> 6 & 1) && (r >> 7 & 1) && ((r >> 1 & 1) ^ (r >> 2 & 1) ^ (r >> 3 & 1) ^ (r >> 4 & 1)) == (r >> 5 & 1);
	t->phase = 0;
	t->outq_n = t->outq_pos = 0;
	if (!valid)
		return;
	if (!ap && !rd && a == 0x0C && t->need_reset == false) {
		t->phase = 3;                      /* TARGETSEL: nobody drives the ack */
		t->nbits = 0;
		t->shift = 0;
		return;
	}
	if (!t->selected)
		return;                            /* not us: the line stays pulled up */
	uint32_t v = 0;
	int ack = 1;
	if (rd) {
		if (ap) {
			ack = ap_ack(t);
			if (ack == 1)
				ack = ap_access(t, true, a, &v);
			if (ack == 1) {                /* posted: this returns the previous read */
				uint32_t prev = t->ap_last;
				t->ap_last = v;
				t->rdbuff = v;
				v = prev;
			}
		} else {
			switch (a) {
			case 0x0: v = DPIDR; break;
			case 0x4: v = (t->ctrl & 0x50000000u) | (t->ctrl & 0x50000000u) << 1 | (t->sticky ? 0x20 : 0); break;
			case 0x8: v = 0; break;        /* RESEND: not modelled */
			case 0xC: v = t->rdbuff; break;
			}
		}
		queue(t, (uint32_t)ack, 3);
		if (ack == 1) {
			queue(t, v, 32);
			queue(t, (uint32_t)parity32(v), 1);
		}
		return;
	}
	/* writes: ack now, data next */
	t->req = r;
	int pending = ap ? ap_ack(t) : 1;
	queue(t, (uint32_t)pending, 3);
	if (pending == 1) {
		t->phase = 2;
		t->nbits = 0;
		t->shift = 0;
	}
}

static void write_done(swdt_t *t)
{
	uint32_t v = (uint32_t)t->shift;
	int p = (int)(t->shift >> 32 & 1);
	uint8_t r = t->req;
	bool ap = r >> 1 & 1;
	int a = (r >> 3 & 3) * 4;
	t->phase = 0;
	if (p != parity32(v)) {
		t->sticky = true;                  /* WDATAERR */
		return;
	}
	if (ap) {
		ap_access(t, false, a, &v);        /* acked when the request came */
		return;
	}
	switch (a) {
	case 0x0: if (v & 0x1e) t->sticky = false; break;   /* ABORT clears the sticky flags */
	case 0x4: t->ctrl = v; break;
	case 0x8: t->select = v; break;
	}
}

void swdt_out(swdt_t *t, int bit)
{
	bit &= 1;
	t->ones = bit ? t->ones + 1 : 0;

	if (t->dormant) {
		/* slide the 128-bit window, then look for the activation code */
		for (int i = 0; i < 15; i++)
			t->window[i] = (uint8_t)(t->window[i] >> 1 | t->window[i + 1] << 7);
		t->window[15] = (uint8_t)(t->window[15] >> 1 | bit << 7);
		if (t->after_alert >= 0) {
			int k = t->after_alert++;
			if (k < 4 && bit)
				t->after_alert = -1;        /* 4 low cycles were required */
			else if (k >= 4) {
				t->act |= (uint8_t)(bit << (k - 4));
				if (k == 11) {
					if (t->act == 0x1A) {   /* SWD */
						t->dormant = false;
						t->need_reset = true;
					}
					t->after_alert = -1;
					t->act = 0;
				}
			}
		} else if (!memcmp(t->window, alert, 16)) {
			t->after_alert = 0;
			t->act = 0;
		}
		return;
	}
	if (t->ones >= 50) {                  /* line reset */
		t->need_reset = false;
		t->selected = false;
		t->phase = 0;
		t->outq_n = t->outq_pos = 0;
		t->since_reset = 0;
		t->to_dormant = 0;
		return;
	}
	/* SWD to dormant: $E3BC (LSB first) right after a line reset */
	if (t->since_reset >= 0 && t->since_reset < 16) {
		t->to_dormant |= (uint16_t)(bit << t->since_reset++);
		if (t->since_reset == 16 && t->to_dormant == 0xE3BC) {
			t->dormant = true;
			t->need_reset = false;
			t->selected = false;
			t->phase = 0;
			t->since_reset = -1;
			memset(t->window, 0, sizeof t->window);
			return;
		}
	}
	if (t->need_reset)
		return;
	switch (t->phase) {
	case 0:
		if (bit) {
			t->phase = 1;
			t->nbits = 1;
			t->req = 1;
		}
		return;
	case 1:
		t->req |= (uint8_t)(bit << t->nbits++);
		if (t->nbits == 8)
			request(t);
		return;
	case 2:
	case 3:
		t->shift |= (uint64_t)bit << t->nbits++;
		if (t->nbits == 33) {
			if (t->phase == 2) {
				write_done(t);
			} else {
				uint32_t v = (uint32_t)t->shift;
				t->selected = v == TARGET_ID && (int)(t->shift >> 32 & 1) == parity32(v);
				t->phase = 0;
			}
		}
		return;
	}
}

int swdt_in(swdt_t *t)
{
	if (t->outq_pos < t->outq_n)
		return t->outq[t->outq_pos++];
	return 1;                             /* undriven: the pull-up */
}
