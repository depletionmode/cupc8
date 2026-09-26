/* The QEMU build's slot SPI for the whole-machine emulator: the lockstep
 * QEMU (tools/qemu_build.sh, tools/patches/qemu-esp-lockstep.patch) has a
 * stand-in for the GPSPI2 slave at GPSPI2's address and interrupt, which
 * holds the MISO preload the way the real slave's queued DMA descriptor
 * does. This is transport_spi.c's done()/arm() against it: when a frame ends
 * the ISR queues its MOSI bytes and arms the next frame's preload, swapped in
 * whole by one register write. A stock QEMU has no such device (its ID reads
 * 0) and the UART transport serves instead. */
#include "esp_intr_alloc.h"
#include "frames.h"
#include "soc/interrupts.h"
#include "transport.h"

#define BASE 0x60024000u
#define REG(off) (*(volatile uint32_t *)(BASE + (off)))
#define TX(i) (*(volatile uint8_t *)(BASE + (i)))
#define RX(i) (*(volatile uint8_t *)(BASE + 0x200 + (i)))
#define TXCOMMIT 0x400
#define RXLEN 0x404
#define INT 0x408
#define ID 0x40c
#define ID_C8SL 0x4c533843u

static void arm(void)
{
	static uint8_t pre[FRAMES_MAX_LEN];
	int n = frames_preload(pre, FRAMES_MAX_LEN);
	for (int i = 0; i < n; i++)
		TX(i) = pre[i];
	REG(TXCOMMIT) = (uint32_t)n;         /* then $00s, as arm() zero-fills */
}

static void done(void *arg)
{
	static uint8_t mosi[FRAMES_MAX_LEN];
	REG(INT) = REG(INT);
	int len = (int)REG(RXLEN);
	for (int i = 0; i < len; i++)
		mosi[i] = RX(i);
	frames_received(mosi, len);
	arm();
}

bool transport_slotdev_start(void)
{
	if (REG(ID) != ID_C8SL)
		return false;
	arm();
	ESP_ERROR_CHECK(esp_intr_alloc(ETS_SPI2_INTR_SOURCE, 0, done, NULL, NULL));
	return true;
}
