/* GPU-001/002/003: graphics card core (doc/hardware/gpu-protocol.md).
 * Rendering is checked pixel by pixel against the font and palette, not
 * against golden images produced by this same code. Frames are also written
 * to build/fw as PPM files for a human to look at. */
#include <stdio.h>
#include <string.h>

#include "check.h"
#include "font8x8_cp437.h"
#include "gpu.h"

static gpu_t gpu;
static uint32_t frame[GPU_OUT_W * GPU_OUT_H];

/* send one command frame and let the card execute it */
static void send(const uint8_t *bytes, int len)
{
	card_frame(&gpu.card, bytes, 0, len);
	gpu_run(&gpu, 1000);
}
#define SEND(...) do { uint8_t b_[] = {__VA_ARGS__}; send(b_, (int)sizeof b_); } while (0)

static int read_resp(uint8_t *out, int n)
{
	uint8_t mosi[2 + 16] = {CARD_OP_READ}, miso[2 + 16];
	card_frame(&gpu.card, mosi, miso, 2 + n);
	memcpy(out, miso + 2, (size_t)n);
	return miso[1];
}

static uint8_t status(void)
{
	uint8_t nop = 0x00, st;
	card_select(&gpu.card, true);
	st = card_next_miso(&gpu.card);
	card_mosi(&gpu.card, nop);
	card_select(&gpu.card, false);
	gpu_run(&gpu, 1000);
	return st;
}

static uint32_t pal(int i)
{
	uint16_t c = gpu.palette[i];
	uint32_t r = (c >> 11) & 0x1F, g = (c >> 5) & 0x3F, b = c & 0x1F;
	return ((r * 255 / 31) << 16) | ((g * 255 / 63) << 8) | (b * 255 / 31);
}

static void dump(const char *name)
{
	char path[256];
	snprintf(path, sizeof path, "%s/%s.ppm", getenv("OUT") ? getenv("OUT") : ".", name);
	FILE *f = fopen(path, "wb");
	if (!f)
		return;
	fprintf(f, "P6\n%d %d\n255\n", GPU_OUT_W, GPU_OUT_H);
	for (int i = 0; i < GPU_OUT_W * GPU_OUT_H; i++) {
		uint8_t px[3] = {(uint8_t)(frame[i] >> 16), (uint8_t)(frame[i] >> 8), (uint8_t)frame[i]};
		fwrite(px, 1, 3, f);
	}
	fclose(f);
}

/* the 8x16 cell at (col,row) shows character ch in attr */
static bool cell_shows(int col, int row, uint8_t ch, uint8_t attr)
{
	for (int r = 0; r < 16; r++)
		for (int b = 0; b < 8; b++) {
			bool on = font8x8_cp437[ch][r / 2] & (0x80 >> b);
			uint32_t want = on ? pal(attr & 15) : pal(attr >> 4);
			if (frame[(row * 16 + r) * GPU_OUT_W + col * 8 + b] != want)
				return false;
		}
	return true;
}

static uint32_t gpx(int x, int y) { return frame[(2 * y) * GPU_OUT_W + 2 * x]; }

static void test_text(void)
{
	uint8_t r[4];
	gpu.vsync_count = 15;                     /* cursor blink phase: off */
	SEND(0x14, 0);                            /* cursor off for clean cells */

	/* PUTC and wrapping */
	SEND(0x13, 0x1E);                         /* yellow on blue */
	SEND(0x10, 'A');
	gpu_render(&gpu, frame);
	CHECK(cell_shows(0, 0, 'A', 0x1E), "A at 0,0");
	CHECK(cell_shows(1, 0, ' ', 0x07), "untouched cell keeps the power-on attr");

	/* PUTS, CR, LF, BS, TAB */
	uint8_t puts[] = {0x11, 6, 'x', 'y', '\r', 'z', '\n', 'Q'};
	send(puts, sizeof puts);
	gpu_render(&gpu, frame);
	CHECK(cell_shows(0, 0, 'z', 0x1E), "CR returns to column 0");
	CHECK(cell_shows(1, 0, 'x', 0x1E), "x at 1,0");
	CHECK(cell_shows(0, 1, 'Q', 0x1E), "LF goes to the next line, column 0");
	SEND(0x10, 0x08);
	SEND(0x10, 'R');
	SEND(0x10, 0x09);
	SEND(0x10, 'T');
	gpu_render(&gpu, frame);
	CHECK(cell_shows(0, 1, 'R', 0x1E), "BS overwrote Q");
	CHECK(cell_shows(8, 1, 'T', 0x1E), "TAB to column 8");

	/* GETXY */
	SEND(0x18);
	CHECK_EQ(read_resp(r, 2), 2);
	CHECK(r[0] == 9 && r[1] == 1, "cursor %d,%d", r[0], r[1]);

	/* wrap at column 80 */
	SEND(0x12, 79, 5);
	SEND(0x10, 'W');
	SEND(0x10, 'X');
	gpu_render(&gpu, frame);
	CHECK(cell_shows(79, 5, 'W', 0x1E), "W at 79,5");
	CHECK(cell_shows(0, 6, 'X', 0x1E), "wrapped to 0,6");

	/* writing past row 29 scrolls */
	SEND(0x12, 0, 29);
	SEND(0x10, 'S');
	SEND(0x10, '\n');
	SEND(0x10, 'U');
	gpu_render(&gpu, frame);
	CHECK(cell_shows(0, 28, 'S', 0x1E), "S scrolled up to row 28");
	CHECK(cell_shows(0, 29, 'U', 0x1E), "U on the last row");
	CHECK(cell_shows(0, 5, 'X', 0x1E), "row 6 moved to row 5");

	/* GOTOXY clamps, POKE, CLEOL, SCROLL */
	SEND(0x12, 200, 200);
	SEND(0x18);
	read_resp(r, 2);
	CHECK(r[0] == 79 && r[1] == 29, "clamped to %d,%d", r[0], r[1]);
	SEND(0x17, 40, 10, 0xDB, 0x4F);           /* full block, white on red */
	SEND(0x12, 3, 3);
	SEND(0x11, 5, 'h', 'e', 'l', 'l', 'o');
	SEND(0x12, 5, 3);
	SEND(0x16);
	gpu_render(&gpu, frame);
	CHECK(cell_shows(40, 10, 0xDB, 0x4F), "POKE");
	CHECK(cell_shows(4, 3, 'e', 0x1E) && cell_shows(5, 3, ' ', 0x1E), "CLEOL from the cursor");
	SEND(0x15, 3);
	gpu_render(&gpu, frame);
	CHECK(cell_shows(40, 7, 0xDB, 0x4F), "SCROLL 3");

	/* cursor rendering: underline inverts rows 14-15, block inverts all */
	SEND(0x02, 0x07);                          /* CLS */
	SEND(0x14, 1);
	gpu.vsync_count = 0;
	gpu_render(&gpu, frame);
	CHECK(frame[14 * GPU_OUT_W] == pal(7) && frame[13 * GPU_OUT_W] == pal(0), "underline cursor");
	SEND(0x14, 2);
	gpu_render(&gpu, frame);
	CHECK(frame[0] == pal(7), "block cursor");
	gpu.vsync_count = 15;
	gpu_render(&gpu, frame);
	CHECK(frame[0] == pal(0), "cursor blinks off");

	/* DEFCHAR16 */
	uint8_t def[18] = {0x19, 'Z'};
	for (int i = 0; i < 16; i++) def[2 + i] = (uint8_t)(i & 1 ? 0xFF : 0x00);
	send(def, sizeof def);
	SEND(0x14, 0);
	SEND(0x17, 0, 0, 'Z', 0x07);
	gpu_render(&gpu, frame);
	CHECK(frame[0] == pal(0) && frame[GPU_OUT_W] == pal(7), "custom glyph rows");

	SEND(0x0C);
	dump("gpu_text");
}

static void test_gfx(void)
{
	uint8_t r[2];
	SEND(0x01, 1);                             /* GFX mode */
	CHECK_EQ(gpu.mode, GPU_MODE_GFX);
	SEND(0x02, 4);                             /* CLS red */
	gpu_render(&gpu, frame);
	CHECK(gpx(0, 0) == pal(4) && gpx(319, 239) == pal(4), "CLS");
	CHECK(frame[1] == pal(4) && frame[GPU_OUT_W] == pal(4), "pixel doubling");

	SEND(0x20, 10, 0, 20, 15);                  /* PIXEL (10,20) white */
	SEND(0x20, 0xFF, 0xFF, 20, 15);             /* x = -1: clipped */
	SEND(0x21, 50, 0, 60, 30, 0, 40, 2);        /* FILL_RECT 30x40 green at (50,60) */
	SEND(0x21, 0x2C, 0x01, 230, 100, 0, 100, 3);/* partly off-screen: clipped */
	SEND(0x22, 100, 0, 10, 20, 0, 10, 14);      /* RECT outline */
	SEND(0x23, 0, 0, 0, 0x3F, 0x01, 239, 13);   /* LINE (0,0)-(319,239) */
	gpu_render(&gpu, frame);
	CHECK(gpx(10, 20) == pal(15), "PIXEL");
	CHECK(gpx(50, 60) == pal(2) && gpx(79, 99) == pal(2) && gpx(80, 70) == pal(4) && gpx(50, 100) == pal(4),
	      "FILL_RECT bounds");
	CHECK(gpx(319, 239) == pal(13) || gpx(319, 239) == pal(3), "clipped fill / line end");
	CHECK(gpx(100, 10) == pal(14) && gpx(119, 19) == pal(14) && gpx(110, 15) == pal(4), "RECT is an outline");
	CHECK(gpx(0, 0) == pal(13), "LINE start");

	/* BLIT8: 2x2 */
	SEND(0x24, 200, 0, 5, 2, 2, 1, 2, 3, 5);
	gpu_render(&gpu, frame);
	CHECK(gpx(200, 5) == pal(1) && gpx(201, 5) == pal(2) && gpx(200, 6) == pal(3) && gpx(201, 6) == pal(5),
	      "BLIT8 row-major");

	/* BLIT1 with transparent background */
	SEND(0x21, 0, 0, 0, 16, 0, 2, 9);           /* backdrop */
	SEND(0x25, 0, 0, 0, 10, 2, 11, 0xFF, 0x80, 0x40, 0x01, 0x80);
	gpu_render(&gpu, frame);
	/* row 0 bytes $80 $40: pixels 0 and 9; row 1 bytes $01 $80: pixels 7 and 8 */
	CHECK(gpx(0, 0) == pal(11) && gpx(1, 0) == pal(9) && gpx(9, 0) == pal(11) &&
	      gpx(7, 1) == pal(11) && gpx(8, 1) == pal(11) && gpx(9, 1) == pal(9),
	      "BLIT1 bits and transparency");

	/* TEXT8 */
	SEND(0x26, 0, 1, 150, 12, 0, 1, 'H');
	gpu_render(&gpu, frame);
	bool ok = true;
	for (int y = 0; y < 8; y++)
		for (int x = 0; x < 8; x++) {
			bool on = font8x8_cp437['H'][y] & (0x80 >> x);
			if (gpx(256 + x, 150 + y) != (on ? pal(12) : pal(0)))
				ok = false;
		}
	CHECK(ok, "TEXT8 glyph");

	/* GETPIXEL waits for earlier commands (it's in the FIFO) */
	SEND(0x28, 10, 0, 20);
	CHECK_EQ(read_resp(r, 1), 1);
	CHECK_EQ(r[0], 15);

	/* VSCROLL */
	SEND(0x27, 5, 7);
	gpu_render(&gpu, frame);
	CHECK(gpx(10, 15) == pal(15) && gpx(0, 239) == pal(7), "VSCROLL up 5");
	SEND(0x27, (uint8_t)-5, 6);
	gpu_render(&gpu, frame);
	CHECK(gpx(10, 20) == pal(15) && gpx(0, 0) == pal(6), "VSCROLL down 5");

	/* PALETTE, PALETTE_RESET */
	SEND(0x03, 4, 0x12, 0x34, 0x56);
	CHECK_EQ(gpu.palette[4], ((0x12 >> 3) << 11) | ((0x34 >> 2) << 5) | (0x56 >> 3));
	SEND(0x04);
	CHECK_EQ(gpu.palette[15], 0xFFFF);
	CHECK_EQ(gpu.palette[16], 0);
	CHECK_EQ(gpu.palette[231], 0xFFFF);

	/* DEFCHAR8 */
	SEND(0x29, 'H', 0xFF, 0, 0, 0, 0, 0, 0, 0);
	CHECK_EQ(gpu.font8['H'][0], 0xFF);
	dump("gpu_gfx");
	SEND(0x01, 0);
}

static void test_general(void)
{
	uint8_t r[4];
	/* FENCE / FENCE_READ with the IRQ */
	SEND(CARD_OP_IRQ_EN, 1);
	SEND(0x05, 0x5A);
	CHECK(card_irq(&gpu.card), "FENCE raises IRQ");
	SEND(0x06);
	CHECK_EQ(read_resp(r, 1), 1);
	CHECK_EQ(r[0], 0x5A);
	CHECK(!card_irq(&gpu.card), "FENCE_READ releases IRQ");
	/* VSYNC_COUNT */
	gpu.vsync_count = 0;
	gpu_vsync(&gpu); gpu_vsync(&gpu);
	SEND(0x07);
	read_resp(r, 1);
	CHECK_EQ(r[0], 2);
	/* errors: unknown opcode, short frame; longer frames are fine */
	uint32_t e = gpu.errors;
	SEND(0x5F);
	SEND(0x21, 1, 2);
	CHECK_EQ(gpu.errors, e + 2);
	SEND(0x10, 'q', 1, 2, 3);
	CHECK_EQ(gpu.errors, e + 2);
	/* IDENT */
	SEND(CARD_OP_IDENT);
	CHECK_EQ(read_resp(r, 4), 4);
	CHECK(r[0] == CARD_TYPE_GPU && r[3] == CARD_IDENT_SIG, "IDENT");
	/* SOFT_RESET restores the power-on state */
	SEND(0x01, 1);
	SEND(CARD_OP_SOFT_RESET);
	CHECK(gpu.mode == GPU_MODE_TEXT && gpu.attr == 0x07 && gpu.cursor == 1, "SOFT_RESET");
}

static void test_fifo(void)
{
	/* idle: FREE = 127 */
	CHECK_EQ(status(), 127);
	/* fill without executing: frames are stored until gpu_run */
	uint8_t blit[1 + 5 + 50 * 20];
	blit[0] = 0x24; blit[1] = 0; blit[2] = 0; blit[3] = 0; blit[4] = 50; blit[5] = 20;
	memset(blit + 6, 7, 50 * 20);
	int accepted = 0;
	for (int i = 0; i < 10; i++) {
		uint8_t st;
		card_select(&gpu.card, true);
		st = card_next_miso(&gpu.card);
		if ((int)sizeof blit > st * 64) {
			card_select(&gpu.card, false);     /* host rule: not enough room, give up */
			break;
		}
		for (size_t k = 0; k < sizeof blit; k++) {
			(void)card_next_miso(&gpu.card);
			card_mosi(&gpu.card, blit[k]);
		}
		card_select(&gpu.card, false);
		accepted++;
	}
	CHECK_EQ(gpu.frame_seq - gpu.exec_seq, (unsigned)accepted);
	CHECK(accepted >= 7, "only %d BLITs fitted in 8 KB", accepted);
	/* the guarantee: a frame of FREE*64 bytes is always accepted */
	uint8_t st = status();
	(void)st;
	gpu_run(&gpu, 1000);
	CHECK_EQ(status(), 127);
	static uint8_t max[127 * 64];
	max[0] = 0x00;                              /* a NOP with padding */
	uint32_t e = gpu.errors;
	card_frame(&gpu.card, max, 0, (int)sizeof max);
	CHECK_EQ(gpu.errors, e);
	CHECK_EQ(gpu.frame_seq - gpu.exec_seq, 1u);
	/* a frame that does not fit is discarded and counted */
	static uint8_t huge[GPU_FIFO_SIZE];
	card_frame(&gpu.card, huge, 0, (int)sizeof huge);
	CHECK_EQ(gpu.errors, e + 1);
	gpu_run(&gpu, 1000);
	CHECK_EQ(gpu.frame_seq, gpu.exec_seq);
	/* a maximum-rate host that respects FREE never loses a frame */
	e = gpu.errors;
	for (int i = 0; i < 2000; i++) {
		uint8_t putc_frame[2] = {0x10, (uint8_t)('a' + i % 26)};
		card_frame(&gpu.card, putc_frame, 0, 2);
		if (i % 7 == 0)
			gpu_run(&gpu, 3);
	}
	gpu_run(&gpu, 100000);
	CHECK_EQ(gpu.errors, e);
}

int main(void)
{
	gpu_init(&gpu);
	test_text();
	test_gfx();
	test_general();
	test_fifo();
	return check_report("GPU-001/002/003 gpu core");
}
