#include "frames.h"

#include <string.h>

#include "freertos/FreeRTOS.h"

#define RING 4096                   /* bytes of queued frames, 2-byte length each */

static card_t *card;
static uint8_t ring[RING];
static volatile uint32_t head, tail;             /* free-running */
static volatile int commands;                    /* queued frames other than READ */
static volatile bool busy;
static portMUX_TYPE lock = portMUX_INITIALIZER_UNLOCKED;

void frames_init(card_t *c)
{
	card = c;
}

static void put(uint32_t at, uint8_t b)
{
	ring[at % RING] = b;
}

bool frames_received(const uint8_t *mosi, int len)
{
	if (len <= 0)
		return true;
	if (len > FRAMES_MAX_LEN || RING - (head - tail) < (uint32_t)len + 2)
		return false;
	uint32_t h = head;
	put(h, (uint8_t)len);
	put(h + 1, (uint8_t)(len >> 8));
	for (int i = 0; i < len; i++)
		put(h + 2 + i, mosi[i]);
	portENTER_CRITICAL_SAFE(&lock);
	head = h + 2 + (uint32_t)len;
	if (mosi[0] != CARD_OP_READ)
		commands++;
	portEXIT_CRITICAL_SAFE(&lock);
	return true;
}

int frames_preload(uint8_t *miso, int max)
{
	int n = 0;
	miso[n++] = (uint8_t)(card->ops->status(card) & 0x7f);
	if (!commands && !busy && card->resp_ready && n + 1 + card->resp_len <= max) {
		miso[n++] = (uint8_t)card->resp_len;
		memcpy(&miso[n], card->resp, (size_t)card->resp_len);
		n += card->resp_len;
	}
	return n;
}

void frames_busy(bool b)
{
	busy = b;
}

int frames_poll(void)
{
	int n = 0;
	while (tail != head) {
		uint32_t t = tail;
		int len = ring[t % RING] | ring[(t + 1) % RING] << 8;
		bool command = ring[(t + 2) % RING] != CARD_OP_READ;
		busy = true;
		card_select(card, true);
		for (int i = 0; i < len; i++) {
			(void)card_next_miso(card);
			card_mosi(card, ring[(t + 2 + i) % RING]);
		}
		card_select(card, false);
		portENTER_CRITICAL(&lock);
		tail = t + 2 + (uint32_t)len;
		if (command)
			commands--;
		busy = false;
		portEXIT_CRITICAL(&lock);
		n++;
	}
	return n;
}
