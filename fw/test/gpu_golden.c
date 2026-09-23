/*
 * The golden frame for the emulated graphics card tests (GPU-005): feed a
 * command stream to the GPU core, the one the firmware runs, and write what
 * gpu_render() shows.
 *
 *   gpu_golden frames.bin vsyncs out.rgb
 * frames.bin: each frame as [len lo][len hi][bytes]. out.rgb: 640x480 x
 * uint32 0x00RRGGBB, little-endian.
 */
#include <stdio.h>
#include <stdlib.h>

#include "gpu.h"

static gpu_t gpu;
static uint32_t rgb[GPU_OUT_W * GPU_OUT_H];

int main(int argc, char **argv)
{
	if (argc != 4) {
		fprintf(stderr, "usage: gpu_golden frames.bin vsyncs out.rgb\n");
		return 2;
	}
	FILE *in = fopen(argv[1], "rb");
	if (!in) {
		perror(argv[1]);
		return 1;
	}
	gpu_init(&gpu);
	static uint8_t frame[CARD_FRAME_MAX];
	int lo, hi;
	while ((lo = fgetc(in)) != EOF && (hi = fgetc(in)) != EOF) {
		size_t len = (size_t)(lo | hi << 8);
		if (len > sizeof frame || fread(frame, 1, len, in) != len) {
			fprintf(stderr, "bad frame\n");
			return 1;
		}
		card_frame(&gpu.card, frame, NULL, (int)len);
		while (gpu_run(&gpu, 1000))
			;
	}
	fclose(in);
	for (long v = strtol(argv[2], NULL, 0); v > 0; v--)
		gpu_vsync(&gpu);
	gpu_render(&gpu, rgb);
	FILE *out = fopen(argv[3], "wb");
	if (!out || fwrite(rgb, sizeof rgb, 1, out) != 1) {
		perror(argv[3]);
		return 1;
	}
	return fclose(out) ? 1 : 0;
}
