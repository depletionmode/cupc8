#include "slotspi.h"

#include <string.h>

#include "hardware/dma.h"
#include "hardware/gpio.h"
#include "hardware/irq.h"
#include "hardware/pio.h"
#include "hardware/sync.h"
#include "pins.h"
#include "slotspi.pio.h"

/* the PIO program waits on these GPIOs by number */
_Static_assert(PIN_SLOT_SCK == 2 && PIN_SLOT_MOSI == 3 && PIN_SLOT_MISO == 4 && PIN_SLOT_NCS == 5,
	       "slotspi.pio hard-codes the slot pins");

#define RING_BITS 14                    /* 16 KB of MOSI bytes */
#define RING_SIZE (1u << RING_BITS)
#define QUEUE_LEN 32                    /* frames */

static uint8_t ring[RING_SIZE] __attribute__((aligned(RING_SIZE)));
static struct { uint32_t start, end; } queue[QUEUE_LEN];
static volatile uint32_t q_head, q_tail;        /* free-running */
static volatile uint32_t q_commands;            /* queued frames other than READ */
static uint32_t frame_start;                    /* ring position (free-running) */
static uint32_t replayed_bytes;                 /* bytes of frames replayed */
static volatile bool busy;

/* two: slotspi_refresh() fills the one the TX DMA is not reading */
static uint8_t preload[2][2 + CARD_RESP_MAX];
static int cur;                                 /* the one armed */

static card_t *card;
static slotspi_status_fn status_fn;
static PIO pio = pio1;                          /* pio0 is PicoDVI's on the GPU */
static uint sm, prog;
static int dma_rx, dma_tx;
volatile uint32_t slotspi_errors;

/* free-running count of MOSI bytes the RX DMA has written */
static uint32_t rx_count(void)
{
	return 0xffffffffu - dma_channel_hw_addr(dma_rx)->transfer_count;
}

static void rx_start(void)
{
	dma_channel_config c = dma_channel_get_default_config(dma_rx);
	channel_config_set_transfer_data_size(&c, DMA_SIZE_8);
	channel_config_set_read_increment(&c, false);
	channel_config_set_write_increment(&c, true);
	channel_config_set_ring(&c, true, RING_BITS);
	channel_config_set_dreq(&c, pio_get_dreq(pio, sm, false));
	dma_channel_configure(dma_rx, &c, ring, &pio->rxf[sm], 0xffffffffu, true);
}

/* MISO for the next frame into p: the status byte, then the response if
 * one is ready and nothing that could change it is still queued or running
 * (a READ frame changes nothing). Returns the length. */
static uint fill(uint8_t *p)
{
	uint32_t queued_frames = q_head - q_tail;
	uint32_t queued_bytes = frame_start - replayed_bytes;
	uint n = 0;
	p[n++] = (uint8_t)(status_fn(card, queued_bytes, queued_frames) & 0x7f);
	if (!q_commands && !busy && card->resp_ready) {
		p[n++] = (uint8_t)card->resp_len;
		memcpy(&p[n], card->resp, (size_t)card->resp_len);
		n += (uint)card->resp_len;
	}
	return n;
}

/* The TX DMA feeds preload[b] to the SM (after it, `pull noblock` sends
 * $00). The SM's first pull blocks, so it waits for the status byte if CS_n
 * falls while this is still loading it. */
static void __not_in_flash_func(start_tx)(int b, uint n)
{
	dma_channel_config c = dma_channel_get_default_config(dma_tx);
	channel_config_set_transfer_data_size(&c, DMA_SIZE_8);      /* a byte lands in all four lanes */
	channel_config_set_read_increment(&c, true);
	channel_config_set_write_increment(&c, false);
	channel_config_set_dreq(&c, pio_get_dreq(pio, sm, true));
	dma_channel_configure(dma_tx, &c, &pio->txf[sm], preload[b], n, true);
	cur = b;
}

static void arm_tx(void)
{
	start_tx(cur, fill(preload[cur]));
}

static bool is_command(uint32_t start)
{
	return ring[start % RING_SIZE] != CARD_OP_READ;
}

static void sm_restart(void)
{
	pio_sm_set_enabled(pio, sm, false);
	pio_sm_exec(pio, sm, pio_encode_set(pio_pindirs, 0));   /* MISO Hi-Z */
	pio_sm_clear_fifos(pio, sm);
	pio_sm_restart(pio, sm);
	pio_sm_exec(pio, sm, pio_encode_set(pio_x, 0));
	pio_sm_exec(pio, sm, pio_encode_jmp(prog + slotspi_offset_start));
}

/* CS_n rose: the frame is over */
static void cs_rose(uint gpio, uint32_t events)
{
	(void)gpio;
	(void)events;
	/* the last byte may still be on its way from the RX FIFO */
	while (!pio_sm_is_rx_fifo_empty(pio, sm))
		tight_loop_contents();
	uint32_t end = rx_count();
	dma_channel_abort(dma_tx);
	sm_restart();
	if (end != frame_start) {
		if (q_head - q_tail < QUEUE_LEN) {
			queue[q_head % QUEUE_LEN].start = frame_start;
			queue[q_head % QUEUE_LEN].end = end;
			q_head++;
			q_commands += is_command(frame_start);
		} else {
			slotspi_errors++;
			replayed_bytes += end - frame_start;    /* dropped: never replayed */
		}
		frame_start = end;
	}
	arm_tx();
	pio_sm_set_enabled(pio, sm, true);
}

void slotspi_init(card_t *c, slotspi_status_fn status)
{
	card = c;
	status_fn = status;
	prog = pio_add_program(pio, &slotspi_program);
	sm = (uint)pio_claim_unused_sm(pio, true);
	dma_rx = dma_claim_unused_channel(true);
	dma_tx = dma_claim_unused_channel(true);

	pio_sm_config cfg = slotspi_program_get_default_config(prog);
	sm_config_set_in_pins(&cfg, PIN_SLOT_MOSI);
	sm_config_set_out_pins(&cfg, PIN_SLOT_MISO, 1);
	sm_config_set_set_pins(&cfg, PIN_SLOT_MISO, 1);
	sm_config_set_in_shift(&cfg, false, true, 8);
	sm_config_set_out_shift(&cfg, false, false, 32);
	pio_gpio_init(pio, PIN_SLOT_MISO);
	gpio_init(PIN_SLOT_SCK);
	gpio_init(PIN_SLOT_MOSI);
	gpio_init(PIN_SLOT_NCS);
	gpio_pull_up(PIN_SLOT_NCS);                     /* no host: not selected */
	pio_sm_init(pio, sm, prog + slotspi_offset_start, &cfg);

	/* SLOT_nIRQ is open drain: driven low, or released */
	gpio_init(PIN_SLOT_NIRQ);
	gpio_put(PIN_SLOT_NIRQ, 0);
	gpio_set_dir(PIN_SLOT_NIRQ, false);

	rx_start();
	sm_restart();
	arm_tx();
	gpio_set_irq_enabled_with_callback(PIN_SLOT_NCS, GPIO_IRQ_EDGE_RISE, true, cs_rose);
	/* high, but below the GPU's PicoDVI DMA interrupt (priority 0), which
	 * must never wait: it has a porch interval to set up the next scanline.
	 * This one has the host's 20 us between frames. */
	irq_set_priority(IO_IRQ_BANK0, 0x40);
	pio_sm_set_enabled(pio, sm, true);
}

void slotspi_busy(bool b)
{
	busy = b;
}

void __not_in_flash_func(slotspi_refresh)(void)
{
	const uint start = prog + slotspi_offset_start;
	/* CS_n's interrupt shares this state (see slotspi_init) */
	irq_set_enabled(IO_IRQ_BANK0, false);
	/* A frame has begun: it goes out with the old preload, and cs_rose
	 * re-arms after it. Never stop the SM then: a host clocking a stopped
	 * SM loses bits (the MISO bytes, and the MOSI bytes of a command,
	 * shift by the SCK edges missed). */
	if (pio_sm_get_pc(pio, sm) != start) {
		irq_set_enabled(IO_IRQ_BANK0, true);
		return;
	}
	/* the new preload, into the buffer the DMA is not reading */
	int b = cur ^ 1;
	uint n = fill(preload[b]);
	/* Swap it in only while the SM is still waiting for CS_n: stopped, it
	 * cannot move on, and at `start` it has pulled nothing. (Checking the
	 * CS_n pin instead raced a falling CS_n: the SM could pull the old
	 * status byte between the check and the FIFO clear, and the frame then
	 * began with two status bytes.) The SM is stopped for a few dozen
	 * cycles from RAM with every interrupt off, so even if CS_n falls
	 * meanwhile it runs again long before the host's first SCK edge (>= 2
	 * us after CS_n). Stopping it with interrupts on, or around fill()
	 * running from flash, held it for up to ~10 us: CS_n fell, the host
	 * clocked the first bits with MISO still Hi-Z (a status byte with bit 7
	 * set) and the SM, restarted mid-byte, lost the frame's alignment. The
	 * video's DMA interrupt on the GPU waits those few cycles at most. */
	uint32_t irq = save_and_disable_interrupts();
	if (pio_sm_get_pc(pio, sm) == start) {
		pio_sm_set_enabled(pio, sm, false);
		if (pio_sm_get_pc(pio, sm) == start) {
			dma_channel_abort(dma_tx);
			pio_sm_clear_fifos(pio, sm);
			start_tx(b, n);
		}
		pio_sm_set_enabled(pio, sm, true);
	}
	restore_interrupts(irq);
	irq_set_enabled(IO_IRQ_BANK0, true);
}

void slotspi_update_irq(void)
{
	gpio_set_dir(PIN_SLOT_NIRQ, card_irq(card));   /* output (low) = asserted */
}

int slotspi_poll(void)
{
	int n = 0;
	while (q_tail != q_head) {
		uint32_t start = queue[q_tail % QUEUE_LEN].start, end = queue[q_tail % QUEUE_LEN].end;
		busy = true;
		card_select(card, true);
		for (uint32_t i = start; i != end; i++) {
			(void)card_next_miso(card);
			card_mosi(card, ring[i % RING_SIZE]);
		}
		card_select(card, false);
		irq_set_enabled(IO_IRQ_BANK0, false);
		replayed_bytes += end - start;
		q_commands -= is_command(start);
		q_tail++;
		busy = false;
		irq_set_enabled(IO_IRQ_BANK0, true);
		n++;
	}
	if (n)
		slotspi_refresh();
	slotspi_update_irq();
	return n;
}
